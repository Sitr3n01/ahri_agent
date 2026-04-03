"""
Context window compaction manager.

Strategies:
1. Summarize: Use cheapest model to summarize middle messages
2. Snip: Trim large tool outputs to their first/last N lines
3. Drop: Remove old tool results, keep only summaries

Inspired by Claude Code's compact/ directory.
"""
import logging
from typing import Optional

from ..types import Message, Role
from ..model_registry import ModelRegistry

logger = logging.getLogger("ahri.engine.compact")

# Max characters for a single tool result before snipping
SNIP_THRESHOLD = 5000
SNIP_KEEP_LINES = 20  # Keep first and last N lines


class CompactManager:
    """Manages context window compaction."""

    def __init__(
        self,
        model_registry: ModelRegistry,
        compact_model: str = "lite",
        threshold: float = 0.80,
        keep_recent: int = 4,
    ):
        self.model_registry = model_registry
        self.compact_model = compact_model
        self.threshold = threshold
        self.keep_recent = keep_recent

    async def compact(
        self,
        messages: list[Message],
        keep_recent: Optional[int] = None,
    ) -> list[Message]:
        """
        Compact message history to reduce token count.

        Strategy:
        1. Snip large tool outputs
        2. Summarize middle messages using cheapest model
        3. Keep first message (user goal) + last N messages
        """
        keep = keep_recent or self.keep_recent

        if len(messages) <= keep + 1:
            return messages  # Nothing to compact

        # Step 1: Snip large tool outputs
        messages = self._snip_large_outputs(messages)

        # Step 2: Separate messages
        first_msg = messages[0]
        middle = messages[1:-keep]
        recent = messages[-keep:]

        if not middle:
            return messages

        # Step 3: Summarize middle messages
        summary = await self._summarize(middle)

        # Reconstruct
        summary_msg = Message(
            role=Role.USER,
            content=f"[Conversation summary - {len(middle)} messages compacted]\n{summary}",
        )

        compacted = [first_msg, summary_msg] + recent
        logger.info(
            f"Compacted {len(messages)} → {len(compacted)} messages "
            f"({len(middle)} summarized)"
        )
        return compacted

    def _snip_large_outputs(self, messages: list[Message]) -> list[Message]:
        """Snip tool outputs that are too large."""
        result = []
        for msg in messages:
            if msg.role == Role.TOOL_RESULT and len(msg.content) > SNIP_THRESHOLD:
                lines = msg.content.split("\n")
                if len(lines) > SNIP_KEEP_LINES * 2:
                    kept = lines[:SNIP_KEEP_LINES] + [
                        f"\n... ({len(lines) - SNIP_KEEP_LINES * 2} lines snipped) ...\n"
                    ] + lines[-SNIP_KEEP_LINES:]
                    msg = Message(
                        role=msg.role,
                        content="\n".join(kept),
                        tool_results=msg.tool_results,
                        metadata=msg.metadata,
                    )
            result.append(msg)
        return result

    async def _summarize(self, messages: list[Message]) -> str:
        """Summarize a list of messages using the cheapest model."""
        # Build content for summarization
        content_parts = []
        for msg in messages:
            prefix = msg.role.value.upper()
            if msg.metadata.get("tool_name"):
                prefix = f"TOOL[{msg.metadata['tool_name']}]"
            content_parts.append(f"{prefix}: {msg.content[:1000]}")

        content = "\n---\n".join(content_parts)

        prompt = f"""Summarize the following conversation exchanges concisely.
Focus on: key decisions, tool results, important findings, and errors.
Keep the summary under 500 words.

{content}"""

        try:
            response = await self.model_registry.call(
                model_or_alias=self.compact_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
            )
            return response.content
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback: simple truncation
            return f"[{len(messages)} messages occurred - summarization failed]"

    def should_compact(self, total_tokens: int, context_window: int) -> bool:
        """Check if compaction should be triggered."""
        if context_window == 0:
            return False
        return (total_tokens / context_window) > self.threshold
