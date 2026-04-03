"""
OrchestratorService - Multi-agent task orchestration with Gemini coordination.

The orchestrator plans task decomposition, delegates to specialized workers,
and synthesizes final results. Uses hybrid approach:
- Gemini Flash as orchestrator (native function calling, high reliability)
- Configured agent model workers for execution (low cost, specialized tasks)
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.database import AgentExecution, AgentWorkerTask
from ..models.schemas import AgentExecutionStatus, AgentTaskStatus
from .llm_service import LLMService
from .vector_service import VectorService
from .tpm_manager import TPMManager, AgentKeyRotator
from .workers.rag_worker import RAGWorker
from .workers.code_worker import CodeWorker
from .workers.shell_worker import ShellWorker
from .workers.memory_worker import MemoryWorker
from .workers.web_worker import WebWorker
from .workers.vision_worker import VisionWorker
from .workers.browser_worker import BrowserWorker
from .workers.router_worker import RouterWorker
from .workers.dynamic_worker import DynamicWorker
from .workers.context_manager import WorkerContextManager
from .plan_cache import PlanCache
from .event_log import (
    EventType, get_or_create_log, cleanup_log, WORKER_FALLBACKS
)

logger = logging.getLogger("ahri.orchestrator")


class OrchestratorService:
    """
    Orchestrator for multi-agent task execution.

    Coordinates specialized workers (RAG, Code, Web, etc.) to accomplish complex goals.
    Implements TPM management, retry logic, and result synthesis.
    """

    def __init__(
        self,
        llm_service: LLMService,
        vector_service: VectorService,
        tpm_manager: Optional[TPMManager] = None,
        key_rotator: Optional[AgentKeyRotator] = None,
    ):
        self.llm = llm_service
        self.vector_service = vector_service
        self.tpm = tpm_manager or TPMManager(limit_tpm=250000, limit_rpm=15)
        self.key_rotator = key_rotator
        self._max_parallel = llm_service.settings.agent_mode_max_parallel

        # Initialize all workers (Phase 2: All 8 workers)
        self.workers = {
            "RAG": RAGWorker(llm_service, vector_service),
            "Code": CodeWorker(llm_service),
            "Shell": ShellWorker(llm_service),
            "Memory": MemoryWorker(llm_service),
            "Web": WebWorker(llm_service),
            "Vision": VisionWorker(llm_service),
            "Browser": BrowserWorker(llm_service),
            "Router": RouterWorker(llm_service),
            "Dynamic": DynamicWorker(llm_service),
        }

        # Runtime params set per-execution (not per-init)
        self._thinking_budget = 0
        self._enable_thinking = False

        # Context engineering, plan caching, and event log
        self._context_manager = WorkerContextManager()
        self._plan_cache = PlanCache()

        # Semaphore to cap parallel worker execution
        self._semaphore = asyncio.Semaphore(self._max_parallel)

    async def execute_task(
        self,
        db: AsyncSession,
        goal: str,
        orchestrator_model: str,
        execution_id: Optional[int] = None,
        reasoning_level: str = "medium",
        enable_thinking: bool = False,
        internet_search_enabled: bool = False,
        permission_mode: str = "auto",
        agent_session_id: Optional[int] = None,
    ) -> "AgentExecution":
        """
        Main orchestration loop.

        Args:
            db: Database session
            goal: User's task goal in natural language
            orchestrator_model: Model for orchestration
            execution_id: Pre-created execution ID (from background task pattern).
                          If None, creates a new record.
            reasoning_level: Gemini thinking budget level (off/low/medium/high)
            enable_thinking: Qwen/Ollama thinking toggle
            internet_search_enabled: Whether Search worker is available
            permission_mode: Permission mode (auto/plan_first/supervised)
            agent_session_id: Session ID for memory context across executions

        Returns:
            Completed AgentExecution with result
        """
        # Set per-execution reasoning params
        _THINKING_MAP = {"off": 0, "low": 1024, "medium": 8192, "high": 24576}
        self._thinking_budget = _THINKING_MAP.get(reasoning_level, 8192)
        self._enable_thinking = enable_thinking

        # Conditionally register Search worker
        if internet_search_enabled and "Search" not in self.workers:
            from .workers.search_worker import SearchWorker
            self.workers["Search"] = SearchWorker(self.llm)
        # Step 1: Get or create execution record
        if execution_id:
            stmt = select(AgentExecution).where(AgentExecution.id == execution_id)
            result = await db.execute(stmt)
            execution = result.scalar_one_or_none()
            if not execution:
                raise Exception(f"Execution {execution_id} not found")
        else:
            execution = AgentExecution(
                goal=goal,
                orchestrator_model=orchestrator_model,
                status=AgentExecutionStatus.PLANNING,
                permission_mode=permission_mode,
            )
            db.add(execution)
            await db.commit()
            await db.refresh(execution)

        logger.info(f"[Orchestrator] Starting execution #{execution.id}: {goal[:100]}")

        # Create event log for this execution (real-time WebSocket streaming)
        event_log = get_or_create_log(execution.id)

        try:
            # Step 1b: Inject session context (memory from previous executions)
            planning_goal = goal
            if agent_session_id:
                session_context = await self._build_session_context(db, agent_session_id, execution.id)
                if session_context:
                    planning_goal = f"[Previous tasks in this session]\n{session_context}\n\n[Current task]\n{goal}"
                    logger.info(f"[Orchestrator] Session context injected ({len(session_context)} chars)")

            # Step 2: Plan task decomposition (always uses flash-lite, independent of chat model)
            plan = await self._plan_task(planning_goal, "LITE")
            execution.plan = plan
            execution.status = AgentExecutionStatus.DELIBERATING
            await db.commit()

            event_log.emit(EventType.PLAN_CREATED, {
                "steps_count": len(plan.get("steps", [])),
                "reasoning": plan.get("reasoning", "")[:200],
            })
            logger.info(f"[Orchestrator] Plan created: {len(plan.get('steps', []))} steps")

            # Step 2b: Deliberate on plan (multi-perspective analysis)
            refined = await self._deliberate_on_plan(goal, plan)
            if refined and refined.get("steps"):
                plan["deliberation"] = refined.get("deliberation", "")
                plan["refined_understanding"] = refined.get("refined_understanding", "")
                plan["steps"] = refined["steps"]
                execution.plan = plan
            elif refined:
                # Deliberation succeeded but didn't refine steps — store analysis only
                if refined.get("deliberation"):
                    plan["deliberation"] = refined["deliberation"]
                if refined.get("refined_understanding"):
                    plan["refined_understanding"] = refined["refined_understanding"]
                execution.plan = plan

            execution.status = AgentExecutionStatus.RUNNING
            await db.commit()

            if refined and refined.get("deliberation"):
                event_log.emit(EventType.PLAN_DELIBERATED, {
                    "deliberation": refined.get("deliberation", "")[:300],
                    "refined_understanding": refined.get("refined_understanding", ""),
                })

            # Step 2b: If plan_first or supervised, pause for user approval
            if permission_mode in ("plan_first", "supervised"):
                execution.status = AgentExecutionStatus.AWAITING_APPROVAL
                await db.commit()
                logger.info(f"[Orchestrator] Execution #{execution.id} awaiting user approval (mode={permission_mode})")
                return execution

            # Step 3: Execute workers (with parallelization support + replanning)
            results = await self._execute_workers_with_dependencies(
                db, execution.id, plan.get("steps", []), goal=goal,
                event_log=event_log,
            )

            # Step 4: Synthesize final result (always uses flash-lite)
            event_log.emit(EventType.SYNTHESIS_STARTED, {"steps_completed": len(results)})
            final_result = await self._synthesize_results(goal, plan, results, "LITE")
            execution.result = final_result
            execution.status = AgentExecutionStatus.COMPLETED
            execution.completed_at = datetime.utcnow()
            await db.commit()

            # Record success in plan cache
            self._plan_cache.record_outcome(goal, success=True)
            event_log.emit(EventType.EXECUTION_COMPLETED, {
                "result_length": len(final_result),
            })
            logger.info(f"[Orchestrator] Execution #{execution.id} completed successfully")
            return execution

        except Exception as e:
            logger.error(f"[Orchestrator] Execution #{execution.id} failed: {e}")
            execution.error = str(e)
            execution.status = AgentExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            await db.commit()

            # Record failure in plan cache
            self._plan_cache.record_outcome(goal, success=False)
            event_log.emit(EventType.EXECUTION_FAILED, {"error": str(e)[:300]})
            return execution

        finally:
            # Cleanup event log after a delay (let WebSocket clients drain events)
            async def _delayed_cleanup():
                await asyncio.sleep(30)
                cleanup_log(execution.id)
            asyncio.create_task(_delayed_cleanup())

    async def _plan_task(self, goal: str, model: str) -> dict:
        """
        Orchestrator generates step-by-step execution plan.

        Phase 3: Uses Gemini function calling for PRO model (reliable structured output).
        Falls back to prompt-based for other models.

        Args:
            goal: User's task goal
            model: Orchestrator model (PRO or GOOGLE)

        Returns:
            {
                "reasoning": str,  # Why this plan
                "steps": [
                    {
                        "worker": str,     # Worker type (RAG, Code, etc.)
                        "input": dict,     # Input parameters for worker
                        "description": str # What this step does
                    }
                ]
            }
        """
        # Check plan cache first (saves ~5K tokens + ~500ms per hit)
        cached = self._plan_cache.get(goal)
        if cached:
            logger.info("[Orchestrator] Plan cache hit — reusing cached plan")
            return cached

        # Use Gemini function calling for PRO model
        if model == "PRO":
            try:
                plan = await self._plan_task_with_function_calling(goal)
                self._plan_cache.store(goal, plan)
                return plan
            except Exception as e:
                logger.warning(f"[Orchestrator] Function calling failed, falling back to prompt-based: {e}")
                # Fall through to prompt-based approach

        # Prompt-based planning (fallback or for other models)
        plan = await self._plan_task_prompt_based(goal, model)
        self._plan_cache.store(goal, plan)
        return plan

    async def _plan_task_with_function_calling(self, goal: str) -> dict:
        """
        Use Gemini function calling for structured plan generation.

        Uses google-genai SDK with async support (client.aio).
        This is more reliable than prompt-based as JSON is guaranteed valid.
        """
        from google import genai as genai_sdk
        from google.genai import types

        # Define the function schema using new SDK types
        create_plan_function = types.FunctionDeclaration(
            name="create_execution_plan",
            description="Create a multi-step execution plan for agent orchestration",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "reasoning": types.Schema(
                        type="STRING",
                        description="Explanation of why this approach is optimal for the task"
                    ),
                    "steps": types.Schema(
                        type="ARRAY",
                        description="Ordered list of steps to execute",
                        items=types.Schema(
                            type="OBJECT",
                            properties={
                                "worker": types.Schema(
                                    type="STRING",
                                    enum=list(self.workers.keys()),
                                    description="Worker type to execute this step"
                                ),
                                "input": types.Schema(
                                    type="OBJECT",
                                    description="Input parameters for the worker (specific to worker type)"
                                ),
                                "description": types.Schema(
                                    type="STRING",
                                    description="What this step accomplishes"
                                ),
                                "depends_on": types.Schema(
                                    type="ARRAY",
                                    items=types.Schema(type="INTEGER"),
                                    description="Array of step indices (0-based) this step depends on. Empty or omitted means no dependencies."
                                )
                            },
                            required=["worker", "input", "description"]
                        )
                    )
                },
                required=["reasoning", "steps"]
            )
        )

        tool = types.Tool(function_declarations=[create_plan_function])

        # Resolve orchestrator model name from settings if aliases are used
        orchestrator_model_name = self.llm.settings.agent_mode_orchestrator
        if not orchestrator_model_name or orchestrator_model_name in ("LITE", "FLASH"):
            if orchestrator_model_name == "FLASH":
                orchestrator_model_name = getattr(self.llm.settings, "google_model_flash", "gemini-2.5-flash")
            else:
                orchestrator_model_name = getattr(self.llm.settings, "google_model_lite", "gemini-3.1-flash-lite-preview")
        
        api_key = None
        if self.key_rotator and self.key_rotator.keys:
            api_key, wait = self.key_rotator.get_next_key()
            if wait > 0:
                await asyncio.sleep(wait)
                api_key, _ = self.key_rotator.get_next_key()
        config_key = api_key or self.llm.settings.gemini_primary_key or self.llm.settings.gemini_fallback_key

        # Create per-request client (thread-safe, no global state)
        client = genai_sdk.Client(api_key=config_key)

        # Build prompt with worker capabilities
        # Build dynamic worker list for prompt
        _search_block = ""
        if "Search" in self.workers:
            _search_block = "\n9. **Search** - Search the web for information via Google\n   Required inputs: {{\"query\": str, \"max_results\": int (optional), \"synthesize\": bool (optional)}}"

        prompt = f"""You are a task orchestrator. Create an execution plan for this task: {goal}

