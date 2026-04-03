"""
BaseWorker - Abstract base class for all specialized agent workers.

Workers execute atomic tasks delegated by the orchestrator.
Each worker type (RAG, Code, Web, etc.) implements specific logic.

Thread-safety: Workers create dedicated LLM client instances per call,
never mutating the shared LLMService singleton used by chat.

ReAct support: Workers can opt-in to iterative think→act→observe loops
by setting REACT_ENABLED = True and implementing get_tools().
"""
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from jsonschema import validate, ValidationError

from ...models.database import AgentWorkerTask
from ...models.schemas import AgentTaskStatus
from ..llm_service import LLMService
from ...core.llm_clients import GeminiClient, OllamaClient
from .react_loop import ReactLoop, ToolDefinition, ReactResult
from .output_evaluator import OutputEvaluator, ErrorClassifier, ErrorType, OutputQuality, ReflexionNote

logger = logging.getLogger("ahri.worker")


class BaseWorker(ABC):
    """
    Abstract base class for agent workers.

    Each worker specializes in a specific task type and is responsible for:
    1. Executing atomic tasks with structured input
    2. Calling appropriate LLM models via dedicated client instances
    3. Returning structured JSON output
    4. Handling retries and JSON validation

    ReAct support:
    - Set REACT_ENABLED = True in subclass
    - Implement get_tools() to return available tools
    - execute_react() will run the ReAct loop instead of one-shot execute()

    Self-correction support:
    - Set ENABLE_EVALUATION = True to evaluate output quality
    - Set MAX_SELF_CORRECTIONS > 0 to enable retry with reflexion notes
    - execute_with_correction() wraps execute_react() with evaluation + retry

    Thread-safety: _call_llm() creates per-call client instances,
    never calling set_mode() on the shared LLMService singleton.
    """

    # Override in subclasses to define worker specialization.
    # This is prepended to every LLM call as context.
    ROLE_PROMPT: str = ""

    # ── ReAct Configuration (override in subclasses) ──
    REACT_ENABLED: bool = False
    REACT_MAX_ITERATIONS: int = 5
    REACT_TOKEN_BUDGET: int = 4000

    # ── Self-Correction Configuration (override in subclasses) ──
    ENABLE_EVALUATION: bool = True    # Set False for cheap workers (RAG, Memory, Router)
    MAX_SELF_CORRECTIONS: int = 2     # Max retry attempts with reflexion

    def __init__(self, llm_service: LLMService, worker_type: str, default_model: str):
        """
        Args:
            llm_service: LLM service (used for client factory methods, NOT for set_mode)
            worker_type: Worker type identifier (RAG, Code, Web, etc.)
            default_model: Default model mode string ("GOOGLE", "PRO", "LOCAL", etc.)
        """
        self.llm = llm_service
        self.worker_type = worker_type
        self.default_model = default_model

    @abstractmethod
    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: dict
    ) -> AgentWorkerTask:
        """Execute worker task and return result (one-shot mode)."""
        pass

    def get_tools(self) -> list[ToolDefinition]:
        """
        Override in subclasses to define tools for ReAct loop.
        Each tool wraps an existing worker method as a callable action.
        Return empty list to stay in one-shot mode.
        """
        return []

    async def execute_react(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: dict
    ) -> AgentWorkerTask:
        """
        Entry point that decides: ReAct loop or one-shot.

        If REACT_ENABLED and get_tools() returns tools, runs the ReAct loop.
        Otherwise falls back to the existing execute() method.
        """
        tools = self.get_tools()
        if not self.REACT_ENABLED or not tools:
            return await self.execute(db, execution_id, input_data)

        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            # Extract orchestrator params for LLM calls
            orch_params = input_data.pop("_orchestrator_params", {})
            api_key = orch_params.get("api_key")
            thinking_budget = orch_params.get("thinking_budget", 0)
            enable_thinking = orch_params.get("enable_thinking", False)

            # Build the task description from input_data
            task_description = self._build_react_task(input_data)

            # Context for the loop (dependency results, reflexion notes)
            context = {}
            if input_data.get("dependency_results"):
                context["dependency_results"] = input_data["dependency_results"]
            if input_data.get("_reflexion_notes"):
                context["_reflexion_notes"] = input_data["_reflexion_notes"]

            # Create a bound LLM caller that uses the orchestrator's API key
            async def bound_llm_caller(prompt: str, schema: Optional[dict] = None) -> Any:
                return await self._call_llm(
                    prompt=prompt,
                    model=self.default_model,
                    schema=schema,
                    api_key=api_key,
                    thinking_budget=thinking_budget,
                    enable_thinking=enable_thinking,
                )

            # Run the ReAct loop
            loop = ReactLoop(
                llm_caller=bound_llm_caller,
                tools=tools,
                max_iterations=self.REACT_MAX_ITERATIONS,
                token_budget_per_step=self.REACT_TOKEN_BUDGET,
                system_prompt=self.ROLE_PROMPT,
            )

            result: ReactResult = await loop.run(task_description, context)

            # Build output data
            output_data = {
                "answer": result.answer,
                "react_steps": result.steps,
                "iterations": result.iterations,
                "forced_finish": result.forced_finish,
            }

            tokens = result.total_tokens_estimated
            logger.info(
                f"[{self.worker_type}] ReAct completed: "
                f"{result.iterations} iterations, ~{tokens} tokens, "
                f"forced={result.forced_finish}"
            )

            return await self._complete_task(db, task, output_data, tokens, start_time)

        except Exception as e:
            logger.error(f"[{self.worker_type}] ReAct execution failed: {e}")
            return await self._fail_task(db, task, str(e), start_time)

    def _build_react_task(self, input_data: dict) -> str:
        """
        Build a task description string from input_data for the ReAct loop.
        Override in subclasses for custom task formatting.
        """
        # Remove internal keys
        clean = {k: v for k, v in input_data.items()
                 if not k.startswith("_") and k != "dependency_results"}

        # Try common task description fields
        if "prompt" in clean:
            return clean["prompt"]
        if "task" in clean:
            return clean["task"]
        if "task_description" in clean:
            return clean["task_description"]
        if "query" in clean:
            return clean["query"]

        # Fallback: serialize the input
        return json.dumps(clean, ensure_ascii=False, default=str)

    async def execute_with_correction(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: dict
    ) -> AgentWorkerTask:
        """
        Execute with self-correction via the Reflexion pattern.

        Wraps execute_react() with output evaluation and retry logic:
        1. Execute the task (via ReAct loop or one-shot)
        2. Evaluate output quality (if ENABLE_EVALUATION)
        3. If poor/failed: generate reflexion note, retry with notes injected
        4. If error: classify (temporary/logical/permanent) and retry or skip

        Max attempts = 1 + MAX_SELF_CORRECTIONS (e.g., 3 total with default 2).
        """
        if not self.ENABLE_EVALUATION or self.MAX_SELF_CORRECTIONS == 0:
            return await self.execute_react(db, execution_id, input_data)

        evaluator = OutputEvaluator()
        reflexion_notes: list[ReflexionNote] = []
        best_result = None
        task_description = self._build_react_task(input_data)

        # Extract orchestrator params once (will be re-injected each attempt)
        orch_params = input_data.get("_orchestrator_params", {})

        for attempt in range(1 + self.MAX_SELF_CORRECTIONS):
            # Inject reflexion notes from previous failed attempts
            if reflexion_notes:
                input_data["_reflexion_notes"] = [n.to_dict() for n in reflexion_notes]

            # Re-inject orchestrator params (may have been popped by execute_react)
            if "_orchestrator_params" not in input_data and orch_params:
                input_data["_orchestrator_params"] = orch_params

            # Execute
            result = await self.execute_react(db, execution_id, input_data)
            best_result = result

            # Last attempt — return whatever we got
            if attempt == self.MAX_SELF_CORRECTIONS:
                logger.info(f"[{self.worker_type}] Final attempt {attempt + 1}, returning result as-is")
                return result

            # ── Handle completed tasks ──
            if result.status == AgentTaskStatus.COMPLETED:
                output_data = result.output_data or {}

                # Build a bound LLM caller for evaluation
                api_key = orch_params.get("api_key")
                thinking_budget = orch_params.get("thinking_budget", 0)
                enable_thinking = orch_params.get("enable_thinking", False)

                async def eval_llm_caller(prompt, schema=None):
                    return await self._call_llm(
                        prompt=prompt, model=self.default_model,
                        schema=schema, api_key=api_key,
                        thinking_budget=thinking_budget,
                        enable_thinking=enable_thinking,
                    )

                evaluation = await evaluator.evaluate(
                    task_description=task_description,
                    worker_type=self.worker_type,
                    input_data=input_data,
                    output_data=output_data,
                    llm_caller=eval_llm_caller,
                )

                logger.info(
                    f"[{self.worker_type}] Attempt {attempt + 1} evaluation: "
                    f"quality={evaluation.quality.value}, retry={evaluation.should_retry}"
                )

                if evaluation.quality in (OutputQuality.EXCELLENT, OutputQuality.ADEQUATE):
                    return result  # Good enough

                # Poor/Failed — create reflexion note and retry
                note = evaluator.create_reflexion_note(
                    attempt=attempt + 1,
                    error_type=ErrorType.LOGICAL,
                    error_or_evaluation=evaluation,
                )
                reflexion_notes.append(note)
                continue

            # ── Handle failed tasks ──
            elif result.status == AgentTaskStatus.FAILED:
                error_str = result.error or ""
                error_type = evaluator.classify_error(error_str)

                logger.info(
                    f"[{self.worker_type}] Attempt {attempt + 1} failed: "
                    f"type={error_type.value}, error={error_str[:100]}"
                )

                if error_type == ErrorType.PERMANENT:
                    return result  # No point retrying

                # Temporary or logical — create reflexion note and retry
                note = evaluator.create_reflexion_note(
                    attempt=attempt + 1,
                    error_type=error_type,
                    error_or_evaluation=error_str,
                )
                reflexion_notes.append(note)

                if error_type == ErrorType.TEMPORARY:
                    import asyncio
                    await asyncio.sleep(2)  # Brief delay for temporary errors

                continue

            else:
                return result  # Unknown status, return as-is

        # Persist retry metadata to the task record
        if best_result and reflexion_notes:
            try:
                best_result.retry_count = len(reflexion_notes)
                best_result.reflexion_notes = [n.to_dict() for n in reflexion_notes]
                await db.commit()
            except Exception as e:
                logger.warning(f"[{self.worker_type}] Failed to persist retry metadata: {e}")

        return best_result  # Should not reach here, but safety fallback

    def _create_client(self, model: str, api_key: Optional[str] = None) -> tuple:
        """
        Create a dedicated LLM client instance for this call.

        Returns (client_type, client) where client_type is 'gemini' or 'ollama'.
        Never mutates the shared LLMService singleton.

        Args:
            model: Mode string ("GOOGLE", "PRO", "LOCAL") or direct model ID
            api_key: Optional specific API key (from round-robin rotation)
        """
        # Local/Ollama models
        if model == "LOCAL" or model.startswith("qwen") or model.startswith("ollama"):
            ollama_model = self.llm.settings.agent_mode_local_model
            ollama_url = self.llm.settings.ollama_base_url + "/api/chat"
            return ("ollama", OllamaClient(model_name=ollama_model, api_url=ollama_url))

        # Gemini/Google models — create fresh GeminiClient instance
        if model in ("FLASH", "LITE", "GOOGLE", "PRO") or model.startswith("gemini") or model.startswith("gemma"):
            target_model = model
            if model in ("FLASH", "PRO", "GOOGLE"):
                target_model = getattr(self.llm.settings, "google_model_flash", "gemini-2.5-flash")
            elif model == "LITE":
                target_model = getattr(self.llm.settings, "google_model_lite", "gemini-3.1-flash-lite-preview")

            # If a specific API key was provided (round-robin), create client directly
            if api_key:
                return ("gemini", GeminiClient(api_key=api_key, model_name=target_model))

            client = self.llm.get_agent_client(target_model)
            if client:
                return ("gemini", client)

        # Fallback: try any available Gemini client (with rotated key if available)
        if api_key:
            fallback_model = self.llm.settings.agent_mode_api_model
            return ("gemini", GeminiClient(api_key=api_key, model_name=fallback_model))

        client = self.llm.get_agent_client()
        if client:
            return ("gemini", client)

        raise Exception(f"No LLM client available for model '{model}'")

    async def _call_llm(
        self,
        prompt: str,
        model: Optional[str] = None,
        schema: Optional[dict] = None,
        max_retries: int = 3,
        api_key: Optional[str] = None,
        thinking_budget: int = 0,
        enable_thinking: bool = False,
    ) -> Any:
        """
        Call LLM with retry logic and JSON validation.

        Thread-safe: Creates a dedicated client instance per call.
        Never calls set_mode() on the shared LLMService singleton.

        Args:
            prompt: Input prompt for LLM
            model: Model mode string (default: self.default_model)
            schema: Optional JSON schema for validation
            max_retries: Maximum retry attempts (default: 3)
            api_key: Specific API key from round-robin rotation
            thinking_budget: Gemini thinking budget tokens (0=off)
            enable_thinking: Ollama/Qwen thinking toggle

        Returns:
            str or dict (if schema provided and valid JSON)
        """
        import asyncio

        model = model or self.default_model
        client_type, client = self._create_client(model, api_key=api_key)

        # Prepend role prompt if defined
        if self.ROLE_PROMPT:
            prompt = f"{self.ROLE_PROMPT}\n\n{prompt}"

        for attempt in range(max_retries):
            try:
                # Generate response using dedicated client instance
                if client_type == "ollama":
                    # OllamaClient.generate_sync() — non-streaming, returns full text
                    def _generate():
                        return client.generate_sync(
                            messages=[{"role": "user", "content": prompt}],
                            think=enable_thinking,
                        )
                    loop = asyncio.get_running_loop()
                    response_text = await loop.run_in_executor(None, _generate)

                elif client_type == "gemini":
                    # GeminiClient.generate_content_rest() — REST API, thread-safe
                    def _generate():
                        return client.generate_content_rest(
                            prompt, thinking_budget=thinking_budget
                        ) or ""
                    loop = asyncio.get_running_loop()
                    response_text = await loop.run_in_executor(None, _generate)

                else:
                    raise Exception(f"Unknown client type: {client_type}")

                # If no schema, return raw text
                if not schema:
                    return response_text.strip()

                # Try to parse and validate JSON
                try:
                    parsed = json.loads(response_text)
                    validate(instance=parsed, schema=schema)
                    return parsed
                except (json.JSONDecodeError, ValidationError) as e:
                    if attempt == max_retries - 1:
                        # Last retry — use json-repair as fallback
                        try:
                            from json_repair import repair_json
                            repaired = repair_json(response_text)
                            validate(instance=repaired, schema=schema)
                            return repaired
                        except Exception:
                            try:
                                return json.loads(response_text)
                            except Exception:
                                raise Exception(f"Failed to parse JSON after {max_retries} retries: {e}")

                    # Retry with clarification prompt
                    prompt = f"{prompt}\n\nThe previous response was not valid JSON. Please return ONLY valid JSON matching the schema."
                    continue

            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"LLM call failed after {max_retries} retries: {str(e)}")
                await asyncio.sleep(1)

        raise Exception("Unexpected: retry loop completed without return")

    async def _create_task_record(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: dict,
        model: Optional[str] = None
    ) -> AgentWorkerTask:
        """Create AgentWorkerTask record in database with status=running."""
        task = AgentWorkerTask(
            execution_id=execution_id,
            worker_type=self.worker_type,
            model=model or self.default_model,
            input_data=input_data,
            status=AgentTaskStatus.RUNNING
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task

    async def _complete_task(
        self,
        db: AsyncSession,
        task: AgentWorkerTask,
        output_data: dict,
        tokens_used: int = 0,
        start_time: Optional[float] = None
    ) -> AgentWorkerTask:
        """Mark task as completed and update database."""
        # Inject tokens_used into output_data for orchestrator to read
        output_data["_tokens_used"] = tokens_used

        task.output_data = output_data
        task.tokens_used = tokens_used
        task.status = AgentTaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()

        if start_time:
            task.duration_ms = int((time.time() - start_time) * 1000)

        await db.commit()
        await db.refresh(task)
        return task

    async def _fail_task(
        self,
        db: AsyncSession,
        task: AgentWorkerTask,
        error: str,
        start_time: Optional[float] = None
    ) -> AgentWorkerTask:
        """Mark task as failed and update database."""
        task.error = error
        task.status = AgentTaskStatus.FAILED
        task.completed_at = datetime.utcnow()

        if start_time:
            task.duration_ms = int((time.time() - start_time) * 1000)

        await db.commit()
        await db.refresh(task)
        return task

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (heuristic: 1 token ~ 4 chars)."""
        return len(text) // 4 + 5
