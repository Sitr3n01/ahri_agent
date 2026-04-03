"""
WorkerContextManager - Context engineering for agent executions.

Manages context window size across the execution pipeline:
1. Compacts large dependency results before passing to downstream workers
2. Compacts worker outputs for downstream consumption
3. Follows Anthropic's recommendation: subagents return 1-2K token summaries

This prevents context rot — as token count increases, LLM recall accuracy
decreases due to n² attention relationships spreading the model thin.
"""
import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("ahri.context_manager")

# Token thresholds (estimated: 1 token ≈ 4 chars)
DEPENDENCY_TOTAL_THRESHOLD = 4000   # Compact if total dep results > this many tokens
SINGLE_RESULT_THRESHOLD = 500       # Compact individual results > this many tokens
OUTPUT_COMPACT_THRESHOLD = 1000     # Compact output for downstream if > this many tokens
MAX_COMPACTED_TOKENS = 500          # Target size after compaction


def _estimate_tokens(text: str) -> int:
    """Estimate token count (heuristic: 1 token ≈ 4 chars)."""
    return len(text) // 4 + 5


class WorkerContextManager:
    """
    Manages context size for dependency results and worker outputs.

    Used by the orchestrator between worker executions to keep context
    within manageable bounds for small models.
    """

    async def compact_dependency_results(
        self,
        dependency_results: dict,
        task_description: str,
        llm_caller: Callable,
    ) -> dict:
        """
        Compact large dependency results before passing to a downstream worker.

        If total estimated tokens of all results exceeds DEPENDENCY_TOTAL_THRESHOLD,
        summarizes each result that exceeds SINGLE_RESULT_THRESHOLD into a concise
        summary relevant to the current task. Small results pass through unchanged.

        Args:
            dependency_results: Dict mapping step_idx -> output_data
            task_description: The downstream worker's task (for relevance filtering)
            llm_caller: Async callable for LLM summarization

        Returns:
            Compacted dependency_results dict
        """
        if not dependency_results:
            return dependency_results

        # Estimate total tokens
        total_text = json.dumps(dependency_results, ensure_ascii=False, default=str)
        total_tokens = _estimate_tokens(total_text)

        if total_tokens <= DEPENDENCY_TOTAL_THRESHOLD:
            return dependency_results  # Small enough, pass through

        logger.info(
            f"[ContextManager] Compacting dependency results: "
            f"~{total_tokens} tokens > {DEPENDENCY_TOTAL_THRESHOLD} threshold"
        )

        compacted = {}
        for step_idx, result_data in dependency_results.items():
            result_text = json.dumps(result_data, ensure_ascii=False, default=str)
            result_tokens = _estimate_tokens(result_text)

            if result_tokens <= SINGLE_RESULT_THRESHOLD:
                compacted[step_idx] = result_data  # Small, keep as-is
                continue

            # Large result — summarize with LLM
            try:
                summary = await self._summarize_for_downstream(
                    result_data, task_description, llm_caller
                )
                compacted[step_idx] = {"_compacted_summary": summary}
                logger.info(
                    f"[ContextManager] Step {step_idx}: {result_tokens} tokens → "
                    f"~{_estimate_tokens(summary)} tokens"
                )
            except Exception as e:
                # On failure, truncate instead
                logger.warning(f"[ContextManager] Compaction failed for step {step_idx}: {e}")
                compacted[step_idx] = self._truncate_result(result_data)

        return compacted

    async def compact_output_for_downstream(
        self,
        output_data: dict,
        llm_caller: Callable,
    ) -> dict:
        """
        Compact a worker's output for downstream steps.

        Following Anthropic's recommendation: subagents should return
        condensed summaries (1-2K tokens) regardless of how much they explored.

        Args:
            output_data: The worker's output dict
            llm_caller: Async callable for LLM summarization

        Returns:
            Compacted output dict (or original if small enough)
        """
        if not output_data:
            return output_data

        output_text = json.dumps(output_data, ensure_ascii=False, default=str)
        output_tokens = _estimate_tokens(output_text)

        if output_tokens <= OUTPUT_COMPACT_THRESHOLD:
            return output_data  # Small enough

        logger.info(
            f"[ContextManager] Compacting output: "
            f"~{output_tokens} tokens > {OUTPUT_COMPACT_THRESHOLD} threshold"
        )

        try:
            prompt = (
                f"Summarize this worker output, preserving all key data, code snippets, "
                f"numerical values, and important findings. Be concise but complete.\n\n"
                f"Output to summarize:\n{output_text[:3000]}\n\n"
                f"Return a concise summary (max 500 words) that preserves all actionable information."
            )

            summary = await llm_caller(prompt=prompt)

            return {
                "_compacted_summary": summary,
                "_original_keys": list(output_data.keys()),
            }
        except Exception as e:
            logger.warning(f"[ContextManager] Output compaction failed: {e}")
            return self._truncate_result(output_data)

    async def _summarize_for_downstream(
        self,
        result_data: dict,
        task_description: str,
        llm_caller: Callable,
    ) -> str:
        """Summarize a result, focusing on information relevant to the downstream task."""
        result_text = json.dumps(result_data, ensure_ascii=False, default=str)
        if len(result_text) > 3000:
            result_text = result_text[:3000] + "..."

        prompt = (
            f"Summarize this data for the following downstream task: {task_description[:200]}\n\n"
            f"Data:\n{result_text}\n\n"
            f"Keep only information relevant to the downstream task. "
            f"Preserve code, numbers, URLs, and key facts. Max 300 words."
        )

        return await llm_caller(prompt=prompt)

    def _truncate_result(self, data: dict, max_chars: int = 2000) -> dict:
        """Fallback: truncate result when LLM compaction fails."""
        truncated = {}
        budget = max_chars

        for key, value in data.items():
            if key.startswith("_"):
                continue  # Skip internal keys

            value_str = json.dumps(value, ensure_ascii=False, default=str)
            if len(value_str) <= budget:
                truncated[key] = value
                budget -= len(value_str)
            else:
                # Truncate this value
                if isinstance(value, str) and len(value) > budget:
                    truncated[key] = value[:budget] + "... [truncated]"
                elif isinstance(value, list) and len(value) > 5:
                    truncated[key] = value[:5]  # Keep first 5 items
                else:
                    truncated[key] = value
                break

        truncated["_truncated"] = True
        return truncated