Available workers and their capabilities:

1. **RAG** - Search knowledge base and indexed documents
   Required inputs: {{"query": str, "top_k": int}}

2. **Code** - Analyze, generate, review, or execute code
   Required inputs: {{"task_type": "analyze|generate|execute|review", "code": str (for analyze/execute/review), "prompt": str (for generate), "language": str}}

3. **Shell** - Execute shell commands and file operations
   Required inputs: {{"operation": "command|file_read|file_write|list_dir", "command": str (for command), "path": str (for file ops)}}

4. **Memory** - Search execution history and stored knowledge
   Required inputs: {{"query": str, "memory_type": "episodic", "limit": int}}

5. **Web** - Fetch and analyze web pages
   Required inputs: {{"url": str, "action": "fetch|summarize|extract_links|extract_data"}}

6. **Vision** - Analyze images (OCR, object detection, description)
   Required inputs: {{"task_type": "describe|ocr|detect|qa", "image_path": str, "question": str (for qa)}}

7. **Browser** - Automate browser interactions (Playwright)
   Required inputs: {{"action": "navigate|click|fill_form|extract|screenshot", "url": str, "selector": str (for click)}}

8. **Router** - Classify tasks and recommend workers
   Required inputs: {{"task_description": str, "context": str (optional)}}
{_search_block}

