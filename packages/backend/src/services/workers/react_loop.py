"""
ReactLoop - Think → Act → Observe agent loop for worker execution.

Implements the ReAct (Reason + Act) pattern where an LLM iteratively:
1. Thinks about what to do next
2. Selects and calls a tool
3. Observes the result
4. Repeats until done or max iterations reached

Designed for small models (Gemini Flash Lite, Qwen 3 8B) with:
- Hard iteration caps to prevent infinite loops
- Schema-forced JSON decisions (no freeform parsing)
- Scratchpad compaction to manage context window
- Explicit tool enumeration to reduce hallucination
"""
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Awaitable, Optional

logger = logging.getLogger("ahri.react_loop")


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass
class ToolDefinition:
    """A tool available to the ReAct agent."""
    name: str
    description: str
    parameters: dict  # JSON schema for the tool's input
    handler: Callable[[dict], Awaitable["ToolResult"]]


@dataclass
class ToolResult:
    """Result of executing a tool."""
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None

    def truncate(self, max_chars: int = 4000) -> "ToolResult":
        """Truncate output to stay within token budget."""
        if len(self.output) > max_chars:
            self.output = self.output[:max_chars] + f"\n... [truncated, {len(self.output)} total chars]"
        return self


@dataclass
class ReactStep:
    """One iteration of the ReAct loop."""
    iteration: int
    thought: str
    action: str
    action_input: dict
    observation: str = ""
    duration_ms: int = 0
    compacted: bool = False  # True if this step was summarized

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReactResult:
    """Final result of the ReAct loop."""
    answer: str
    steps: list
    iterations: int
    total_tokens_estimated: int = 0
    forced_finish: bool = False  # True if max iterations reached

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "steps": [s.to_dict() if isinstance(s, ReactStep) else s for s in self.steps],
            "iterations": self.iterations,
            "total_tokens_estimated": self.total_tokens_estimated,
            "forced_finish": self.forced_finish,
        }


# ── Decision Schema ───────────────────────────────────────────────────

def build_decision_schema(tool_names: list[str]) -> dict:
    """
    JSON schema for the LLM's decision at each ReAct step.
    The model MUST return this shape — enforced by _call_llm(schema=...).
    """
    return {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "Your reasoning about what to do next"
            },
            "action": {
                "type": "string",
                "enum": tool_names + ["finish"],
                "description": "The tool to use, or 'finish' if done"
            },
            "action_input": {
                "type": "object",
                "description": "Input parameters for the chosen tool (empty {} if action is 'finish')"
            },
            "final_answer": {
                "type": "string",
                "description": "Your final answer (ONLY when action is 'finish')"
            }
        },
        "required": ["thought", "action"]
    }


# ── Main Loop ─────────────────────────────────────────────────────────

