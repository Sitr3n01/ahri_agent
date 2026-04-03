"""
Compaction Service - Summarizes older messages to reduce context window usage.

When a chat session exceeds THRESHOLD messages, the oldest messages (beyond
RECENT_WINDOW) are summarized into a compact paragraph using flash-lite.
The summary is stored on the ChatSession row and injected into the system prompt.
"""
import logging
from typing import Optional

from src.core.llm_clients import GeminiClient
from src.config import get_settings

logger = logging.getLogger("ahri.compaction")


class CompactionService:
    """Compacts chat history by summarizing older messages."""

    def __init__(self):
        self.settings = get_settings()

    def should_compact(self, history: list[dict]) -> bool:
        """Check if history exceeds compaction threshold."""
        return len(history) > self.settings.compaction_threshold

    def compact_history(
        self,
        history: list[dict],
        existing_summary: str = "",
    ) -> tuple[str, list[dict]]:
        """
        Summarize older messages and return (new_summary, recent_messages).

        Args:
            history: Full message list from session
            existing_summary: Previous compaction summary (if any)

        Returns:
            (summary_text, recent_messages_only)
        """
        window = self.settings.compaction_recent_window
        if len(history) <= window:
            return existing_summary, history

        # Split: older messages to summarize vs recent to keep
        older = history[:-window]
        recent = history[-window:]

        # Build text from older messages
        older_text = self._format_messages(older)

        # Include existing summary for continuity
        context = ""
        if existing_summary:
            context = f"Resumo anterior da conversa:\n{existing_summary}\n\n"

        prompt = f"""{context}Resuma de forma concisa a seguinte conversa entre usuario e assistente.
Mantenha: fatos importantes, decisoes tomadas, nomes mencionados, topicos discutidos, e o tom emocional.
Omita: saudacoes triviais, repetições, e detalhes irrelevantes.
Maximo 300 palavras. Responda em portugues.

Conversa:
{older_text}"""

        try:
            key = self.settings.memory_key or self.settings.gemini_fallback_key
            if not key:
                logger.warning("No API key for compaction, skipping")
                return existing_summary, history

            target_model = getattr(self.settings, "google_model_lite", "gemini-3.1-flash-lite-preview")
            client = GeminiClient(api_key=key, model_name=target_model)
            summary = client.generate_content_rest(prompt, temperature=0.3)

            if summary:
                logger.info(f"Compacted {len(older)} messages into summary ({len(summary)} chars)")
                return summary.strip(), recent
            else:
                logger.warning("Compaction returned empty, keeping full history")
                return existing_summary, history

        except Exception as e:
            logger.error(f"Compaction failed: {e}")
            return existing_summary, history

    def _format_messages(self, messages: list[dict]) -> str:
        """Format messages into readable text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."
            label = "User" if role == "user" else "AI"
            lines.append(f"{label}: {content}")
        return "\n".join(lines)
