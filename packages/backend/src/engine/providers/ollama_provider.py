"""
Ollama provider for local models.
Supports: Qwen, Llama, Mistral, DeepSeek, etc.
"""
import json
import logging
from typing import Optional, AsyncGenerator

import httpx

from .base import LLMProvider
from ..types import LLMResponse, ToolCall, StopReason, ModelCapabilities
from ..errors import ProviderError

logger = logging.getLogger("ahri.engine.ollama")


class OllamaProvider(LLMProvider):
    """Ollama local model provider."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=300.0)  # Local models can be slow

    async def generate(
        self,
        messages: list[dict],
        model: str,
        api_key: str = "",  # Not used for Ollama
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        thinking_budget: int = 0,
        json_mode: bool = False,
    ) -> LLMResponse:
        url = f"{self.base_url}/api/chat"

        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if json_mode:
            body["format"] = "json"

        if tools:
            body["tools"] = self._format_ollama_tools(tools)

        try:
            response = await self._client.post(url, json=body)
            if response.status_code != 200:
                raise ProviderError(
                    f"Ollama error: {response.status_code} - {response.text}",
                    provider="ollama",
                    status_code=response.status_code,
                )

            data = response.json()
            return self._parse_response(data, model)

        except httpx.ConnectError:
            raise ProviderError(
                f"Cannot connect to Ollama at {self.base_url}. Is it running?",
                provider="ollama",
                retryable=False,
            )

    def _parse_response(self, data: dict, model: str) -> LLMResponse:
        message = data.get("message", {})
        content = message.get("content", "")

        tool_calls = []
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            tool_calls.append(ToolCall(
                tool_name=func.get("name", ""),
                arguments=func.get("arguments", {}),
            ))

        # Separate thinking from content (Qwen3 <think>...</think>)
        thinking = None
        if "<think>" in content:
            import re
            think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if think_match:
                thinking = think_match.group(1).strip()
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=StopReason.TOOL_USE if tool_calls else StopReason.END_TURN,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=model,
            thinking=thinking,
        )

    async def stream(
        self,
        messages: list[dict],
        model: str,
        api_key: str = "",
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/api/chat"

        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        async with self._client.stream("POST", url, json=body) as response:
            async for line in response.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            yield text
                    except json.JSONDecodeError:
                        continue

    def get_capabilities(self, model: str) -> ModelCapabilities:
        # Ollama doesn't expose this; use sensible defaults
        return ModelCapabilities(
            max_tokens=8192,
            supports_tools=True,
            supports_vision=False,
            supports_thinking=model.startswith("qwen"),
            supports_streaming=True,
            context_window=32768,
        )

    def _format_ollama_tools(self, tools: list[dict]) -> list[dict]:
        """Convert to Ollama tool format."""
        formatted = []
        for tool in tools:
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return formatted
