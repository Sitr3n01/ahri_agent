"""
Google Gemini provider.
Supports: Gemini 2.5 Pro/Flash, Gemini 3.1 Flash Lite, Gemma models.
Uses REST API directly for thread-safety (no global genai.configure).
"""
import asyncio
import json
import logging
from typing import Optional, AsyncGenerator

import httpx

from .base import LLMProvider
from ..types import LLMResponse, ToolCall, StopReason, ModelCapabilities
from ..errors import ProviderError, RateLimitError, ContextWindowError

logger = logging.getLogger("ahri.engine.gemini")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Model capabilities registry
GEMINI_MODELS = {
    "gemini-2.5-pro-preview": ModelCapabilities(
        max_tokens=65536, supports_tools=True, supports_vision=True,
        supports_thinking=True, supports_streaming=True,
        context_window=1048576, cost_per_1k_input=0.00125,
    ),
    "gemini-2.5-flash": ModelCapabilities(
        max_tokens=65536, supports_tools=True, supports_vision=True,
        supports_thinking=True, supports_streaming=True,
        context_window=1048576, cost_per_1k_input=0.000075,
    ),
    "gemini-3.1-flash-lite-preview": ModelCapabilities(
        max_tokens=8192, supports_tools=True, supports_vision=False,
        supports_thinking=False, supports_streaming=True,
        context_window=262144, cost_per_1k_input=0.0,
    ),
}


class GeminiProvider(LLMProvider):
    """Google Gemini provider using REST API."""

    provider_name = "gemini"

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=120.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
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
        url = f"{GEMINI_API_BASE}/models/{model}:generateContent?key={api_key}"

        # Extract system messages for systemInstruction (Gemini doesn't support system role in contents)
        system_parts = []
        non_system_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", ""))
            else:
                non_system_messages.append(msg)

        body = {
            "contents": self.format_messages(non_system_messages),
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        # Send system prompt as systemInstruction (Gemini's dedicated field)
        if system_parts:
            body["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }

        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        if thinking_budget > 0:
            body["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": thinking_budget
            }

        if tools:
            body["tools"] = [{"functionDeclarations": self.format_tools(tools)}]

        try:
            response = await self._client.post(url, json=body)

            if response.status_code == 429:
                raise RateLimitError(
                    "Gemini rate limit exceeded",
                    provider="gemini",
                    retry_after=60,
                )

            if response.status_code != 200:
                raise ProviderError(
                    f"Gemini API error: {response.status_code} - {response.text}",
                    provider="gemini",
                    status_code=response.status_code,
                )

            data = response.json()
            return self._parse_response(data, model)

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            raise ProviderError(
                f"Gemini connection error: {e}",
                provider="gemini",
                retryable=True,
            )

    def _parse_response(self, data: dict, model: str) -> LLMResponse:
        """Parse Gemini API response into LLMResponse."""
        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(content="", model=model, stop_reason=StopReason.ERROR)

        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts", [])

        content = ""
        thinking = ""
        tool_calls = []

        for part in parts:
            if "text" in part:
                content += part["text"]
            elif "thought" in part:
                thinking += part["thought"]
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(ToolCall(
                    tool_name=fc["name"],
                    arguments=fc.get("args", {}),
                ))

        # Parse token usage
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        # Determine stop reason
        finish_reason = candidate.get("finishReason", "STOP")
        if tool_calls:
            stop_reason = StopReason.TOOL_USE
        elif finish_reason == "MAX_TOKENS":
            stop_reason = StopReason.MAX_TOKENS
        else:
            stop_reason = StopReason.END_TURN

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            thinking=thinking or None,
            raw_response=data,
        )

    async def stream(
        self,
        messages: list[dict],
        model: str,
        api_key: str,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> AsyncGenerator[str, None]:
        url = f"{GEMINI_API_BASE}/models/{model}:streamGenerateContent?key={api_key}&alt=sse"

        body = {
            "contents": self.format_messages(messages),
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if tools:
            body["tools"] = [{"functionDeclarations": self.format_tools(tools)}]

        async with self._client.stream("POST", url, json=body) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part:
                                yield part["text"]
                    except (json.JSONDecodeError, IndexError):
                        continue

    def get_capabilities(self, model: str) -> ModelCapabilities:
        return GEMINI_MODELS.get(model, ModelCapabilities())

    def format_messages(self, messages: list[dict]) -> list[dict]:
        """Convert to Gemini format: role=user/model, parts=[{text:...}].

        Handles:
        - system → skipped (sent via systemInstruction upstream)
        - assistant with tool_calls → model + functionCall parts
        - tool_result → function + functionResponse part
        - user/model → standard text parts
        """
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")

            # System messages should have been extracted upstream;
            # skip as safety fallback
            if role == "system":
                continue

            # Assistant → "model" in Gemini format
            if role == "assistant":
                role = "model"

            # Tool result → function response
            if role == "tool_result":
                formatted.append({
                    "role": "function",
                    "parts": [{"functionResponse": {
                        "name": msg.get("tool_name", "unknown"),
                        "response": {"result": msg.get("content", "")},
                    }}],
                })
                continue

            # Build parts for this message
            parts = []

            # Add text content if present
            content = msg.get("content", "")
            if content:
                parts.append({"text": content})

            # Add functionCall parts for assistant/model messages with tool_calls
            tool_calls = msg.get("tool_calls", [])
            if tool_calls and role == "model":
                for tc in tool_calls:
                    parts.append({"functionCall": {
                        "name": tc.get("name", tc.get("tool_name", "")),
                        "args": tc.get("arguments", tc.get("args", {})),
                    }})

            # Ensure at least one part (Gemini requires non-empty parts)
            if not parts:
                parts.append({"text": ""})

            formatted.append({
                "role": role,
                "parts": parts,
            })
        return formatted

    def format_tools(self, tools: list[dict]) -> list[dict]:
        """Convert tool defs to Gemini function declarations."""
        declarations = []
        for tool in tools:
            decl = {
                "name": tool["name"],
                "description": tool.get("description", ""),
            }
            if "parameters" in tool:
                decl["parameters"] = tool["parameters"]
            declarations.append(decl)
        return declarations
