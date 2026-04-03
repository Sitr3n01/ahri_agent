"""
Dynamic Worker - Executes tasks with orchestrator-generated system prompts.

Used for specialized tasks that don't fit existing worker types.
The orchestrator generates a detailed system_prompt during planning that
defines the agent's role, expertise, and output expectations.

This enables the orchestrator to create ad-hoc specialized agents on the fly,
without needing a pre-built worker for every possible task type.
"""
import json
import time
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker


class DynamicWorker(BaseWorker):
    """
    Dynamic Worker - Generic LLM executor with custom system prompts.

    The orchestrator creates the system_prompt during task planning,
    allowing it to spawn specialized agents for any domain or task type.
    """

    # Intentionally empty — the system_prompt from input_data replaces this
    ROLE_PROMPT = ""

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Dynamic",
            default_model="LITE"
        )

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Execute a task with a custom system prompt.

        Input format:
        {
            "system_prompt": str,       # Detailed role + expertise + instructions
            "task": str,                # The specific task to execute
            "output_format": "text|json|code",  # Expected output type
            "context": dict,            # Optional additional context data
            "_orchestrator_params": {   # Injected by orchestrator
                "api_key": str,
                "thinking_budget": int,
                "enable_thinking": bool
            }
        }
        """
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            system_prompt = input_data.get("system_prompt", "")
            task_description = input_data.get("task", "")
            output_format = input_data.get("output_format", "text")
            context = input_data.get("context", {})

            if not system_prompt or not task_description:
                return await self._fail_task(
                    db, task,
                    "Missing required fields: system_prompt and task are required",
                    start_time
                )

            # Extract orchestrator params (API key rotation, thinking budget)
            orch_params = input_data.get("_orchestrator_params", {})
            api_key = orch_params.get("api_key")
            thinking_budget = orch_params.get("thinking_budget", 0)
            enable_thinking = orch_params.get("enable_thinking", False)

            # Build the complete prompt
            prompt_parts = [system_prompt, ""]

            # Inject context if provided
            if context:
                prompt_parts.append(f"Context:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n")

            # Inject dependency results from previous steps
            dep_results = input_data.get("dependency_results", {})
            if dep_results:
                prompt_parts.append("Results from previous steps:")
                for step_idx, result in dep_results.items():
                    prompt_parts.append(f"  Step {step_idx}: {json.dumps(result, indent=2, ensure_ascii=False)}")
                prompt_parts.append("")

            # Add the task
            prompt_parts.append(f"Task: {task_description}")

            # Add output format instructions
            if output_format == "json":
                prompt_parts.append("\nReturn your response as valid JSON only, no markdown formatting.")
            elif output_format == "code":
                prompt_parts.append("\nReturn only the code, no explanations or markdown fences.")

            prompt = "\n".join(prompt_parts)

            # Call LLM via BaseWorker (thread-safe, with retries)
            response = await self._call_llm(
                prompt=prompt,
                api_key=api_key,
                thinking_budget=thinking_budget,
                enable_thinking=enable_thinking,
            )

            output = {
                "result": response,
                "output_format": output_format,
                "system_prompt_summary": system_prompt[:200] + ("..." if len(system_prompt) > 200 else ""),
            }

            tokens = self._estimate_tokens(prompt + str(response))
            return await self._complete_task(db, task, output, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)
