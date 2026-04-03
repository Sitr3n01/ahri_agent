"""
Abstract LLM provider.
Each provider handles one backend (Gemini, Ollama, OpenRouter).
Thread-safe: each call creates its own client context.
"""
from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator
from ..types import LLMResponse, ToolCall, ModelCapabilities


class LLMProvider(ABC):
    """
    Abstract base for LLM providers.
    Implementations must be stateless and thread-safe.
    """

    provider_name: str = ""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        thinking_budget: int = 0,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Generate a response from the LLM.

        Args:
            messages: Conversation history in provider format
            model: Model ID (e.g., "gemini-2.5-flash")
            api_key: API key for this request
            tools: Tool definitions for function calling
            temperature: Sampling temperature
            max_tokens: Max output tokens
            thinking_budget: Tokens for thinking (0 = disabled)
            json_mode: Force JSON output

        Returns:
            LLMResponse with content and/or tool_calls
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncGenerator[str, None]:
        """Stream text chunks from the LLM."""
        ...

    @abstractmethod
    def get_capabilities(self, model: str) -> ModelCapabilities:
        """Return capabilities for a specific model."""
        ...

    def format_messages(self, messages: list[dict]) -> list[dict]:
        """
        Convert from engine Message format to provider-specific format.
        Override in subclasses if needed.
        """
        return messages

    def format_tools(self, tools: list[dict]) -> list[dict]:
        """
        Convert tool definitions to provider's function calling format.
        Override in subclasses.
        """
        return tools