10. **Dynamic** - Create a specialized agent for any task not covered by other workers.
   Required inputs: {{"system_prompt": str (detailed role, expertise, and instructions for the agent), "task": str (the specific task to execute), "output_format": "text|json|code"}}
   Use freely when the task needs specialized reasoning, domain expertise, or a custom approach.
   The system_prompt MUST define: the agent's role, domain expertise, and expected output format.
   Example: {{"system_prompt": "You are a senior database architect...", "task": "Optimize this SQL query...", "output_format": "text"}}

Guidelines:
- Use multiple workers when task is complex
- Steps with depends_on can reference previous step outputs
- Steps without depends_on run in parallel
- Keep plans concise (1-5 steps)
- Be specific with input parameters
- Use Dynamic worker freely for specialized reasoning, analysis, writing, math, or any domain-specific task

Call create_execution_plan with your plan."""

        # Generate with function calling via async client
        response = await client.aio.models.generate_content(
            model=orchestrator_model_name,
            contents=prompt,
            config=types.GenerateContentConfig(tools=[tool]),
        )

        # Extract function call arguments
        function_call = response.candidates[0].content.parts[0].function_call

        # Convert to dict
        plan = {
            "reasoning": function_call.args["reasoning"],
            "steps": [dict(step) for step in function_call.args["steps"]]
        }

        logger.info(f"[Orchestrator] Function calling plan created: {len(plan['steps'])} steps")
        return plan

    async def _plan_task_prompt_based(self, goal: str, model: str) -> dict:
        """Legacy prompt-based planning (fallback)."""
        prompt = f"""You are a task orchestrator. Given a user's goal, break it down into steps executed by specialized workers.

Available workers:
- RAG: Search knowledge base and indexed documents (inputs: query, top_k)
- Code: Analyze, generate, review, or execute code (inputs: task_type=analyze|generate|execute|review, code, language, prompt)
- Shell: Execute shell commands and file operations (inputs: operation=command|file_read|file_write|list_dir, command, path)
- Memory: Search execution history and stored knowledge (inputs: query, memory_type=episodic, limit)
- Web: Fetch and analyze web pages (inputs: url, action=fetch|summarize|extract_links|extract_data)
- Vision: Analyze images (inputs: task_type=describe|ocr|detect|qa, image_path, question)
- Browser: Automate browser interactions (inputs: action=navigate|click|fill_form|extract|screenshot, url, selector)
- Router: Classify tasks and recommend workers (inputs: task_description, context)
{"- Search: Search the web for information (inputs: query, max_results, synthesize)" if "Search" in self.workers else ""}
- Dynamic: Create a specialized agent for unique tasks (inputs: system_prompt, task, output_format=text|json|code). Use freely for reasoning, analysis, writing, math, or domain-specific tasks. system_prompt must define the agent's role and expertise.