class ReactLoop:
    """
    ReAct agent loop engine.

    Usage:
        loop = ReactLoop(
            llm_caller=worker._call_llm,
            tools=worker.get_tools(),
            max_iterations=5,
            system_prompt=worker.ROLE_PROMPT,
        )
        result = await loop.run("Write and test a Python function", context={})
    """

    def __init__(
        self,
        llm_caller: Callable,
        tools: list[ToolDefinition],
        max_iterations: int = 5,
        token_budget_per_step: int = 4000,
        system_prompt: str = "",
        compact_after: int = 3,
    ):
        self.llm_caller = llm_caller
        self.tools = {t.name: t for t in tools}
        self.max_iterations = max_iterations
        self.token_budget_per_step = token_budget_per_step
        self.system_prompt = system_prompt
        self.compact_after = compact_after

        self._tool_names = [t.name for t in tools]
        self._decision_schema = build_decision_schema(self._tool_names)
        self._total_tokens = 0

    async def run(self, task: str, context: Optional[dict] = None) -> ReactResult:
        """
        Execute the ReAct loop.

        Args:
            task: The task description for the agent
            context: Optional context dict (dependency_results, reflexion_notes, etc.)

        Returns:
            ReactResult with the final answer and step history
        """
        scratchpad: list[ReactStep] = []
        context = context or {}

        for i in range(self.max_iterations):
            # Build prompt with current scratchpad
            prompt = self._build_prompt(task, context, scratchpad)
            self._total_tokens += len(prompt) // 4

            # Get LLM decision (schema-enforced JSON)
            try:
                decision = await self.llm_caller(
                    prompt=prompt,
                    schema=self._decision_schema,
                )
            except Exception as e:
                logger.error(f"[ReactLoop] LLM decision failed at step {i}: {e}")
                return self._force_finish(scratchpad, f"LLM error: {e}")

            thought = decision.get("thought", "")
            action = decision.get("action", "finish")
            action_input = decision.get("action_input", {})
            final_answer = decision.get("final_answer", "")

            logger.info(f"[ReactLoop] Step {i}: thought='{thought[:80]}...' action={action}")

            # ── Finish ──
            if action == "finish":
                return ReactResult(
                    answer=final_answer or thought,
                    steps=[s.to_dict() for s in scratchpad],
                    iterations=i + 1,
                    total_tokens_estimated=self._total_tokens,
                    forced_finish=False,
                )

            # ── Execute tool ──
            step_start = time.time()
            tool_result = await self._execute_tool(action, action_input)
            step_duration = int((time.time() - step_start) * 1000)

            step = ReactStep(
                iteration=i,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=tool_result.output if tool_result.success else f"ERROR: {tool_result.error}",
                duration_ms=step_duration,
            )
            scratchpad.append(step)
            self._total_tokens += len(step.observation) // 4

            # ── Compact scratchpad if growing too large ──
            if len(scratchpad) > self.compact_after:
                scratchpad = self._compact_scratchpad(scratchpad)

        # Max iterations reached — force finish
        logger.warning(f"[ReactLoop] Max iterations ({self.max_iterations}) reached, forcing finish")
        return self._force_finish(scratchpad)

    async def _execute_tool(self, action: str, action_input: dict) -> ToolResult:
        """Execute a tool by name, with validation."""
        if action not in self.tools:
            available = ", ".join(self._tool_names)
            return ToolResult(
                tool_name=action,
                success=False,
                output="",
                error=f"Unknown tool '{action}'. Available tools: {available}"
            )

        tool = self.tools[action]
        try:
            result = await tool.handler(action_input)
            return result.truncate(self.token_budget_per_step)
        except Exception as e:
            logger.error(f"[ReactLoop] Tool '{action}' raised exception: {e}")
            return ToolResult(
                tool_name=action,
                success=False,
                output="",
                error=str(e)
            )

    def _build_prompt(
        self, task: str, context: dict, scratchpad: list[ReactStep]
    ) -> str:
        """Build the prompt for the next ReAct decision."""
        parts = []

        # System context
        if self.system_prompt:
            parts.append(self.system_prompt)

        # Task
        parts.append(f"\n## Task\n{task}")

        # Additional context (dependency results, reflexion notes)
        if context.get("dependency_results"):
            dep_str = json.dumps(context["dependency_results"], ensure_ascii=False, default=str)
            if len(dep_str) > 2000:
                dep_str = dep_str[:2000] + "... [truncated]"
            parts.append(f"\n## Context from previous steps\n{dep_str}")

        if context.get("_reflexion_notes"):
            notes = context["_reflexion_notes"]
            notes_str = "\n".join(
                f"- Attempt {n.get('attempt', '?')}: {n.get('what_happened', '')} → Fix: {n.get('what_to_change', '')}"
                for n in notes
            )
            parts.append(f"\n## Previous attempts failed\n{notes_str}\nAvoid repeating these mistakes.")

        # Available tools
        tool_list = "\n".join(
            f"- **{name}**: {tool.description}"
            for name, tool in self.tools.items()
        )
        parts.append(f"\n## Available Tools\n{tool_list}\n- **finish**: Return your final answer")

        # Scratchpad (previous steps)
        if scratchpad:
            steps_str = []
            for step in scratchpad:
                if step.compacted:
                    steps_str.append(f"[Steps summary]: {step.observation}")
                else:
                    obs_preview = step.observation[:500] if len(step.observation) > 500 else step.observation
                    steps_str.append(
                        f"Step {step.iteration}:\n"
                        f"  Thought: {step.thought}\n"
                        f"  Action: {step.action}({json.dumps(step.action_input, ensure_ascii=False, default=str)[:200]})\n"
                        f"  Observation: {obs_preview}"
                    )
            parts.append(f"\n## Previous Steps\n" + "\n\n".join(steps_str))

        # Instructions
        parts.append(
            "\n## Instructions\n"
            "Decide what to do next. You MUST respond with a JSON object:\n"
            '{"thought": "your reasoning", "action": "tool_name or finish", '
            '"action_input": {...}, "final_answer": "only if action is finish"}\n\n'
            "If you have enough information to complete the task, use action='finish'.\n"
            "Do NOT repeat the same action with the same input."
        )

        return "\n".join(parts)

    def _compact_scratchpad(self, scratchpad: list[ReactStep]) -> list[ReactStep]:
        """
        Compact early steps to prevent context rot.
        Keeps the last 2 steps intact, summarizes earlier ones.
        """
        if len(scratchpad) <= 2:
            return scratchpad

        # Summarize all but the last 2 steps
        early_steps = scratchpad[:-2]
        recent_steps = scratchpad[-2:]

        summary_parts = []
        for step in early_steps:
            if step.compacted:
                summary_parts.append(step.observation)
            else:
                result_preview = step.observation[:100] if step.observation else "no output"
                summary_parts.append(
                    f"Step {step.iteration}: Used {step.action} → {result_preview}"
                )

        summary = ReactStep(
            iteration=-1,
            thought="[compacted]",
            action="[compacted]",
            action_input={},
            observation="; ".join(summary_parts),
            compacted=True,
        )

        return [summary] + recent_steps

    def _force_finish(self, scratchpad: list[ReactStep], error: str = "") -> ReactResult:
        """Force a finish when max iterations reached or on error."""
        # Build answer from scratchpad observations
        observations = []
        for step in scratchpad:
            if not step.compacted and step.observation:
                observations.append(step.observation[:300])

        answer = error if error else (
            "Task reached maximum iterations. "
            "Here is what was accomplished:\n" +
            "\n".join(f"- {obs}" for obs in observations[-3:])  # Last 3 observations
        )

        return ReactResult(
            answer=answer,
            steps=[s.to_dict() for s in scratchpad],
            iterations=len(scratchpad),
            total_tokens_estimated=self._total_tokens,
            forced_finish=True,
        )
