"""
OpenRouter provider for DeepSeek, Claude, etc.
Uses OpenAI-compatible API format.
"""
import json
import logging
from typing import Optional, AsyncGenerator

import httpx

from .base import LLMProvider
from ..types import LLMResponse, ToolCall, StopReason, ModelCapabilities
from ..errors import ProviderError, RateLimitError

logger = logging.getLogger("ahri.engine.openrouter")


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider (OpenAI-compatible API)."""

    provider_name = "openrouter"

    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            timeout=120.0,
        )

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
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            body["response_format"] = {"type": "json_object"}

        if tools:
            body["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        try:
            response = await self._client.post("/chat/completions", headers=headers, json=body)

            if response.status_code == 429:
                raise RateLimitError("OpenRouter rate limit", provider="openrouter")

            if response.status_code != 200:
                raise ProviderError(
                    f"OpenRouter error: {response.status_code}",
                    provider="openrouter",
                    status_code=response.status_code,
                )

            data = response.json()
            return self._parse_response(data, model)

        except httpx.ConnectError as e:
            raise ProviderError(f"OpenRouter connection error: {e}", provider="openrouter")

    def _parse_response(self, data: dict, model: str) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls = []
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCall(tool_name=func.get("name", ""), arguments=args))

        usage = data.get("usage", {})
        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=tool_calls,
            stop_reason=StopReason.TOOL_USE if tool_calls else StopReason.END_TURN,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=model,
        )

    async def stream(self, messages, model, api_key, tools=None, temperature=0.7, max_tokens=8192):
        # OpenRouter SSE streaming (standard OpenAI format)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with self._client.stream("POST", "/chat/completions", headers=headers, json=body) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            max_tokens=8192,
            supports_tools=True,
            context_window=128000,
        )