User goal: {goal}

Create a JSON execution plan with this structure:
{{
  "reasoning": "Why this approach is best",
  "steps": [
    {{
      "worker": "RAG",
      "input": {{"query": "...", "top_k": 5}},
      "description": "What this step accomplishes",
      "depends_on": [0]  // Optional: array of step indices this depends on (0-indexed). Omit for parallel execution.
    }},
    {{
      "worker": "Dynamic",
      "input": {{"system_prompt": "You are a specialist in...", "task": "Analyze...", "output_format": "text"}},
      "description": "Specialized analysis",
      "depends_on": []  // Empty array = no dependencies, can run in parallel with step 0
    }}
  ]
}}

Important:
- Use ALL available workers when appropriate (don't limit to RAG only)
- Steps with "depends_on": [] or no "depends_on" key can run in parallel
- Steps with "depends_on": [0, 1] will wait for steps 0 and 1 to complete
- Keep steps minimal (1-5 steps max)
- Be specific with input parameters
- Return ONLY the JSON, no markdown formatting

Plan:"""

        try:
            # Use dedicated client instance (thread-safe, uses agent key rotation)
            api_key = None
            if self.key_rotator and self.key_rotator.keys:
                api_key, wait = self.key_rotator.get_next_key()
                if wait > 0:
                    await asyncio.sleep(wait)
                    api_key, _ = self.key_rotator.get_next_key()

            target_model = self.llm.settings.agent_mode_api_model or "gemini-3.1-flash-lite-preview"
            key = api_key or self.llm.settings.gemini_primary_key or self.llm.settings.gemini_fallback_key
            if not key:
                raise Exception("No API key available for planning")

            from ..core.llm_clients import GeminiClient
            client = GeminiClient(api_key=key, model_name=target_model)
            response_text = client.generate_content_rest(prompt) or ""

            # Clean markdown code fences if present
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            plan = json.loads(response_text)
            return plan

        except Exception as e:
            logger.error(f"[Orchestrator] Planning failed: {e}")
            # Fallback: simple single-step RAG plan
            return {
                "reasoning": f"Fallback plan due to planning error: {str(e)}",
                "steps": [
                    {
                        "worker": "RAG",
                        "input": {"query": goal, "top_k": 5},
                        "description": "Search knowledge base for answer"
                    }
                ]
            }

    async def _synthesize_results(
        self,
        goal: str,
        plan: dict,
        worker_results: list[dict],
        model: str
    ) -> str:
        """
        Orchestrator combines worker outputs into final answer.

        Args:
            goal: Original user goal
            plan: Execution plan
            worker_results: List of worker output_data dicts
            model: Orchestrator model

        Returns:
            Synthesized final answer as string
        """
        # Format worker results
        results_text = []
        for i, (step, result) in enumerate(zip(plan.get("steps", []), worker_results), 1):
            worker_type = step.get("worker", "Unknown")
            description = step.get("description", "")
            results_text.append(f"Step {i} - {worker_type}: {description}")
            results_text.append(f"Result: {json.dumps(result, indent=2)}\n")

        combined_results = "\n".join(results_text)

        prompt = f"""Synthesize a final answer from worker results.

Original goal: {goal}

Worker results:
{combined_results}

Instructions:
- Create a coherent final answer that addresses the user's goal
- If workers provided source citations, include them
- Be concise but complete (2-4 paragraphs)
- If results are incomplete or contain errors, acknowledge limitations

Final answer:"""

        try:
            # Use dedicated client with key rotation (thread-safe)
            api_key = None
            if self.key_rotator and self.key_rotator.keys:
                api_key, wait = self.key_rotator.get_next_key()
                if wait > 0:
                    await asyncio.sleep(wait)
                    api_key, _ = self.key_rotator.get_next_key()

            target_model = self.llm.settings.agent_mode_api_model or "gemini-3.1-flash-lite-preview"
            key = api_key or self.llm.settings.gemini_primary_key or self.llm.settings.gemini_fallback_key
            if not key:
                logger.warning("[Orchestrator] No client for synthesis, returning raw results")
                return f"Task completed with {len(worker_results)} steps:\n\n{combined_results}"

            from ..core.llm_clients import GeminiClient
            client = GeminiClient(api_key=key, model_name=target_model)
            response_text = client.generate_content_rest(prompt) or ""
            return response_text.strip()

        except Exception as e:
            logger.error(f"[Orchestrator] Synthesis failed: {e}")
            return f"Task completed with {len(worker_results)} steps:\n\n{combined_results}"

    async def _deliberate_on_plan(self, goal: str, plan: dict) -> dict:
        """
        Multi-perspective deliberation on the execution plan before running.

        Analyzes the plan from 3 perspectives (Intent, Gaps, Flow) to catch
        issues like empty inputs, missing dependencies, or misunderstood intent.

        Returns:
            {"deliberation": str, "refined_understanding": str, "steps": [...]}
            or empty dict on failure
        """
        plan_json = json.dumps(plan, indent=2, ensure_ascii=False)

        prompt = f"""You are a council of three analysts reviewing an execution plan before it runs.

USER'S REQUEST: {goal}

CURRENT PLAN:
{plan_json}

Analyze from three perspectives:

## INTENT ANALYST
What does the user ACTUALLY want? What implicit requirements exist?
For example: "create a hello world script" means create a FILE WITH WORKING CODE, not an empty file.
"create X and Y" means create BOTH, not just one.

## GAP DETECTOR
Are any step inputs incomplete? Will any worker receive empty or insufficient data?
Check: Does the Shell worker have actual content to write, or is it relying on dependency_results?
If a step generates content (Dynamic/Code) that a later step needs, is the dependency declared?
Are file paths specific and valid?

## FLOW AUDITOR
Will data flow correctly between steps? Are depends_on declarations correct?
Will dependency_results provide the right data format for each downstream step?
Are steps ordered logically?

Then return ONLY valid JSON:
{{
  "deliberation": "Your complete multi-perspective analysis (2-3 paragraphs)",
  "refined_understanding": "One sentence: what the user actually wants, including implicit requirements",
  "steps": [<refined steps array - same structure as input, with enriched/corrected inputs>]
}}

CRITICAL RULES:
- If a step needs content from a previous step, ensure depends_on is set correctly
- Enrich vague inputs with specific details inferred from the user's intent
- If Shell write_file has empty content but depends on a code-generating step, that's OK (dependency_results will provide it)
- Do NOT add new steps unless absolutely necessary
- Do NOT remove steps the user explicitly requested
- Return ONLY the JSON, no markdown formatting"""

        try:
            api_key = None
            if self.key_rotator and self.key_rotator.keys:
                api_key, wait = self.key_rotator.get_next_key()
                if wait > 0:
                    await asyncio.sleep(wait)
                    api_key, _ = self.key_rotator.get_next_key()

            target_model = self.llm.settings.agent_mode_api_model or "gemini-3.1-flash-lite-preview"
            key = api_key or self.llm.settings.gemini_primary_key or self.llm.settings.gemini_fallback_key
            if not key:
                logger.warning("[Orchestrator] No API key for deliberation, skipping")
                return {}

            from ..core.llm_clients import GeminiClient
            client = GeminiClient(api_key=key, model_name=target_model)
            response_text = client.generate_content_rest(prompt) or ""

            # Clean markdown fences
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            result = json.loads(response_text)
            logger.info(f"[Orchestrator] Deliberation complete: {result.get('refined_understanding', '')[:100]}")
            return result

        except Exception as e:
            logger.warning(f"[Orchestrator] Deliberation failed (non-fatal): {e}")
            return {}

    async def _build_session_context(self, db: AsyncSession, session_id: int, current_execution_id: int) -> str:
        """
        Build context from previous executions in the same session.

        Returns a formatted string with goal summaries and results from
        the last 5 completed executions (excluding the current one).
        """
        try:
            stmt = (
                select(AgentExecution)
                .where(
                    AgentExecution.agent_session_id == session_id,
                    AgentExecution.id != current_execution_id,
                    AgentExecution.status == AgentExecutionStatus.COMPLETED,
                )
                .order_by(AgentExecution.created_at.desc())
                .limit(5)
            )
            result = await db.execute(stmt)
            past_executions = list(reversed(result.scalars().all()))

            if not past_executions:
                return ""

            lines = []
            for i, ex in enumerate(past_executions, 1):
                goal_short = (ex.goal or "")[:80]
                result_short = (ex.result or "")[:250]
                lines.append(f"Task {i}: {goal_short}")
                if result_short:
                    lines.append(f"  Result: {result_short}")
                lines.append("")

            return "\n".join(lines).strip()

        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to build session context: {e}")
            return ""

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (heuristic: 1 token ≈ 4 chars)."""
        return len(text) // 4 + 10

    async def _execute_workers_with_dependencies(
        self,
        db: AsyncSession,
        execution_id: int,
        steps: list,
        goal: str = "",
        event_log=None,
    ) -> list:
        """
        Execute workers with support for parallel execution, dependencies, and replanning.

        Features:
        - Topological sort for parallel execution by dependency level
        - Dynamic replanning when steps fail mid-execution (max 1 replan)
        - Context compaction for large dependency results
        - Event logging for real-time WebSocket streaming

        Args:
            db: Database session
            execution_id: Execution ID
            steps: List of step definitions from plan
            goal: Original user goal (used for replanning context)
            event_log: EventLog for streaming events to WebSocket

        Returns:
            List of worker results (in step order)
        """
        # Build dependency graph
        dependency_graph = self._build_dependency_graph(steps)

        # Track completed steps and their results
        completed_steps = {}
        results = [None] * len(steps)

        # Group steps by dependency level for parallel execution
        execution_levels = self._topological_sort(dependency_graph, len(steps))

        logger.info(f"[Orchestrator] Dependency graph: {len(execution_levels)} levels")

        replan_count = 0

        for level_idx, level_steps in enumerate(execution_levels):
            logger.info(f"[Orchestrator] Executing level {level_idx + 1}: {len(level_steps)} parallel tasks")

            # Execute all steps in this level in parallel
            tasks = []
            for step_idx in level_steps:
                step = steps[step_idx]
                task = self._execute_single_worker(
                    db, execution_id, step, step_idx, completed_steps,
                    event_log=event_log,
                )
                tasks.append(task)

            # Wait for all parallel tasks to complete
            level_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Store results
            for step_idx, result in zip(level_steps, level_results):
                if isinstance(result, Exception):
                    logger.error(f"[Orchestrator] Step {step_idx} failed: {result}")
                    results[step_idx] = {"error": str(result)}
                else:
                    results[step_idx] = result
                    completed_steps[step_idx] = result

            # ── Dynamic Replanning: check if failed steps require plan revision ──
            failed_in_level = [
                idx for idx in level_steps
                if isinstance(results[idx], dict) and "error" in results[idx]
            ]
            remaining_levels = execution_levels[level_idx + 1:]
            remaining_indices = [idx for level in remaining_levels for idx in level]

            if failed_in_level and remaining_indices and replan_count == 0:
                replan_count += 1
                logger.info(
                    f"[Orchestrator] Replanning: {len(failed_in_level)} failed steps, "
                    f"{len(remaining_indices)} remaining steps"
                )

                # Persist replan state to DB
                try:
                    stmt = select(AgentExecution).where(AgentExecution.id == execution_id)
                    exec_result = await db.execute(stmt)
                    execution_record = exec_result.scalar_one_or_none()
                    if execution_record:
                        execution_record.replan_count = replan_count
                        execution_record.original_plan = execution_record.plan
                        await db.commit()
                except Exception as e:
                    logger.warning(f"[Orchestrator] Failed to persist replan state: {e}")

                if event_log:
                    event_log.emit(EventType.REPLAN_TRIGGERED, {
                        "failed_steps": failed_in_level,
                        "remaining_steps": remaining_indices,
                    })

                new_plan = await self._replan_remaining_steps(
                    goal=goal,
                    steps=steps,
                    completed_results=completed_steps,
                    failed_indices=failed_in_level,
                    remaining_indices=remaining_indices,
                )

                if new_plan and new_plan.get("steps"):
                    logger.info(f"[Orchestrator] Replan generated {len(new_plan['steps'])} new steps")
                    if event_log:
                        event_log.emit(EventType.PLAN_REVISED, {
                            "new_steps_count": len(new_plan["steps"]),
                        })
                    # Execute new steps sequentially (simpler than rebuilding dependency graph)
                    for new_step in new_plan["steps"]:
                        new_idx = len(results)
                        new_result = await self._execute_single_worker(
                            db, execution_id, new_step, new_idx, completed_steps,
                            event_log=event_log,
                        )
                        results.append(new_result)
                        if not (isinstance(new_result, dict) and "error" in new_result):
                            completed_steps[new_idx] = new_result
                    break  # Exit original level loop — replanned steps replace remaining

        return results

    async def _replan_remaining_steps(
        self,
        goal: str,
        steps: list,
        completed_results: dict,
        failed_indices: list,
        remaining_indices: list,
    ) -> dict:
        """
        Generate a revised plan for remaining steps after failures.

        Scoped replanning: only revises the remaining work, keeping completed
        results as inputs. Max 1 replan per execution.
        """
        # Format completed results as summaries
        completed_summary = []
        for idx, result in sorted(completed_results.items()):
            step_desc = steps[idx].get("description", f"Step {idx}") if idx < len(steps) else f"Step {idx}"
            result_preview = json.dumps(result, ensure_ascii=False, default=str)[:200]
            completed_summary.append(f"  Step {idx} ({step_desc}): COMPLETED — {result_preview}")

        # Format failed steps
        failed_summary = []
        for idx in failed_indices:
            step_desc = steps[idx].get("description", f"Step {idx}") if idx < len(steps) else f"Step {idx}"
            error = json.dumps(steps[idx], ensure_ascii=False, default=str)[:150] if idx < len(steps) else "unknown"
            failed_summary.append(f"  Step {idx} ({step_desc}): FAILED")

        # Format remaining steps
        remaining_summary = []
        for idx in remaining_indices:
            if idx < len(steps):
                step = steps[idx]
                remaining_summary.append(f"  Step {idx}: {step.get('worker', '?')} — {step.get('description', '?')}")

        prompt = f"""A multi-step execution plan partially failed. Revise ONLY the remaining steps.

## Original Goal
{goal}

## Completed Successfully
{chr(10).join(completed_summary) if completed_summary else "  (none)"}

## Failed Steps
{chr(10).join(failed_summary) if failed_summary else "  (none)"}

## Remaining Steps (from original plan — may need revision)
{chr(10).join(remaining_summary) if remaining_summary else "  (none)"}

## Available Workers
{', '.join(self.workers.keys())}

Create a revised plan for ONLY the remaining work. Consider:
- What completed steps produced (use their results as context)
- Why steps failed (avoid repeating the same approach)
- Whether alternative workers could accomplish the failed steps' goals

Return JSON: {{"reasoning": "why this revised plan", "steps": [...]}}
Each step: {{"worker": str, "input": dict, "description": str}}
"""

        try:
            # Use the same planning infrastructure
            result = await self._plan_task_prompt_based(prompt, "LITE")
            return result
        except Exception as e:
            logger.error(f"[Orchestrator] Replanning failed: {e}")
            return {}

    async def _execute_workers_supervised(
        self,
        db: AsyncSession,
        execution_id: int,
        steps: list
    ) -> list:
        """
        Execute workers sequentially with per-step user approval.

        For each step:
        1. Creates a WorkerTask with status=awaiting_approval
        2. Polls DB every 1s waiting for status change to approved/failed
        3. On approved: executes the worker
        4. On failed (skipped): records skip and continues
        5. 5-minute timeout per step

        Args:
            db: Database session
            execution_id: Execution ID
            steps: List of step definitions from plan

        Returns:
            List of worker results (in step order)
        """
        results = []
        completed_steps = {}

        for step_idx, step in enumerate(steps):
            worker_type = step.get("worker", "Unknown")
            worker_input = step.get("input", {})
            description = step.get("description", "")

            logger.info(f"[Orchestrator] Supervised step {step_idx}: {worker_type} - awaiting approval")

            # Create worker task record in awaiting_approval state
            worker_task_record = AgentWorkerTask(
                execution_id=execution_id,
                worker_type=worker_type,
                model="pending",
                input_data={"description": description, "step_index": step_idx, **worker_input},
                status="awaiting_approval",
            )
            db.add(worker_task_record)
            await db.commit()
            await db.refresh(worker_task_record)

            task_id = worker_task_record.id

            # Poll DB for approval (timeout 5 minutes)
            approved = False
            skipped = False
            timeout_seconds = 300
            poll_interval = 1.0
            elapsed = 0.0

            while elapsed < timeout_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # Re-fetch task status from DB
                stmt = select(AgentWorkerTask).where(AgentWorkerTask.id == task_id)
                result = await db.execute(stmt)
                task_record = result.scalar_one_or_none()

                if not task_record:
                    logger.error(f"[Orchestrator] Worker task {task_id} disappeared")
                    skipped = True
                    break

                if task_record.status == "approved":
                    approved = True
                    break
                elif task_record.status == "failed":
                    skipped = True
                    break

            if not approved and not skipped:
                # Timeout
                logger.warning(f"[Orchestrator] Worker task {task_id} timed out after {timeout_seconds}s")
                worker_task_record.status = "failed"
                worker_task_record.error = "Timeout: sem resposta do usuário em 5 minutos"
                await db.commit()
                results.append({"error": "Timeout", "skipped": True})
                continue

            if skipped:
                logger.info(f"[Orchestrator] Worker task {task_id} skipped by user")
                results.append({"skipped": True, "worker": worker_type})
                continue

            # Approved — execute the worker
            logger.info(f"[Orchestrator] Worker task {task_id} approved, executing {worker_type}")
            try:
                result = await self._execute_single_worker(
                    db, execution_id, step, step_idx, completed_steps
                )
                results.append(result)
                completed_steps[step_idx] = result
            except Exception as e:
                logger.error(f"[Orchestrator] Supervised step {step_idx} failed: {e}")
                results.append({"error": str(e)})

        return results

    def _build_dependency_graph(self, steps: list) -> dict:
        """
        Build dependency graph from steps.

        Each step can specify dependencies via 'depends_on': [step_indices]

        Returns:
            Dict mapping step_idx -> list of dependency step_indices
        """
        graph = {}
        for i, step in enumerate(steps):
            depends_on = step.get("depends_on", [])
            # Convert to list if single int
            if isinstance(depends_on, int):
                depends_on = [depends_on]
            graph[i] = depends_on
        return graph

    def _topological_sort(self, graph: dict, num_steps: int) -> list:
        """
        Topological sort to determine execution levels.

        Returns:
            List of levels, where each level is a list of step indices that can run in parallel
        """
        completed = set()
        levels = []
        remaining = set(range(num_steps))

        while remaining:
            # Find nodes whose dependencies are all completed
            current_level = [
                i for i in remaining
                if all(dep in completed for dep in graph.get(i, []))
            ]

            if not current_level:
                # Circular dependency or error - execute remaining sequentially
                logger.warning("[Orchestrator] Circular dependency detected, executing remaining steps sequentially")
                current_level = list(remaining)

            levels.append(current_level)

            # Mark current level as completed
            for node in current_level:
                remaining.discard(node)
                completed.add(node)

        return levels

    # ── Per-worker timeouts (seconds) ──
    # ReAct-enabled workers get more time for iterative loops
    WORKER_TIMEOUTS = {
        "Code": 120.0,     # ReAct: generate → execute → fix cycles
        "Shell": 90.0,     # ReAct: read → write → verify cycles
        "Browser": 180.0,  # ReAct: navigate → click → screenshot cycles
        "Web": 60.0,       # ReAct: fetch → summarize (fewer iterations)
        "Search": 60.0,    # ReAct: search → refine (fewer iterations)
        "RAG": 30.0,       # One-shot: retrieval + synthesis
        "Memory": 30.0,    # One-shot: search + synthesis
        "Router": 30.0,    # One-shot: classification
        "Vision": 60.0,    # One-shot: image processing
        "Dynamic": 90.0,   # One-shot: freeform tasks
    }

    def _get_worker_timeout(self, worker_type: str) -> float:
        """Get timeout for a worker type, with default fallback."""
        return self.WORKER_TIMEOUTS.get(worker_type, 60.0)

    async def _execute_single_worker(
        self,
        db: AsyncSession,
        execution_id: int,
        step: dict,
        step_idx: int,
        completed_steps: dict,
        event_log=None,
    ) -> dict:
        """Execute a single worker with TPM+RPM management, context compaction, and event logging."""
        async with self._semaphore:  # Cap parallel workers
            worker_type = step.get("worker")
            worker_input = step.get("input", {})

            if worker_type not in self.workers:
                logger.warning(f"[Orchestrator] Worker {worker_type} not implemented, skipping step {step_idx}")
                return {"error": f"Worker {worker_type} not available"}

            logger.info(f"[Orchestrator] Executing step {step_idx}: {worker_type}")

            if event_log:
                event_log.emit(EventType.WORKER_STARTED, {
                    "description": step.get("description", ""),
                }, worker_type=worker_type, step_index=step_idx)

            # Inject results from dependencies if needed
            depends_on = step.get("depends_on", [])
            if depends_on:
                raw_deps = {
                    dep_idx: completed_steps.get(dep_idx)
                    for dep_idx in depends_on
                    if dep_idx in completed_steps
                }
                # Context engineering: compact large dependency results
                # to prevent context rot in downstream workers
                try:
                    llm_caller = self._make_compact_llm_caller()
                    worker_input["dependency_results"] = await self._context_manager.compact_dependency_results(
                        raw_deps, step.get("description", ""), llm_caller
                    )
                except Exception as e:
                    logger.warning(f"[Orchestrator] Dependency compaction failed, using raw: {e}")
                    worker_input["dependency_results"] = raw_deps

            # Dual rate limit check (TPM + RPM) before calling worker
            estimated_tokens = self._estimate_tokens(json.dumps(worker_input))
            wait_seconds = self.tpm.request_permission(estimated_tokens)
            if wait_seconds > 0:
                logger.warning(f"[Orchestrator] Rate limit hit, waiting {wait_seconds:.1f}s (step {step_idx})")
                if event_log:
                    event_log.emit(EventType.RATE_LIMIT_WAIT, {
                        "wait_seconds": wait_seconds,
                    }, worker_type=worker_type, step_index=step_idx)
                await asyncio.sleep(wait_seconds)
                # Re-check after waiting (another worker may have consumed quota)
                wait_seconds = self.tpm.request_permission(estimated_tokens)
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

            # Get rotated API key if key_rotator is available
            api_key = None
            if self.key_rotator and self.key_rotator.keys:
                api_key, key_wait = self.key_rotator.get_next_key()
                if key_wait > 0:
                    logger.info(f"[Orchestrator] Key rotation wait {key_wait:.1f}s (step {step_idx})")
                    await asyncio.sleep(key_wait)
                    api_key, _ = self.key_rotator.get_next_key()

            # Inject orchestrator-level params into worker input for _call_llm
            worker_input["_orchestrator_params"] = {
                "api_key": api_key,
                "thinking_budget": self._thinking_budget,
                "enable_thinking": self._enable_thinking,
            }

            # Execute worker with per-type timeout via self-correction-aware dispatch
            # Timeout scales with max self-corrections to allow retry attempts
            worker = self.workers[worker_type]
            base_timeout = self._get_worker_timeout(worker_type)
            correction_factor = 1 + getattr(worker, 'MAX_SELF_CORRECTIONS', 0)
            timeout = base_timeout * correction_factor if getattr(worker, 'ENABLE_EVALUATION', False) else base_timeout
            try:
                worker_task = await asyncio.wait_for(
                    worker.execute_with_correction(db, execution_id, worker_input),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"[Orchestrator] Worker {worker_type} timed out after {timeout}s (step {step_idx})")
                if event_log:
                    event_log.emit(EventType.WORKER_FAILED, {
                        "error": f"Timed out after {int(timeout)}s",
                    }, worker_type=worker_type, step_index=step_idx)
                return {"error": f"Worker {worker_type} timed out after {int(timeout)} seconds"}

            if worker_task.status == AgentTaskStatus.COMPLETED:
                result_data = worker_task.output_data or {}
                # Update TPM with actual tokens (replace estimated entry)
                actual_tokens = result_data.pop("_tokens_used", 0)
                if actual_tokens > 0 and estimated_tokens > 0:
                    self.tpm.update_actual_tokens(estimated_tokens, actual_tokens)

                if event_log:
                    event_log.emit(EventType.WORKER_COMPLETED, {
                        "tokens_used": actual_tokens,
                        "output_keys": list(result_data.keys())[:5],
                    }, worker_type=worker_type, step_index=step_idx)

                # Context engineering: compact output for downstream consumption
                try:
                    llm_caller = self._make_compact_llm_caller()
                    result_data = await self._context_manager.compact_output_for_downstream(
                        result_data, llm_caller
                    )
                except Exception as e:
                    logger.warning(f"[Orchestrator] Output compaction failed, using raw: {e}")

                return result_data
            else:
                logger.error(f"[Orchestrator] Worker {worker_type} failed: {worker_task.error}")
                if event_log:
                    event_log.emit(EventType.WORKER_FAILED, {
                        "error": (worker_task.error or "")[:200],
                    }, worker_type=worker_type, step_index=step_idx)
                return {"error": worker_task.error}

    def _make_compact_llm_caller(self):
        """
        Create a lightweight async LLM caller for context compaction.

        Uses the cheapest model (flash-lite) for summarization tasks.
        Returns an async callable(prompt: str) -> str.
        """
        async def _caller(prompt: str) -> str:
            api_key = None
            if self.key_rotator and self.key_rotator.keys:
                api_key, wait = self.key_rotator.get_next_key()
                if wait > 0:
                    await asyncio.sleep(wait)
                    api_key, _ = self.key_rotator.get_next_key()

            target_model = self.llm.settings.agent_mode_api_model or "gemini-3.1-flash-lite-preview"
            key = api_key or self.llm.settings.gemini_primary_key or self.llm.settings.gemini_fallback_key
            if not key:
                raise Exception("No API key for compaction")

            from ..core.llm_clients import GeminiClient
            client = GeminiClient(api_key=key, model_name=target_model)
            return client.generate_content_rest(prompt) or ""

        return _caller

    async def get_execution_status(
        self,
        db: AsyncSession,
        execution_id: int
    ) -> Optional[AgentExecution]:
        """
        Get execution status with worker tasks.

        Args:
            db: Database session
            execution_id: Execution ID

        Returns:
            AgentExecution with worker_tasks loaded, or None if not found
        """
        stmt = select(AgentExecution).where(AgentExecution.id == execution_id)
        result = await db.execute(stmt)
        execution = result.scalar_one_or_none()

        if execution:
            # Load worker tasks
            worker_stmt = select(AgentWorkerTask).where(
                AgentWorkerTask.execution_id == execution_id
            ).order_by(AgentWorkerTask.created_at)
            worker_result = await db.execute(worker_stmt)
            execution.worker_tasks = worker_result.scalars().all()

        return execution
