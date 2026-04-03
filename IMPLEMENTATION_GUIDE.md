# Ahri V4 Engine - Guia de Implementação Completo

> **Para:** Gemini (implementador)
> **De:** Análise arquitetural do Claude Code (Anthropic)
> **Objetivo:** Reescrever o sistema de agentes do Ahri V3 usando padrões avançados
> **Stack:** Python 3.11+ / FastAPI / SQLAlchemy async / Gemini API / Ollama
> **Estratégia:** Feature flag `engine_v2_enabled` — V1 e V4 coexistem

---

## Índice

- [Phase 0 - Foundation Types](#phase-0---foundation-types)
- [Phase 1 - Multi-Model & Provider Abstraction](#phase-1---multi-model--provider-abstraction)
- [Phase 2 - Tool Registry & Execution](#phase-2---tool-registry--execution)
- [Phase 3 - Core Query Engine](#phase-3---core-query-engine)
- [Phase 4 - Permission System](#phase-4---permission-system)
- [Phase 5 - Hook System](#phase-5---hook-system)
- [Phase 6 - Context Window Management](#phase-6---context-window-management)
- [Phase 7 - Agent Spawning & Coordination](#phase-7---agent-spawning--coordination)
- [Phase 8 - Plugin/Skill System](#phase-8---pluginskill-system)
- [Phase 9 - Worker Migration](#phase-9---worker-migration)
- [Phase 10 - Database Schema](#phase-10---database-schema)
- [Phase 11 - Frontend Changes](#phase-11---frontend-changes)
- [Rollout Strategy](#rollout-strategy)
- [Testing Strategy](#testing-strategy)

---

## Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React)                       │
│  AgentModeView → WebSocket → /engine/v2/execute             │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   FastAPI Router                             │
│  /engine/v2/execute  /engine/v2/status  /engine/v2/cancel   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    QueryEngine                               │
│  async generator loop: LLM call → tool use → yield events   │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌────────────┐  │
│  │ Provider │  │ Tool     │  │ Permission│  │ Hook       │  │
│  │ Registry │  │ Registry │  │ System    │  │ System     │  │
│  └─────────┘  └──────────┘  └───────────┘  └────────────┘  │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐                  │
│  │ Compact  │  │ Agent    │  │ Plugin    │                  │
│  │ Manager  │  │ Spawner  │  │ Loader    │                  │
│  └─────────┘  └──────────┘  └───────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### Inspiração: Claude Code Architecture

O Claude Code usa um **async generator query loop** como coração do sistema:
1. Monta mensagens (system + history + user)
2. Chama LLM → recebe resposta com possíveis tool_calls
3. Para cada tool_call: verifica permissão → executa hook PRE → executa tool → executa hook POST
4. Yield eventos para o frontend em tempo real
5. Decide se continua (has tool_calls?) ou para
6. Se context window > threshold → compact automaticamente

Nós adaptamos esse padrão para Python/FastAPI com providers Gemini/Ollama.

---

## Phase 0 - Foundation Types

**Dependências:** Nenhuma
**Arquivos a criar:**
- `packages/backend/src/engine/__init__.py`
- `packages/backend/src/engine/types.py`
- `packages/backend/src/engine/errors.py`
- `packages/backend/src/engine/events.py`

**Arquivos a modificar:**
- `packages/backend/src/config.py` (novas settings)

### 0.1 — `engine/__init__.py`

```python
"""
Ahri V4 Engine - Modular agent execution engine.

Inspired by Claude Code (Anthropic) architecture patterns:
- Async generator query loop
- Tool registry with concurrent/serial partitioning
- Permission system in layers
- Hook system (event-driven)
- Agent spawning with isolated contexts
- Plugin system
"""
```

### 0.2 — `engine/types.py`

```python
"""
Foundation types for the V4 Engine.
Inspired by Claude Code's query.ts Message/ToolUse/ToolResult types.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, AsyncGenerator


# ── Enums ──

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_RESULT = "tool_result"


class StopReason(str, Enum):
    END_TURN = "end_turn"           # LLM decided to stop
    TOOL_USE = "tool_use"           # LLM wants to call tools
    MAX_TOKENS = "max_tokens"       # Hit token limit
    CANCELLED = "cancelled"         # User cancelled
    ERROR = "error"                 # Error occurred


class ToolInputSource(str, Enum):
    """Where a tool call came from."""
    LLM = "llm"                     # LLM generated the tool call
    USER = "user"                   # User explicitly requested
    SYSTEM = "system"               # System-generated (e.g., auto-compact)


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"                     # Ask user for permission


class ContinuationDecision(str, Enum):
    CONTINUE = "continue"           # Keep the loop going
    STOP = "stop"                   # End the loop
    COMPACT = "compact"             # Compact context then continue


# ── Core Data Classes ──

@dataclass
class Message:
    """A single message in the conversation."""
    role: Role
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_api_format(self, provider: str = "gemini") -> dict:
        """Convert to provider-specific API format."""
        if provider == "gemini":
            return {
                "role": "model" if self.role == Role.ASSISTANT else self.role.value,
                "parts": [{"text": self.content}],
            }
        elif provider == "ollama":
            return {
                "role": self.role.value,
                "content": self.content,
            }
        # OpenRouter/OpenAI compatible
        return {
            "role": self.role.value,
            "content": self.content,
        }


@dataclass
class ToolCall:
    """A tool invocation requested by the LLM."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    source: ToolInputSource = ToolInputSource.LLM


@dataclass
class ToolResult:
    """Result of executing a tool."""
    tool_call_id: str = ""
    tool_name: str = ""
    output: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: StopReason = StopReason.END_TURN
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    thinking: Optional[str] = None  # For models with thinking/reasoning
    raw_response: Optional[Any] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class EngineState:
    """
    Mutable state of a query engine execution.
    Inspired by Claude Code's queryState in query.ts.
    """
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""
    model: str = ""
    iteration: int = 0
    max_iterations: int = 50
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    is_cancelled: bool = False
    is_compact_needed: bool = False
    start_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Sub-agent tracking
    depth: int = 0                  # 0 = root, 1 = sub-agent, 2 = sub-sub-agent
    max_depth: int = 3
    parent_id: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def add_message(self, message: Message):
        self.messages.append(message)
        self.total_input_tokens += message.token_count

    def cancel(self):
        self.is_cancelled = True


@dataclass
class ModelCapabilities:
    """What a model can do."""
    max_tokens: int = 8192
    supports_tools: bool = True
    supports_vision: bool = False
    supports_thinking: bool = False
    supports_streaming: bool = True
    supports_json_mode: bool = True
    context_window: int = 128000
    cost_per_1k_input: float = 0.0    # USD, 0 = free tier
    cost_per_1k_output: float = 0.0


@dataclass
class ModelInfo:
    """Full model descriptor."""
    id: str                           # e.g., "gemini-2.5-flash"
    provider: str                     # e.g., "gemini", "ollama", "openrouter"
    display_name: str = ""
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    aliases: list[str] = field(default_factory=list)  # e.g., ["fast", "default"]
    api_key_env: str = ""             # Environment variable for API key
    fallback_to: Optional[str] = None # Model ID to fall back to on error


# Type alias for the engine's async generator
EngineGenerator = AsyncGenerator["AgentEvent", None]
```

### 0.3 — `engine/errors.py`

```python
"""
Engine-specific errors.
Inspired by Claude Code's error handling patterns.
"""
from typing import Optional


class EngineError(Exception):
    """Base error for all engine operations."""
    def __init__(self, message: str, code: str = "ENGINE_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderError(EngineError):
    """LLM provider returned an error."""
    def __init__(self, message: str, provider: str, status_code: Optional[int] = None, retryable: bool = True):
        super().__init__(message, code="PROVIDER_ERROR", retryable=retryable)
        self.provider = provider
        self.status_code = status_code


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    def __init__(self, message: str, provider: str, retry_after: Optional[float] = None):
        super().__init__(message, provider=provider, retryable=True)
        self.code = "RATE_LIMIT"
        self.retry_after = retry_after


class ContextWindowError(EngineError):
    """Context window exceeded."""
    def __init__(self, message: str, tokens_used: int = 0, max_tokens: int = 0):
        super().__init__(message, code="CONTEXT_WINDOW", retryable=True)
        self.tokens_used = tokens_used
        self.max_tokens = max_tokens


class ToolExecutionError(EngineError):
    """Tool execution failed."""
    def __init__(self, message: str, tool_name: str, retryable: bool = False):
        super().__init__(message, code="TOOL_ERROR", retryable=retryable)
        self.tool_name = tool_name


class PermissionDeniedError(EngineError):
    """Permission denied for tool/action."""
    def __init__(self, message: str, tool_name: str, rule: str = ""):
        super().__init__(message, code="PERMISSION_DENIED", retryable=False)
        self.tool_name = tool_name
        self.rule = rule


class MaxIterationsError(EngineError):
    """Max iterations reached."""
    def __init__(self, iterations: int):
        super().__init__(f"Max iterations reached: {iterations}", code="MAX_ITERATIONS", retryable=False)
        self.iterations = iterations


class SubAgentError(EngineError):
    """Sub-agent execution failed."""
    def __init__(self, message: str, agent_id: str, depth: int):
        super().__init__(message, code="SUBAGENT_ERROR", retryable=False)
        self.agent_id = agent_id
        self.depth = depth
```

### 0.4 — `engine/events.py`

```python
"""
Event types yielded by the QueryEngine async generator.
The frontend consumes these via WebSocket for real-time updates.
Inspired by Claude Code's streaming events architecture.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    # ── Lifecycle ──
    ENGINE_START = "engine_start"
    ENGINE_STOP = "engine_stop"
    ITERATION_START = "iteration_start"
    ITERATION_END = "iteration_end"

    # ── LLM ──
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_STREAM_CHUNK = "llm_stream_chunk"
    LLM_ERROR = "llm_error"

    # ── Tools ──
    TOOL_USE_START = "tool_use_start"
    TOOL_USE_END = "tool_use_end"
    TOOL_PERMISSION_ASK = "tool_permission_ask"
    TOOL_PERMISSION_RESULT = "tool_permission_result"

    # ── Hooks ──
    HOOK_TRIGGERED = "hook_triggered"
    HOOK_RESULT = "hook_result"

    # ── Compaction ──
    COMPACT_START = "compact_start"
    COMPACT_END = "compact_end"

    # ── Sub-agents ──
    AGENT_SPAWN = "agent_spawn"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"

    # ── User-facing ──
    TEXT_CHUNK = "text_chunk"          # Streaming text to user
    FINAL_RESPONSE = "final_response"  # Complete response
    ERROR = "error"
    CANCELLED = "cancelled"

    # ── Progress ──
    PROGRESS = "progress"
    STATUS_UPDATE = "status_update"


@dataclass
class AgentEvent:
    """
    Single event from the engine.
    Serializable to JSON for WebSocket transmission.
    """
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    execution_id: str = ""
    iteration: int = 0

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "execution_id": self.execution_id,
            "iteration": self.iteration,
        }

    # ── Factory methods ──

    @classmethod
    def engine_start(cls, execution_id: str, model: str, goal: str) -> AgentEvent:
        return cls(
            type=EventType.ENGINE_START,
            execution_id=execution_id,
            data={"model": model, "goal": goal},
        )

    @classmethod
    def engine_stop(cls, execution_id: str, reason: str, total_tokens: int) -> AgentEvent:
        return cls(
            type=EventType.ENGINE_STOP,
            execution_id=execution_id,
            data={"reason": reason, "total_tokens": total_tokens},
        )

    @classmethod
    def text_chunk(cls, execution_id: str, text: str, iteration: int = 0) -> AgentEvent:
        return cls(
            type=EventType.TEXT_CHUNK,
            execution_id=execution_id,
            iteration=iteration,
            data={"text": text},
        )

    @classmethod
    def tool_start(cls, execution_id: str, tool_name: str, args: dict, iteration: int = 0) -> AgentEvent:
        return cls(
            type=EventType.TOOL_USE_START,
            execution_id=execution_id,
            iteration=iteration,
            data={"tool_name": tool_name, "arguments": args},
        )

    @classmethod
    def tool_end(cls, execution_id: str, tool_name: str, result: Any, duration_ms: int = 0, iteration: int = 0) -> AgentEvent:
        return cls(
            type=EventType.TOOL_USE_END,
            execution_id=execution_id,
            iteration=iteration,
            data={"tool_name": tool_name, "result": result, "duration_ms": duration_ms},
        )

    @classmethod
    def error(cls, execution_id: str, error: str, code: str = "ERROR") -> AgentEvent:
        return cls(
            type=EventType.ERROR,
            execution_id=execution_id,
            data={"error": error, "code": code},
        )

    @classmethod
    def progress(cls, execution_id: str, message: str, percent: float = 0) -> AgentEvent:
        return cls(
            type=EventType.PROGRESS,
            execution_id=execution_id,
            data={"message": message, "percent": percent},
        )

    @classmethod
    def agent_spawn(cls, execution_id: str, child_id: str, goal: str, depth: int) -> AgentEvent:
        return cls(
            type=EventType.AGENT_SPAWN,
            execution_id=execution_id,
            data={"child_id": child_id, "goal": goal, "depth": depth},
        )
```

### 0.5 — Modificar `config.py`

Adicionar ao final da classe `Settings` (antes de `@lru_cache`):

```python
    # ── Engine V4 ──
    engine_v2_enabled: bool = False           # Feature flag: True = use V4 engine
    engine_default_model: str = "fast"         # Alias: "fast", "best", "local", or model ID
    engine_max_iterations: int = 50            # Max tool-use loops per execution
    engine_compact_threshold: float = 0.80     # Compact at 80% context window
    engine_compact_keep_recent: int = 4        # Keep last N messages after compaction
    engine_permission_mode: str = "auto"       # "auto" | "ask" | "trust"
    engine_plugin_dirs: str = ""               # Comma-separated plugin directories
    engine_enable_subagents: bool = True       # Allow sub-agent spawning
    engine_max_subagent_depth: int = 3         # Max nesting depth
    engine_coordinator_mode: str = "single"    # "single" | "multi" | "swarm"
    engine_hook_timeout: int = 30              # Hook execution timeout (seconds)
    engine_stream_enabled: bool = True         # Stream events via WebSocket

    @property
    def engine_plugin_directories(self) -> list[str]:
        """Parse comma-separated plugin dirs into list."""
        if not self.engine_plugin_dirs:
            return []
        return [d.strip() for d in self.engine_plugin_dirs.split(",") if d.strip()]
```

### 0.6 — Testes Phase 0

```python
# packages/backend/tests/engine/test_types.py
import pytest
from src.engine.types import (
    Message, Role, ToolCall, ToolResult, LLMResponse,
    EngineState, StopReason, ModelInfo, ModelCapabilities,
)
from src.engine.events import AgentEvent, EventType
from src.engine.errors import ProviderError, RateLimitError


def test_message_creation():
    msg = Message(role=Role.USER, content="Hello")
    assert msg.role == Role.USER
    assert msg.content == "Hello"
    assert msg.tool_calls == []


def test_message_to_gemini_format():
    msg = Message(role=Role.ASSISTANT, content="Hi there")
    fmt = msg.to_api_format("gemini")
    assert fmt["role"] == "model"
    assert fmt["parts"][0]["text"] == "Hi there"


def test_message_to_ollama_format():
    msg = Message(role=Role.USER, content="Test")
    fmt = msg.to_api_format("ollama")
    assert fmt["role"] == "user"
    assert fmt["content"] == "Test"


def test_llm_response_properties():
    resp = LLMResponse(
        content="result",
        tool_calls=[ToolCall(tool_name="file_read")],
        input_tokens=100,
        output_tokens=50,
    )
    assert resp.total_tokens == 150
    assert resp.has_tool_calls is True


def test_engine_state_lifecycle():
    state = EngineState(model="gemini-2.5-flash", max_iterations=10)
    assert state.iteration == 0
    assert state.is_cancelled is False

    msg = Message(role=Role.USER, content="Do something", token_count=10)
    state.add_message(msg)
    assert len(state.messages) == 1
    assert state.total_input_tokens == 10

    state.cancel()
    assert state.is_cancelled is True


def test_agent_event_serialization():
    event = AgentEvent.engine_start("exec-1", "gemini-2.5-flash", "Search files")
    d = event.to_dict()
    assert d["type"] == "engine_start"
    assert d["data"]["model"] == "gemini-2.5-flash"
    assert d["execution_id"] == "exec-1"


def test_error_hierarchy():
    err = RateLimitError("Too many requests", provider="gemini", retry_after=60)
    assert isinstance(err, ProviderError)
    assert err.retryable is True
    assert err.retry_after == 60


def test_model_capabilities():
    caps = ModelCapabilities(max_tokens=65536, supports_vision=True)
    info = ModelInfo(
        id="gemini-2.5-flash",
        provider="gemini",
        capabilities=caps,
        aliases=["fast", "default"],
    )
    assert "fast" in info.aliases
    assert info.capabilities.supports_vision is True
```

---

## Phase 1 - Multi-Model & Provider Abstraction

**Dependências:** Phase 0
**Arquivos a criar:**
- `packages/backend/src/engine/providers/__init__.py`
- `packages/backend/src/engine/providers/base.py`
- `packages/backend/src/engine/providers/gemini_provider.py`
- `packages/backend/src/engine/providers/ollama_provider.py`
- `packages/backend/src/engine/providers/openrouter_provider.py`
- `packages/backend/src/engine/model_registry.py`

### Conceito

No V3 atual, `LLMService` usa `set_mode()` global (não thread-safe para agentes). No V4, cada provider é uma classe isolada que recebe API key no construtor. O `ModelRegistry` resolve aliases ("fast" → "gemini-3.1-flash-lite"), gerencia fallback chains, e faz round-robin de API keys.

### 1.1 — `providers/base.py`

```python
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
```

### 1.2 — `providers/gemini_provider.py`

```python
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
        self._client = httpx.AsyncClient(timeout=120.0)

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

        body = {
            "contents": self.format_messages(messages),
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
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
        """Convert to Gemini format: role=user/model, parts=[{text:...}]."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "assistant":
                role = "model"
            elif role == "system":
                # Gemini doesn't have system role in contents,
                # system instruction goes separately
                continue
            elif role == "tool_result":
                # Format as function response
                formatted.append({
                    "role": "function",
                    "parts": [{"functionResponse": {
                        "name": msg.get("tool_name", "unknown"),
                        "response": {"result": msg.get("content", "")},
                    }}],
                })
                continue

            formatted.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}],
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
```

### 1.3 — `providers/ollama_provider.py`

```python
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
```

### 1.4 — `providers/openrouter_provider.py`

```python
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
```

### 1.5 — `model_registry.py`

```python
"""
Model Registry - Resolve model aliases, manage fallbacks, rotate API keys.

Inspired by Claude Code's model.ts:
- Aliases: "fast" → "gemini-3.1-flash-lite-preview"
- Fallback chains: if model A fails → try model B
- Round-robin API key rotation for rate limit management

IMPORTANT: This replaces the set_mode() pattern from V3 LLMService.
"""
import logging
import asyncio
from typing import Optional
from collections import defaultdict

from .types import ModelInfo, ModelCapabilities, LLMResponse
from .providers.base import LLMProvider
from .providers.gemini_provider import GeminiProvider
from .providers.ollama_provider import OllamaProvider
from .providers.openrouter_provider import OpenRouterProvider
from .errors import ProviderError, RateLimitError

logger = logging.getLogger("ahri.engine.registry")


class ModelRegistry:
    """
    Central model registry.

    Resolves aliases, manages providers, handles fallbacks, rotates API keys.
    Thread-safe: all mutable state is accessed through async locks.
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._models: dict[str, ModelInfo] = {}
        self._aliases: dict[str, str] = {}       # alias → model_id
        self._api_keys: dict[str, list[str]] = defaultdict(list)  # provider → [keys]
        self._key_index: dict[str, int] = defaultdict(int)        # provider → current index
        self._lock = asyncio.Lock()

    def register_provider(self, name: str, provider: LLMProvider):
        """Register an LLM provider."""
        self._providers[name] = provider
        logger.info(f"Registered provider: {name}")

    def register_model(self, model: ModelInfo):
        """Register a model with its metadata."""
        self._models[model.id] = model
        for alias in model.aliases:
            self._aliases[alias] = model.id
        logger.info(f"Registered model: {model.id} (aliases: {model.aliases})")

    def add_api_key(self, provider: str, key: str):
        """Add an API key for round-robin rotation."""
        if key and key not in self._api_keys[provider]:
            self._api_keys[provider].append(key)

    def resolve(self, model_or_alias: str) -> ModelInfo:
        """
        Resolve a model alias to full ModelInfo.

        Args:
            model_or_alias: "fast", "best", "local", or full model ID

        Returns:
            ModelInfo for the resolved model

        Raises:
            KeyError if model not found
        """
        # Direct model ID
        if model_or_alias in self._models:
            return self._models[model_or_alias]

        # Alias resolution
        if model_or_alias in self._aliases:
            model_id = self._aliases[model_or_alias]
            return self._models[model_id]

        raise KeyError(f"Unknown model or alias: {model_or_alias}")

    async def get_next_key(self, provider: str) -> str:
        """Get next API key in round-robin rotation (thread-safe)."""
        async with self._lock:
            keys = self._api_keys.get(provider, [])
            if not keys:
                raise ProviderError(f"No API keys for provider: {provider}", provider=provider)

            idx = self._key_index[provider] % len(keys)
            self._key_index[provider] = idx + 1
            return keys[idx]

    async def call(
        self,
        model_or_alias: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        thinking_budget: int = 0,
        json_mode: bool = False,
        api_key: Optional[str] = None,
    ) -> LLMResponse:
        """
        Call an LLM model with automatic fallback and key rotation.

        Args:
            model_or_alias: Model identifier or alias
            messages: Conversation messages
            tools: Tool definitions for function calling
            api_key: Specific API key (skips rotation if provided)

        Returns:
            LLMResponse from the model
        """
        model_info = self.resolve(model_or_alias)
        provider = self._providers.get(model_info.provider)
        if not provider:
            raise ProviderError(f"Provider not found: {model_info.provider}", provider=model_info.provider)

        # Get API key (provided > rotated)
        key = api_key or await self.get_next_key(model_info.provider)

        try:
            return await provider.generate(
                messages=messages,
                model=model_info.id,
                api_key=key,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_budget=thinking_budget,
                json_mode=json_mode,
            )
        except RateLimitError:
            # Try fallback model if available
            if model_info.fallback_to:
                logger.warning(f"Rate limit on {model_info.id}, falling back to {model_info.fallback_to}")
                return await self.call(
                    model_info.fallback_to, messages, tools,
                    temperature, max_tokens, thinking_budget, json_mode,
                )
            raise
        except ProviderError as e:
            if e.retryable and model_info.fallback_to:
                logger.warning(f"Error on {model_info.id}: {e}, falling back to {model_info.fallback_to}")
                return await self.call(
                    model_info.fallback_to, messages, tools,
                    temperature, max_tokens, thinking_budget, json_mode,
                )
            raise

    @property
    def available_models(self) -> list[ModelInfo]:
        return list(self._models.values())

    @property
    def available_aliases(self) -> dict[str, str]:
        return dict(self._aliases)


def create_model_registry(settings) -> ModelRegistry:
    """
    Factory function to create a fully configured ModelRegistry.
    Called once at app startup in main.py lifespan.

    Args:
        settings: Pydantic Settings instance from config.py
    """
    registry = ModelRegistry()

    # ── Register providers ──
    registry.register_provider("gemini", GeminiProvider())
    registry.register_provider("ollama", OllamaProvider(base_url=settings.ollama_base_url))

    if settings.openrouter_api_key:
        registry.register_provider("openrouter", OpenRouterProvider())

    # ── Register models ──

    # Gemini Flash Lite (cheapest, fastest — for agents/workers)
    registry.register_model(ModelInfo(
        id=settings.google_model_lite,
        provider="gemini",
        display_name="Gemini Flash Lite",
        aliases=["fast", "lite", "agent", "LITE"],
        capabilities=ModelCapabilities(
            max_tokens=8192, supports_tools=True, supports_vision=False,
            supports_thinking=False, context_window=262144,
        ),
        fallback_to=settings.google_model_flash,
    ))

    # Gemini Flash (balanced — default for orchestration)
    registry.register_model(ModelInfo(
        id=settings.google_model_flash,
        provider="gemini",
        display_name="Gemini Flash",
        aliases=["default", "balanced", "flash", "FLASH", "GOOGLE"],
        capabilities=ModelCapabilities(
            max_tokens=65536, supports_tools=True, supports_vision=True,
            supports_thinking=True, context_window=1048576,
        ),
        fallback_to=settings.google_model_lite,
    ))

    # Gemini Pro (best — for complex reasoning)
    registry.register_model(ModelInfo(
        id=settings.google_model_pro,
        provider="gemini",
        display_name="Gemini Pro",
        aliases=["best", "pro", "smart", "PRO"],
        capabilities=ModelCapabilities(
            max_tokens=65536, supports_tools=True, supports_vision=True,
            supports_thinking=True, context_window=1048576,
        ),
        fallback_to=settings.google_model_flash,
    ))

    # Ollama local model
    registry.register_model(ModelInfo(
        id=settings.ollama_chat_model,
        provider="ollama",
        display_name="Local (Ollama)",
        aliases=["local", "LOCAL", "ollama"],
        capabilities=ModelCapabilities(
            max_tokens=8192, supports_tools=True, supports_vision=False,
            supports_thinking=True, context_window=32768,
        ),
    ))

    # DeepSeek via OpenRouter (optional)
    if settings.openrouter_api_key:
        registry.register_model(ModelInfo(
            id=settings.openrouter_model_name,
            provider="openrouter",
            display_name="DeepSeek R1 (OpenRouter)",
            aliases=["deepseek", "DEEPSEEK", "reasoning"],
            capabilities=ModelCapabilities(
                max_tokens=8192, supports_tools=True, supports_thinking=True,
                context_window=128000,
            ),
            fallback_to=settings.google_model_flash,
        ))
        registry.add_api_key("openrouter", settings.openrouter_api_key)

    # ── Register API keys (round-robin) ──
    for key in settings.agent_api_keys:
        registry.add_api_key("gemini", key)

    # Add primary keys too
    if settings.gemini_api_key_paid:
        registry.add_api_key("gemini", settings.gemini_api_key_paid)
    if settings.gemini_api_key_free:
        registry.add_api_key("gemini", settings.gemini_api_key_free)

    logger.info(
        f"ModelRegistry initialized: {len(registry.available_models)} models, "
        f"{len(registry._api_keys.get('gemini', []))} Gemini keys"
    )

    return registry
```

### 1.6 — Testes Phase 1

```python
# packages/backend/tests/engine/test_model_registry.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.model_registry import ModelRegistry, create_model_registry
from src.engine.types import ModelInfo, ModelCapabilities, LLMResponse, StopReason


@pytest.fixture
def registry():
    r = ModelRegistry()
    r.register_model(ModelInfo(
        id="gemini-2.5-flash",
        provider="gemini",
        aliases=["fast", "default"],
        capabilities=ModelCapabilities(max_tokens=65536),
        fallback_to="gemini-3.1-flash-lite",
    ))
    r.register_model(ModelInfo(
        id="gemini-3.1-flash-lite",
        provider="gemini",
        aliases=["lite"],
    ))
    r.add_api_key("gemini", "key-1")
    r.add_api_key("gemini", "key-2")
    return r


def test_resolve_alias(registry):
    info = registry.resolve("fast")
    assert info.id == "gemini-2.5-flash"


def test_resolve_direct(registry):
    info = registry.resolve("gemini-2.5-flash")
    assert info.id == "gemini-2.5-flash"


def test_resolve_unknown_raises(registry):
    with pytest.raises(KeyError):
        registry.resolve("nonexistent")


@pytest.mark.asyncio
async def test_key_rotation(registry):
    k1 = await registry.get_next_key("gemini")
    k2 = await registry.get_next_key("gemini")
    k3 = await registry.get_next_key("gemini")
    assert k1 == "key-1"
    assert k2 == "key-2"
    assert k3 == "key-1"  # Round-robin wraps


@pytest.mark.asyncio
async def test_call_with_fallback(registry):
    """Test that fallback is used when primary model rate-limited."""
    from src.engine.errors import RateLimitError

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=[
        RateLimitError("rate limit", provider="gemini"),
        LLMResponse(content="fallback worked", model="gemini-3.1-flash-lite"),
    ])
    registry._providers["gemini"] = mock_provider

    result = await registry.call("fast", messages=[{"role": "user", "content": "test"}])
    assert result.content == "fallback worked"
    assert mock_provider.generate.call_count == 2
```

---

## Phase 2 - Tool Registry & Execution

**Dependências:** Phase 0, Phase 1
**Arquivos a criar:**
- `packages/backend/src/engine/tools/__init__.py`
- `packages/backend/src/engine/tools/base.py`
- `packages/backend/src/engine/tools/registry.py`
- `packages/backend/src/engine/tools/builtin/__init__.py`
- `packages/backend/src/engine/tools/builtin/file_tools.py`
- `packages/backend/src/engine/tools/builtin/shell_tools.py`
- `packages/backend/src/engine/tools/builtin/code_tools.py`
- `packages/backend/src/engine/tools/builtin/web_tools.py`
- `packages/backend/src/engine/tools/builtin/memory_tools.py`
- `packages/backend/src/engine/tools/builtin/search_tools.py`
- `packages/backend/src/engine/tools/builtin/vision_tools.py`

### Conceito

No V3 atual, cada Worker é uma classe monolítica (ShellWorker tem read_file, write_file, list_dir, execute_command). No V4, cada operação atômica vira um **Tool** independente. Tools são registrados no **ToolRegistry** que particiona entre concurrent (read-only, pode rodar em paralelo) e serial (stateful, roda sequencialmente).

Pattern inspirado no Claude Code `Tool.ts` + `toolOrchestration.ts`.

### 2.1 — `tools/base.py`

```python
"""
Tool definitions and context.

Inspired by Claude Code's Tool.ts:
- ToolDefinition: schema + handler + metadata
- ToolUseContext: dependency injection container passed to every tool handler
- ToolHandler: async callable that receives context + arguments

Key difference from V3 Workers:
- Workers were class-based with inheritance (BaseWorker → ShellWorker)
- Tools are function-based with context injection (no inheritance needed)
- Each tool is atomic (one operation), not a bundle of methods
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..model_registry import ModelRegistry
    from .registry import ToolRegistry
    from ..permissions.base import PermissionManager
    from ..hooks.manager import HookManager


class ToolCategory(str, Enum):
    """Tool categories for grouping and permission rules."""
    FILE_SYSTEM = "filesystem"      # File read/write/list
    SHELL = "shell"                 # Command execution
    CODE = "code"                   # Code analysis/generation
    WEB = "web"                     # HTTP requests, scraping
    MEMORY = "memory"               # Memory search/store
    SEARCH = "search"               # Web search
    VISION = "vision"               # Image analysis
    BROWSER = "browser"             # Browser automation
    AGENT = "agent"                 # Sub-agent spawning
    SYSTEM = "system"               # Internal system tools
    CUSTOM = "custom"               # Plugin-provided tools


class ExecutionMode(str, Enum):
    """How a tool can be executed."""
    CONCURRENT = "concurrent"       # Safe to run in parallel (read-only)
    SERIAL = "serial"               # Must run one at a time (stateful)


class PermissionLevel(str, Enum):
    """Default permission requirement for a tool."""
    SAFE = "safe"                   # Auto-execute, no confirmation needed
    CONFIRM = "confirm"             # Needs user confirmation
    DANGEROUS = "dangerous"         # Blocked by default, needs explicit allowlisting


@dataclass
class ToolDefinition:
    """
    Complete definition of a tool.

    This is what gets registered in the ToolRegistry and
    presented to the LLM as a function declaration.
    """
    name: str                       # Unique tool name (e.g., "file_read")
    description: str                # Description shown to the LLM
    category: ToolCategory = ToolCategory.CUSTOM
    execution_mode: ExecutionMode = ExecutionMode.SERIAL
    permission_level: PermissionLevel = PermissionLevel.SAFE

    # JSON Schema for parameters (Gemini function calling format)
    parameters: dict[str, Any] = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
        "required": [],
    })

    # The actual handler function
    handler: Optional[ToolHandler] = None

    # Metadata
    version: str = "1.0.0"
    plugin_name: Optional[str] = None  # Set if tool comes from a plugin
    is_builtin: bool = True
    enabled: bool = True

    def to_function_declaration(self) -> dict:
        """Convert to Gemini function calling format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_openai_format(self) -> dict:
        """Convert to OpenAI/Ollama tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolUseContext:
    """
    Dependency injection context passed to every tool handler.

    Instead of tools inheriting from BaseWorker and accessing self.llm,
    everything a tool needs is in this context object.

    Inspired by Claude Code's ToolUseContext pattern.
    """
    # Core services
    model_registry: ModelRegistry
    tool_registry: ToolRegistry
    permission_manager: Optional[PermissionManager] = None
    hook_manager: Optional[HookManager] = None

    # Database session (async)
    db: Optional[Any] = None  # AsyncSession

    # Current execution state
    execution_id: str = ""
    user_id: str = ""
    working_directory: str = ""

    # Model preferences for this execution
    default_model: str = "fast"     # Alias for the model to use

    # Settings
    settings: Optional[Any] = None  # Pydantic Settings

    # Metadata (extensible by plugins)
    metadata: dict[str, Any] = field(default_factory=dict)

    async def call_llm(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        json_mode: bool = False,
        thinking_budget: int = 0,
    ) -> Any:
        """
        Convenience method for tools to call an LLM.
        Uses the model registry for alias resolution and key rotation.
        """
        from ..types import LLMResponse
        return await self.model_registry.call(
            model_or_alias=model or self.default_model,
            messages=messages,
            tools=tools,
            json_mode=json_mode,
            thinking_budget=thinking_budget,
        )


# Type alias for tool handler functions
ToolHandler = Callable[[ToolUseContext, dict[str, Any]], Awaitable[Any]]


def build_tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.CUSTOM,
    execution_mode: ExecutionMode = ExecutionMode.SERIAL,
    permission_level: PermissionLevel = PermissionLevel.SAFE,
    parameters: Optional[dict] = None,
    is_builtin: bool = True,
) -> Callable[[ToolHandler], ToolDefinition]:
    """
    Decorator factory to build a ToolDefinition from a handler function.

    Usage:
        @build_tool(
            name="file_read",
            description="Read a file from disk",
            category=ToolCategory.FILE_SYSTEM,
            execution_mode=ExecutionMode.CONCURRENT,
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        )
        async def file_read(ctx: ToolUseContext, args: dict) -> str:
            path = args["path"]
            ...
    """
    def decorator(handler: ToolHandler) -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description=description,
            category=category,
            execution_mode=execution_mode,
            permission_level=permission_level,
            parameters=parameters or {"type": "object", "properties": {}, "required": []},
            handler=handler,
            is_builtin=is_builtin,
        )
    return decorator
```

### 2.2 — `tools/registry.py`

```python
"""
Tool Registry - Central registry for all tools.

Inspired by Claude Code's toolOrchestration.ts:
- Partition tools into concurrent (read-only) and serial (stateful)
- Execute concurrent tools in parallel (asyncio.gather)
- Execute serial tools one at a time
- Support for enable/disable per-tool

Key insight from Claude Code:
Tools are partitioned at execution time, not registration time.
A batch of tool calls from one LLM response gets split into
concurrent-safe tools (run together) and serial tools (run after).
"""
import asyncio
import time
import logging
from typing import Optional

from .base import (
    ToolDefinition, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)
from ..types import ToolCall, ToolResult
from ..errors import ToolExecutionError

logger = logging.getLogger("ahri.engine.tools")


class ToolRegistry:
    """
    Central registry for tools.
    Handles registration, lookup, partitioning, and batch execution.
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        """Register a tool. Overwrites if name exists (plugin override)."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting tool: {tool.name}")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} ({tool.category.value}, {tool.execution_mode.value})")

    def register_many(self, tools: list[ToolDefinition]):
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str):
        """Remove a tool from the registry."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Look up a tool by name."""
        return self._tools.get(name)

    def get_enabled(self) -> list[ToolDefinition]:
        """Return all enabled tools."""
        return [t for t in self._tools.values() if t.enabled]

    def get_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        """Return tools in a category."""
        return [t for t in self._tools.values() if t.category == category and t.enabled]

    def get_function_declarations(self) -> list[dict]:
        """
        Return all enabled tools as function declarations for the LLM.
        Used when building the LLM request.
        """
        return [t.to_function_declaration() for t in self.get_enabled()]

    def partition_tools(self, tool_calls: list[ToolCall]) -> tuple[list[ToolCall], list[ToolCall]]:
        """
        Partition a batch of tool calls into concurrent and serial groups.

        Inspired by Claude Code's toolOrchestration.ts:
        - Concurrent: file reads, searches, memory lookups → run in parallel
        - Serial: file writes, command exec, browser → run sequentially

        Args:
            tool_calls: List of tool calls from LLM response

        Returns:
            (concurrent_calls, serial_calls)
        """
        concurrent = []
        serial = []

        for call in tool_calls:
            tool = self.get(call.tool_name)
            if tool and tool.execution_mode == ExecutionMode.CONCURRENT:
                concurrent.append(call)
            else:
                serial.append(call)

        return concurrent, serial

    async def execute_batch(
        self,
        tool_calls: list[ToolCall],
        context: ToolUseContext,
    ) -> list[ToolResult]:
        """
        Execute a batch of tool calls with optimal parallelism.

        1. Partition into concurrent and serial groups
        2. Run all concurrent tools in parallel (asyncio.gather)
        3. Run serial tools one at a time (in order)
        4. Return all results in original order

        Args:
            tool_calls: Tool calls from LLM response
            context: Shared context for all tools

        Returns:
            List of ToolResult in same order as tool_calls
        """
        if not tool_calls:
            return []

        concurrent, serial = self.partition_tools(tool_calls)

        results: dict[str, ToolResult] = {}  # tool_call.id → result

        # Execute concurrent tools in parallel
        if concurrent:
            concurrent_tasks = [
                self._execute_single(call, context) for call in concurrent
            ]
            concurrent_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)

            for call, result in zip(concurrent, concurrent_results):
                if isinstance(result, Exception):
                    results[call.id] = ToolResult(
                        tool_call_id=call.id,
                        tool_name=call.tool_name,
                        error=str(result),
                    )
                else:
                    results[call.id] = result

        # Execute serial tools sequentially
        for call in serial:
            try:
                result = await self._execute_single(call, context)
                results[call.id] = result
            except Exception as e:
                results[call.id] = ToolResult(
                    tool_call_id=call.id,
                    tool_name=call.tool_name,
                    error=str(e),
                )

        # Return in original order
        return [results[call.id] for call in tool_calls]

    async def _execute_single(
        self,
        tool_call: ToolCall,
        context: ToolUseContext,
    ) -> ToolResult:
        """Execute a single tool call."""
        tool = self.get(tool_call.tool_name)
        if not tool:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                error=f"Unknown tool: {tool_call.tool_name}",
            )

        if not tool.handler:
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                error=f"Tool has no handler: {tool_call.tool_name}",
            )

        start = time.time()
        try:
            output = await tool.handler(context, tool_call.arguments)
            duration_ms = int((time.time() - start) * 1000)

            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.error(f"Tool {tool_call.tool_name} failed: {e}")
            return ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                error=str(e),
                duration_ms=duration_ms,
            )

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def enabled_count(self) -> int:
        return len(self.get_enabled())
```

### 2.3 — `tools/builtin/file_tools.py`

```python
"""
File system tools - Read, write, list files.
Replaces ShellWorker.read_file(), write_file(), list_directory().

Permission levels:
- file_read: SAFE (read-only, concurrent)
- file_write: CONFIRM (modifies disk)
- file_list: SAFE (read-only, concurrent)
"""
import os
import json
from pathlib import Path
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="file_read",
    description="Read the contents of a file. Returns the text content. Supports text files (txt, py, js, ts, md, json, yaml, etc).",
    category=ToolCategory.FILE_SYSTEM,
    execution_mode=ExecutionMode.CONCURRENT,  # Safe to read in parallel
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative file path to read",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding (default: utf-8)",
                "default": "utf-8",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines to read (0 = all, default: 500)",
                "default": 500,
            },
        },
        "required": ["path"],
    },
)
async def file_read(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    path = _resolve_path(args["path"], ctx.working_directory)
    encoding = args.get("encoding", "utf-8")
    max_lines = args.get("max_lines", 500)

    if not path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    if not path.is_file():
        return json.dumps({"error": f"Not a file: {path}"})

    try:
        content = path.read_text(encoding=encoding)
        lines = content.split("\n")

        if max_lines > 0 and len(lines) > max_lines:
            content = "\n".join(lines[:max_lines])
            content += f"\n\n... (truncated, {len(lines)} total lines)"

        return json.dumps({
            "path": str(path),
            "content": content,
            "lines": min(len(lines), max_lines) if max_lines > 0 else len(lines),
            "total_lines": len(lines),
            "size_bytes": path.stat().st_size,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to read file: {e}"})


@build_tool(
    name="file_write",
    description="Write content to a file. Creates the file if it doesn't exist. Creates parent directories if needed.",
    category=ToolCategory.FILE_SYSTEM,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to write to",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
            "mode": {
                "type": "string",
                "enum": ["overwrite", "append"],
                "description": "Write mode (default: overwrite)",
                "default": "overwrite",
            },
        },
        "required": ["path", "content"],
    },
)
async def file_write(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    path = _resolve_path(args["path"], ctx.working_directory)
    content = args["content"]
    mode = args.get("mode", "overwrite")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            path.write_text(content, encoding="utf-8")

        return json.dumps({
            "path": str(path),
            "bytes_written": len(content.encode("utf-8")),
            "mode": mode,
            "success": True,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to write file: {e}"})


@build_tool(
    name="file_list",
    description="List files and directories in a given path. Returns names, sizes, and types.",
    category=ToolCategory.FILE_SYSTEM,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list",
            },
            "recursive": {
                "type": "boolean",
                "description": "List recursively (default: false)",
                "default": False,
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to filter (e.g., '*.py')",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results (default: 100)",
                "default": 100,
            },
        },
        "required": ["path"],
    },
)
async def file_list(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    path = _resolve_path(args["path"], ctx.working_directory)
    recursive = args.get("recursive", False)
    pattern = args.get("pattern", "*")
    max_results = args.get("max_results", 100)

    if not path.exists():
        return json.dumps({"error": f"Path not found: {path}"})

    if not path.is_dir():
        return json.dumps({"error": f"Not a directory: {path}"})

    try:
        entries = []
        glob_method = path.rglob if recursive else path.glob
        for i, entry in enumerate(glob_method(pattern)):
            if i >= max_results:
                break
            info = {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
            }
            if entry.is_file():
                info["size_bytes"] = entry.stat().st_size
            entries.append(info)

        return json.dumps({
            "path": str(path),
            "entries": entries,
            "count": len(entries),
            "truncated": len(entries) >= max_results,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to list directory: {e}"})


def _resolve_path(path_str: str, working_dir: str) -> Path:
    """Resolve path, making relative paths relative to working_dir."""
    p = Path(path_str)
    if not p.is_absolute() and working_dir:
        p = Path(working_dir) / p
    return p.resolve()


# Export all tools for registration
FILE_TOOLS = [file_read, file_write, file_list]
```

### 2.4 — `tools/builtin/shell_tools.py`

```python
"""
Shell command execution tool.
Replaces ShellWorker.execute_command().

IMPORTANT: Only allowed commands are executed. Uses allowlist approach.
"""
import asyncio
import json
import os
import subprocess
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)

# Commands that are safe to execute without confirmation
SAFE_COMMANDS = {
    "ls", "dir", "pwd", "whoami", "date", "echo",
    "cat", "head", "tail", "wc", "sort", "uniq",
    "find", "grep", "which", "type", "where",
    "python", "pip", "node", "npm", "git",
}

# Commands that are NEVER allowed
BLOCKED_COMMANDS = {
    "rm", "rmdir", "del", "format", "mkfs",
    "shutdown", "reboot", "kill", "taskkill",
    "curl", "wget",  # Use web_fetch tool instead
}


@build_tool(
    name="shell_execute",
    description="Execute a shell command and return stdout/stderr. Use for system commands, running scripts, git operations, package management, etc.",
    category=ToolCategory.SHELL,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (default: current)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        "required": ["command"],
    },
)
async def shell_execute(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    command = args["command"]
    working_dir = args.get("working_dir", ctx.working_directory)
    timeout = args.get("timeout", 30)

    # Extract base command for safety check
    base_cmd = command.strip().split()[0].lower() if command.strip() else ""

    if base_cmd in BLOCKED_COMMANDS:
        return json.dumps({
            "error": f"Command '{base_cmd}' is blocked for safety. Use dedicated tools instead.",
            "blocked": True,
        })

    try:
        loop = asyncio.get_running_loop()

        def _run():
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir or None,
            )
            return result

        result = await loop.run_in_executor(None, _run)

        return json.dumps({
            "command": command,
            "stdout": result.stdout[:10000],  # Limit output size
            "stderr": result.stderr[:5000],
            "return_code": result.returncode,
            "success": result.returncode == 0,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s", "command": command})
    except Exception as e:
        return json.dumps({"error": f"Command execution failed: {e}", "command": command})


SHELL_TOOLS = [shell_execute]
```

### 2.5 — `tools/builtin/code_tools.py`

```python
"""
Code analysis and generation tools.
Replaces CodeWorker functionality.
"""
import json
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="code_analyze",
    description="Analyze code for bugs, quality issues, security vulnerabilities, or understanding. Provide the code or a file path.",
    category=ToolCategory.CODE,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code to analyze (if not using file_path)"},
            "file_path": {"type": "string", "description": "Path to file to analyze"},
            "analysis_type": {
                "type": "string",
                "enum": ["bugs", "security", "quality", "explain", "review"],
                "description": "Type of analysis",
                "default": "review",
            },
            "language": {"type": "string", "description": "Programming language (auto-detected if not provided)"},
        },
        "required": [],
    },
)
async def code_analyze(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    code = args.get("code", "")
    file_path = args.get("file_path", "")
    analysis_type = args.get("analysis_type", "review")
    language = args.get("language", "")

    # If file_path provided, read the file
    if file_path and not code:
        from pathlib import Path
        p = Path(file_path)
        if p.exists():
            code = p.read_text(encoding="utf-8")
            if not language:
                ext_map = {".py": "python", ".js": "javascript", ".ts": "typescript", ".rs": "rust"}
                language = ext_map.get(p.suffix, p.suffix[1:])

    if not code:
        return json.dumps({"error": "No code provided. Use 'code' or 'file_path' parameter."})

    prompt = f"""Analyze the following {language} code. Focus on: {analysis_type}

```{language}
{code}
```

Return a JSON object with:
- "issues": list of {{severity, line, description, suggestion}}
- "summary": brief overall assessment
- "score": quality score 1-10
"""

    result = await ctx.call_llm(
        messages=[{"role": "user", "content": prompt}],
        json_mode=True,
    )

    return result.content if hasattr(result, 'content') else str(result)


@build_tool(
    name="code_generate",
    description="Generate code based on a description. Specify the language, requirements, and any constraints.",
    category=ToolCategory.CODE,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "What the code should do"},
            "language": {"type": "string", "description": "Programming language"},
            "context": {"type": "string", "description": "Additional context or requirements"},
            "style": {
                "type": "string",
                "enum": ["minimal", "production", "documented"],
                "default": "production",
            },
        },
        "required": ["description", "language"],
    },
)
async def code_generate(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    description = args["description"]
    language = args["language"]
    context = args.get("context", "")
    style = args.get("style", "production")

    prompt = f"""Generate {language} code that: {description}

Style: {style}
{f"Context: {context}" if context else ""}

Return ONLY the code, no explanations. Use best practices for {language}.
"""

    result = await ctx.call_llm(
        messages=[{"role": "user", "content": prompt}],
    )

    return json.dumps({
        "language": language,
        "code": result.content if hasattr(result, 'content') else str(result),
        "description": description,
    })


CODE_TOOLS = [code_analyze, code_generate]
```

### 2.6 — `tools/builtin/web_tools.py`

```python
"""
Web tools - HTTP fetch, scraping.
Replaces WebWorker.
"""
import json
from typing import Any

import httpx

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="web_fetch",
    description="Fetch content from a URL. Returns the text content of the page. Supports HTML, JSON, plain text.",
    category=ToolCategory.WEB,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "default": "GET",
            },
            "headers": {"type": "object", "description": "Custom headers"},
            "extract_text": {
                "type": "boolean",
                "description": "Extract text from HTML (default: true)",
                "default": True,
            },
            "max_length": {
                "type": "integer",
                "description": "Max content length in chars (default: 10000)",
                "default": 10000,
            },
        },
        "required": ["url"],
    },
)
async def web_fetch(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    url = args["url"]
    method = args.get("method", "GET")
    headers = args.get("headers", {})
    extract_text = args.get("extract_text", True)
    max_length = args.get("max_length", 10000)

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.request(method, url, headers=headers)

            content = response.text
            content_type = response.headers.get("content-type", "")

            # Extract text from HTML
            if extract_text and "html" in content_type:
                try:
                    from html.parser import HTMLParser
                    class TextExtractor(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.result = []
                            self._skip = False
                        def handle_starttag(self, tag, _):
                            if tag in ("script", "style", "noscript"):
                                self._skip = True
                        def handle_endtag(self, tag):
                            if tag in ("script", "style", "noscript"):
                                self._skip = False
                        def handle_data(self, data):
                            if not self._skip:
                                text = data.strip()
                                if text:
                                    self.result.append(text)

                    extractor = TextExtractor()
                    extractor.feed(content)
                    content = "\n".join(extractor.result)
                except Exception:
                    pass  # Fall back to raw content

            # Truncate
            if len(content) > max_length:
                content = content[:max_length] + f"\n... (truncated, {len(response.text)} total chars)"

            return json.dumps({
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "content": content,
                "content_length": len(content),
            })
    except httpx.TimeoutException:
        return json.dumps({"error": f"Request timed out: {url}"})
    except Exception as e:
        return json.dumps({"error": f"Fetch failed: {e}"})


WEB_TOOLS = [web_fetch]
```

### 2.7 — `tools/builtin/memory_tools.py`

```python
"""
Memory tools - Search and store memories.
Replaces MemoryWorker.
"""
import json
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="memory_search",
    description="Search through persona memories (episodic, profile, and session memories). Uses semantic search via ChromaDB.",
    category=ToolCategory.MEMORY,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "memory_type": {
                "type": "string",
                "enum": ["all", "episodic", "profile", "session"],
                "default": "all",
            },
            "max_results": {
                "type": "integer",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def memory_search(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    query = args["query"]
    memory_type = args.get("memory_type", "all")
    max_results = args.get("max_results", 5)

    # Use VectorService if available in context
    vector_svc = ctx.metadata.get("vector_service")
    if not vector_svc:
        return json.dumps({"error": "Vector service not available", "results": []})

    try:
        results = vector_svc.search(query, n_results=max_results)
        return json.dumps({
            "query": query,
            "results": results,
            "count": len(results),
        })
    except Exception as e:
        return json.dumps({"error": f"Memory search failed: {e}", "results": []})


@build_tool(
    name="memory_store",
    description="Store a new memory. The memory will be semantically searchable later.",
    category=ToolCategory.MEMORY,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Memory content to store"},
            "memory_type": {
                "type": "string",
                "enum": ["episodic", "profile", "knowledge"],
                "default": "episodic",
            },
            "importance": {
                "type": "string",
                "enum": ["critical", "important", "useful", "trivial"],
                "default": "useful",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization",
            },
        },
        "required": ["content"],
    },
)
async def memory_store(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    content = args["content"]
    memory_type = args.get("memory_type", "episodic")
    importance = args.get("importance", "useful")
    tags = args.get("tags", [])

    vector_svc = ctx.metadata.get("vector_service")
    if not vector_svc:
        return json.dumps({"error": "Vector service not available"})

    try:
        doc_id = vector_svc.add(content, metadata={
            "type": memory_type,
            "importance": importance,
            "tags": tags,
        })
        return json.dumps({
            "stored": True,
            "id": doc_id,
            "memory_type": memory_type,
            "importance": importance,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to store memory: {e}"})


MEMORY_TOOLS = [memory_search, memory_store]
```

### 2.8 — `tools/builtin/search_tools.py`

```python
"""
Search tools - Google Custom Search.
"""
import json
from typing import Any
import httpx

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="web_search",
    description="Search the web using Google Custom Search. Returns relevant results with titles, URLs, and snippets.",
    category=ToolCategory.SEARCH,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {
                "type": "integer",
                "description": "Number of results (max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def web_search(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    query = args["query"]
    num = min(args.get("num_results", 5), 10)

    settings = ctx.settings
    if not settings or not settings.cse_api_key:
        return json.dumps({"error": "Google Search API not configured", "results": []})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.cse_api_key,
                    "cx": settings.cse_cx,
                    "q": query,
                    "num": num,
                },
            )
            data = response.json()
            items = data.get("items", [])

            results = []
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            return json.dumps({"query": query, "results": results, "count": len(results)})

    except Exception as e:
        return json.dumps({"error": f"Search failed: {e}", "results": []})


SEARCH_TOOLS = [web_search]
```

### 2.9 — `tools/builtin/__init__.py`

```python
"""
Built-in tools for the V4 Engine.
Import all tool collections and provide a single registration function.
"""
from ..registry import ToolRegistry

from .file_tools import FILE_TOOLS
from .shell_tools import SHELL_TOOLS
from .code_tools import CODE_TOOLS
from .web_tools import WEB_TOOLS
from .memory_tools import MEMORY_TOOLS
from .search_tools import SEARCH_TOOLS


def register_builtin_tools(registry: ToolRegistry):
    """Register all built-in tools in the registry."""
    all_tools = (
        FILE_TOOLS +
        SHELL_TOOLS +
        CODE_TOOLS +
        WEB_TOOLS +
        MEMORY_TOOLS +
        SEARCH_TOOLS
    )
    registry.register_many(all_tools)
    return len(all_tools)
```

### 2.10 — Testes Phase 2

```python
# packages/backend/tests/engine/test_tools.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from src.engine.tools.base import (
    ToolDefinition, ToolUseContext, build_tool,
    ToolCategory, ExecutionMode, PermissionLevel,
)
from src.engine.tools.registry import ToolRegistry
from src.engine.types import ToolCall


@build_tool(
    name="test_concurrent",
    description="Test concurrent tool",
    execution_mode=ExecutionMode.CONCURRENT,
    parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
)
async def mock_concurrent(ctx, args):
    return {"result": args.get("x", 0) * 2}


@build_tool(
    name="test_serial",
    description="Test serial tool",
    execution_mode=ExecutionMode.SERIAL,
)
async def mock_serial(ctx, args):
    return {"result": "serial_done"}


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(mock_concurrent)
    r.register(mock_serial)
    return r


def test_register_and_lookup(registry):
    tool = registry.get("test_concurrent")
    assert tool is not None
    assert tool.execution_mode == ExecutionMode.CONCURRENT


def test_partition_tools(registry):
    calls = [
        ToolCall(id="1", tool_name="test_concurrent"),
        ToolCall(id="2", tool_name="test_serial"),
        ToolCall(id="3", tool_name="test_concurrent"),
    ]
    concurrent, serial = registry.partition_tools(calls)
    assert len(concurrent) == 2
    assert len(serial) == 1


def test_function_declarations(registry):
    decls = registry.get_function_declarations()
    assert len(decls) == 2
    names = {d["name"] for d in decls}
    assert "test_concurrent" in names
    assert "test_serial" in names


@pytest.mark.asyncio
async def test_execute_batch(registry):
    ctx = ToolUseContext(
        model_registry=MagicMock(),
        tool_registry=registry,
    )
    calls = [
        ToolCall(id="1", tool_name="test_concurrent", arguments={"x": 5}),
        ToolCall(id="2", tool_name="test_serial", arguments={}),
    ]
    results = await registry.execute_batch(calls, ctx)
    assert len(results) == 2
    assert results[0].output["result"] == 10
    assert results[1].output["result"] == "serial_done"


@pytest.mark.asyncio
async def test_unknown_tool(registry):
    ctx = ToolUseContext(model_registry=MagicMock(), tool_registry=registry)
    calls = [ToolCall(id="1", tool_name="nonexistent")]
    results = await registry.execute_batch(calls, ctx)
    assert results[0].is_error
    assert "Unknown tool" in results[0].error
```

---

## Phase 3 - Core Query Engine

**Dependências:** Phase 0, Phase 1, Phase 2
**Arquivos a criar:**
- `packages/backend/src/engine/query_engine.py`

### Conceito

O QueryEngine é o coração do sistema V4. É um **async generator** que implementa o loop agentic:

```
User message → LLM call → Tool calls? → Execute tools → Feed results back → Repeat
```

Inspirado diretamente em `query.ts` do Claude Code, adaptado para Python com `async def run() -> AsyncGenerator[AgentEvent, None]`.

### 3.1 — `query_engine.py`

```python
"""
Core Query Engine - The agentic loop.

This is the heart of the V4 Engine. It implements an async generator
that yields AgentEvent objects for real-time streaming to the frontend.

Inspired by Claude Code's query.ts:
1. Build system prompt + history
2. Call LLM with tools
3. If tool_calls in response → execute tools → add results to history → loop
4. If no tool_calls → yield final response → stop
5. If context too large → compact → continue
6. If max iterations → force stop

The async generator pattern allows the frontend to consume events
in real-time via WebSocket without blocking.
"""
import asyncio
import logging
import time
from typing import AsyncGenerator, Optional

from .types import (
    Message, Role, ToolCall, ToolResult, LLMResponse,
    EngineState, StopReason, ContinuationDecision, EngineGenerator,
)
from .events import AgentEvent, EventType
from .errors import (
    EngineError, ProviderError, RateLimitError,
    ContextWindowError, MaxIterationsError,
    PermissionDeniedError, ToolExecutionError,
)
from .model_registry import ModelRegistry
from .tools.registry import ToolRegistry
from .tools.base import ToolUseContext

logger = logging.getLogger("ahri.engine.query")


class QueryEngine:
    """
    The core agentic loop as an async generator.

    Usage:
        engine = QueryEngine(model_registry, tool_registry, settings)
        async for event in engine.run(goal, system_prompt, model):
            send_to_websocket(event.to_dict())
    """

    def __init__(
        self,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        settings=None,
        permission_manager=None,
        hook_manager=None,
        compact_manager=None,
    ):
        self.model_registry = model_registry
        self.tool_registry = tool_registry
        self.settings = settings
        self.permission_manager = permission_manager
        self.hook_manager = hook_manager
        self.compact_manager = compact_manager

    async def run(
        self,
        goal: str,
        system_prompt: str = "",
        model: str = "fast",
        max_iterations: int = 50,
        context: Optional[dict] = None,
        parent_id: Optional[str] = None,
        depth: int = 0,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run the agentic loop.

        Args:
            goal: User's goal/message
            system_prompt: System prompt for the LLM
            model: Model alias or ID
            max_iterations: Safety limit
            context: Additional context (dependencies, etc.)
            parent_id: Parent execution ID (for sub-agents)
            depth: Nesting depth (0 = root)

        Yields:
            AgentEvent objects for real-time streaming
        """
        # Initialize state
        state = self._init_state(goal, system_prompt, model, max_iterations, parent_id, depth)

        yield AgentEvent.engine_start(state.execution_id, model, goal)

        try:
            # Main agentic loop
            while state.iteration < state.max_iterations and not state.is_cancelled:
                state.iteration += 1

                yield AgentEvent(
                    type=EventType.ITERATION_START,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={"total_tokens": state.total_tokens},
                )

                # ── Step 1: Call LLM ──
                try:
                    tools = self.tool_registry.get_function_declarations()

                    yield AgentEvent(
                        type=EventType.LLM_REQUEST,
                        execution_id=state.execution_id,
                        iteration=state.iteration,
                        data={"model": state.model, "message_count": len(state.messages)},
                    )

                    llm_response = await self._call_llm(state, tools)

                    state.total_input_tokens += llm_response.input_tokens
                    state.total_output_tokens += llm_response.output_tokens

                    yield AgentEvent(
                        type=EventType.LLM_RESPONSE,
                        execution_id=state.execution_id,
                        iteration=state.iteration,
                        data={
                            "has_tool_calls": llm_response.has_tool_calls,
                            "tool_count": len(llm_response.tool_calls),
                            "content_preview": llm_response.content[:200] if llm_response.content else "",
                            "input_tokens": llm_response.input_tokens,
                            "output_tokens": llm_response.output_tokens,
                            "thinking": llm_response.thinking[:500] if llm_response.thinking else None,
                        },
                    )

                except RateLimitError as e:
                    yield AgentEvent.error(state.execution_id, f"Rate limit: {e}", "RATE_LIMIT")
                    await asyncio.sleep(e.retry_after or 5)
                    continue

                except ContextWindowError:
                    # Auto-compact and retry
                    yield AgentEvent(type=EventType.COMPACT_START, execution_id=state.execution_id)
                    await self._compact_context(state)
                    yield AgentEvent(type=EventType.COMPACT_END, execution_id=state.execution_id)
                    continue

                except ProviderError as e:
                    yield AgentEvent.error(state.execution_id, str(e), e.code)
                    if e.retryable:
                        await asyncio.sleep(2)
                        continue
                    break

                # ── Step 2: Check if LLM wants to use tools ──
                if not llm_response.has_tool_calls:
                    # No tools → final response
                    if llm_response.content:
                        # Stream the text content
                        yield AgentEvent.text_chunk(
                            state.execution_id,
                            llm_response.content,
                            state.iteration,
                        )

                    # Add assistant message to history
                    state.add_message(Message(
                        role=Role.ASSISTANT,
                        content=llm_response.content,
                        token_count=llm_response.output_tokens,
                    ))

                    yield AgentEvent(
                        type=EventType.FINAL_RESPONSE,
                        execution_id=state.execution_id,
                        data={
                            "content": llm_response.content,
                            "total_tokens": state.total_tokens,
                            "iterations": state.iteration,
                        },
                    )
                    break

                # ── Step 3: Execute tool calls ──
                # Add assistant message with tool calls
                state.add_message(Message(
                    role=Role.ASSISTANT,
                    content=llm_response.content,
                    tool_calls=llm_response.tool_calls,
                    token_count=llm_response.output_tokens,
                ))

                # Execute each tool with events
                tool_results = await self._execute_tools(state, llm_response.tool_calls)

                # Add tool results to history
                for result in tool_results:
                    state.add_message(Message(
                        role=Role.TOOL_RESULT,
                        content=str(result.output) if not result.is_error else f"Error: {result.error}",
                        tool_results=[result],
                        metadata={"tool_name": result.tool_name},
                    ))

                # ── Step 4: Check if compaction needed ──
                decision = self._decide_continuation(state)
                if decision == ContinuationDecision.COMPACT:
                    yield AgentEvent(type=EventType.COMPACT_START, execution_id=state.execution_id)
                    await self._compact_context(state)
                    yield AgentEvent(type=EventType.COMPACT_END, execution_id=state.execution_id)

                yield AgentEvent(
                    type=EventType.ITERATION_END,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={"total_tokens": state.total_tokens},
                )

            # Loop ended
            if state.iteration >= state.max_iterations:
                yield AgentEvent.error(
                    state.execution_id,
                    f"Max iterations reached ({state.max_iterations})",
                    "MAX_ITERATIONS",
                )

        except asyncio.CancelledError:
            yield AgentEvent(
                type=EventType.CANCELLED,
                execution_id=state.execution_id,
                data={"reason": "User cancelled"},
            )

        except Exception as e:
            logger.exception(f"Engine error: {e}")
            yield AgentEvent.error(state.execution_id, str(e), "INTERNAL_ERROR")

        finally:
            yield AgentEvent.engine_stop(
                state.execution_id,
                "completed" if not state.is_cancelled else "cancelled",
                state.total_tokens,
            )

    def _init_state(
        self, goal: str, system_prompt: str, model: str,
        max_iterations: int, parent_id: Optional[str], depth: int,
    ) -> EngineState:
        """Initialize engine state for a new execution."""
        state = EngineState(
            model=model,
            system_prompt=system_prompt or self._build_default_system_prompt(),
            max_iterations=max_iterations,
            depth=depth,
            parent_id=parent_id,
        )

        # Add user message
        state.add_message(Message(role=Role.USER, content=goal))

        return state

    def _build_default_system_prompt(self) -> str:
        """Build a default system prompt listing available tools."""
        tools = self.tool_registry.get_enabled()
        tool_list = "\n".join(f"- {t.name}: {t.description}" for t in tools)

        return f"""You are Ahri, an AI assistant with access to tools.

Available tools:
{tool_list}

Use tools when needed to complete the user's request.
Always explain what you're doing before and after using tools.
If a tool fails, try an alternative approach.
"""

    async def _call_llm(self, state: EngineState, tools: list[dict]) -> LLMResponse:
        """Call the LLM with current state."""
        # Build messages in provider format
        messages = []

        # System prompt as first message
        if state.system_prompt:
            messages.append({"role": "system", "content": state.system_prompt})

        # Conversation history
        for msg in state.messages:
            if msg.role == Role.TOOL_RESULT:
                messages.append({
                    "role": "tool_result",
                    "content": msg.content,
                    "tool_name": msg.metadata.get("tool_name", ""),
                })
            else:
                entry = {"role": msg.role.value, "content": msg.content}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {"name": tc.tool_name, "arguments": tc.arguments}
                        for tc in msg.tool_calls
                    ]
                messages.append(entry)

        # Call model registry
        return await self.model_registry.call(
            model_or_alias=state.model,
            messages=messages,
            tools=tools if tools else None,
        )

    async def _execute_tools(
        self, state: EngineState, tool_calls: list[ToolCall],
    ) -> list[ToolResult]:
        """Execute tool calls with permission checks and events."""
        # Build context for tools
        context = ToolUseContext(
            model_registry=self.model_registry,
            tool_registry=self.tool_registry,
            permission_manager=self.permission_manager,
            hook_manager=self.hook_manager,
            execution_id=state.execution_id,
            default_model=state.model,
            settings=self.settings,
        )

        results = []
        for call in tool_calls:
            # Permission check
            if self.permission_manager:
                decision = await self.permission_manager.check(call.tool_name, call.arguments)
                if decision.value == "deny":
                    results.append(ToolResult(
                        tool_call_id=call.id,
                        tool_name=call.tool_name,
                        error=f"Permission denied for tool: {call.tool_name}",
                    ))
                    continue

            # Pre-hook
            if self.hook_manager:
                await self.hook_manager.emit("pre_tool_use", {
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                })

        # Execute batch (with concurrent/serial partitioning)
        batch_results = await self.tool_registry.execute_batch(tool_calls, context)

        # Post-hooks
        if self.hook_manager:
            for result in batch_results:
                await self.hook_manager.emit("post_tool_use", {
                    "tool_name": result.tool_name,
                    "output": result.output,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                })

        return batch_results

    def _decide_continuation(self, state: EngineState) -> ContinuationDecision:
        """
        Decide whether to continue, stop, or compact.
        Inspired by Claude Code's continuation logic.
        """
        # Check context window usage
        threshold = getattr(self.settings, 'engine_compact_threshold', 0.80)

        # Estimate context usage
        try:
            model_info = self.model_registry.resolve(state.model)
            context_window = model_info.capabilities.context_window
            usage_ratio = state.total_tokens / context_window if context_window > 0 else 0

            if usage_ratio > threshold:
                return ContinuationDecision.COMPACT
        except KeyError:
            pass

        return ContinuationDecision.CONTINUE

    async def _compact_context(self, state: EngineState):
        """
        Compact the conversation history to free context window space.

        Strategy: Keep system prompt + first user message + last N messages.
        Summarize the middle using the cheapest available model.
        """
        if self.compact_manager:
            state.messages = await self.compact_manager.compact(
                state.messages,
                keep_recent=getattr(self.settings, 'engine_compact_keep_recent', 4),
            )
        else:
            # Simple fallback: keep first message + last N messages
            keep = getattr(self.settings, 'engine_compact_keep_recent', 4)
            if len(state.messages) > keep + 1:
                first_msg = state.messages[0]
                recent = state.messages[-keep:]
                summary = Message(
                    role=Role.SYSTEM,
                    content=f"[Previous {len(state.messages) - keep - 1} messages were compacted. "
                            f"Key context has been preserved in the remaining messages.]",
                )
                state.messages = [first_msg, summary] + recent

        logger.info(f"Compacted context to {len(state.messages)} messages")
```

### 3.2 — Testes Phase 3

```python
# packages/backend/tests/engine/test_query_engine.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.query_engine import QueryEngine
from src.engine.types import LLMResponse, ToolCall, StopReason, ModelInfo, ModelCapabilities
from src.engine.events import EventType
from src.engine.tools.registry import ToolRegistry
from src.engine.tools.base import ToolDefinition, ExecutionMode


@pytest.fixture
def mock_registry():
    registry = MagicMock()

    # First call: response with tool call
    # Second call: final response (no tools)
    registry.call = AsyncMock(side_effect=[
        LLMResponse(
            content="Let me read the file.",
            tool_calls=[ToolCall(id="1", tool_name="file_read", arguments={"path": "test.txt"})],
            stop_reason=StopReason.TOOL_USE,
            input_tokens=100,
            output_tokens=50,
        ),
        LLMResponse(
            content="The file contains: Hello World",
            stop_reason=StopReason.END_TURN,
            input_tokens=200,
            output_tokens=30,
        ),
    ])

    registry.resolve = MagicMock(return_value=ModelInfo(
        id="gemini-2.5-flash", provider="gemini",
        capabilities=ModelCapabilities(context_window=1048576),
    ))

    return registry


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()

    async def mock_handler(ctx, args):
        return {"content": "Hello World", "path": args.get("path", "")}

    reg.register(ToolDefinition(
        name="file_read",
        description="Read a file",
        execution_mode=ExecutionMode.CONCURRENT,
        handler=mock_handler,
    ))
    return reg


@pytest.mark.asyncio
async def test_basic_loop(mock_registry, tool_registry):
    engine = QueryEngine(mock_registry, tool_registry)

    events = []
    async for event in engine.run("Read test.txt", model="fast", max_iterations=5):
        events.append(event)

    event_types = [e.type for e in events]

    assert EventType.ENGINE_START in event_types
    assert EventType.LLM_REQUEST in event_types
    assert EventType.LLM_RESPONSE in event_types
    assert EventType.TOOL_USE_START in event_types or EventType.FINAL_RESPONSE in event_types
    assert EventType.ENGINE_STOP in event_types


@pytest.mark.asyncio
async def test_no_tools_response():
    """Test direct response without tool use."""
    registry = MagicMock()
    registry.call = AsyncMock(return_value=LLMResponse(
        content="Hello! How can I help?",
        stop_reason=StopReason.END_TURN,
        input_tokens=50,
        output_tokens=20,
    ))
    registry.resolve = MagicMock(return_value=ModelInfo(
        id="test", provider="gemini",
        capabilities=ModelCapabilities(context_window=100000),
    ))

    engine = QueryEngine(registry, ToolRegistry())

    events = []
    async for event in engine.run("Hi"):
        events.append(event)

    # Should have text_chunk and final_response
    types = [e.type for e in events]
    assert EventType.FINAL_RESPONSE in types
    assert EventType.ENGINE_STOP in types

    final = next(e for e in events if e.type == EventType.FINAL_RESPONSE)
    assert final.data["content"] == "Hello! How can I help?"
```

---

## Phase 4 - Permission System

**Dependências:** Phase 0, Phase 2
**Arquivos a criar:**
- `packages/backend/src/engine/permissions/__init__.py`
- `packages/backend/src/engine/permissions/base.py`
- `packages/backend/src/engine/permissions/rules.py`

### Conceito

Inspirado em `permissions.ts` do Claude Code. Sistema de permissões em camadas:
1. **Tool-level defaults** (SAFE/CONFIRM/DANGEROUS definido no ToolDefinition)
2. **Rules** (allow/deny/ask por tool name, category, ou pattern de argumentos)
3. **Dangerous pattern detection** (detecta rm -rf, format, etc. nos argumentos)
4. **Permission modes** (auto: usa defaults, ask: sempre pergunta, trust: auto-approve tudo)

### 4.1 — `permissions/base.py`

```python
"""
Permission manager for tool execution.
Evaluates whether a tool call should be allowed, denied, or needs user confirmation.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from ..types import PermissionDecision

logger = logging.getLogger("ahri.engine.permissions")


class RuleAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionRule:
    """A single permission rule."""
    tool_pattern: str           # Glob pattern for tool name (e.g., "file_*", "shell_*")
    action: RuleAction
    arg_patterns: dict = field(default_factory=dict)  # argument name → regex pattern
    reason: str = ""
    priority: int = 0           # Higher priority rules evaluated first


# Dangerous patterns in tool arguments
DANGEROUS_PATTERNS = [
    (r"rm\s+-rf", "Recursive forced deletion"),
    (r"format\s+[A-Z]:", "Disk formatting"),
    (r"mkfs\.", "Filesystem creation"),
    (r"dd\s+if=", "Direct disk write"),
    (r">\s*/dev/sd", "Write to block device"),
    (r"shutdown|reboot|halt", "System shutdown/reboot"),
    (r"DROP\s+TABLE|DROP\s+DATABASE", "Database destruction"),
    (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "Unfiltered DELETE (no WHERE)"),
]


class PermissionManager:
    """
    Evaluates tool permissions using layered rules.

    Evaluation order:
    1. Check permission mode (trust → always allow, ask → always ask)
    2. Check explicit rules (highest priority first)
    3. Check dangerous argument patterns
    4. Fall back to tool's default permission level
    """

    def __init__(self, mode: str = "auto"):
        """
        Args:
            mode: "auto" (use rules + defaults), "ask" (always ask), "trust" (always allow)
        """
        self.mode = mode
        self.rules: list[PermissionRule] = []
        self._compile_dangerous_patterns()

    def _compile_dangerous_patterns(self):
        self._dangerous = [(re.compile(p, re.IGNORECASE), desc) for p, desc in DANGEROUS_PATTERNS]

    def add_rule(self, rule: PermissionRule):
        """Add a permission rule."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: -r.priority)

    async def check(self, tool_name: str, arguments: dict) -> PermissionDecision:
        """
        Check if a tool call is allowed.

        Returns:
            PermissionDecision.ALLOW, DENY, or ASK
        """
        # Mode overrides
        if self.mode == "trust":
            return PermissionDecision.ALLOW
        if self.mode == "ask":
            return PermissionDecision.ASK

        # Check explicit rules
        for rule in self.rules:
            if self._matches_tool(rule.tool_pattern, tool_name):
                if self._matches_args(rule.arg_patterns, arguments):
                    return PermissionDecision(rule.action.value)

        # Check dangerous patterns in arguments
        args_str = str(arguments)
        for pattern, description in self._dangerous:
            if pattern.search(args_str):
                logger.warning(f"Dangerous pattern detected in {tool_name}: {description}")
                return PermissionDecision.DENY

        # Fall back to tool's default permission level
        return PermissionDecision.ALLOW

    def _matches_tool(self, pattern: str, tool_name: str) -> bool:
        """Check if tool name matches a glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(tool_name, pattern)

    def _matches_args(self, arg_patterns: dict, arguments: dict) -> bool:
        """Check if arguments match the rule's arg patterns."""
        if not arg_patterns:
            return True
        for key, pattern in arg_patterns.items():
            value = str(arguments.get(key, ""))
            if not re.search(pattern, value):
                return False
        return True
```

---

## Phase 5 - Hook System

**Dependências:** Phase 0
**Arquivos a criar:**
- `packages/backend/src/engine/hooks/__init__.py`
- `packages/backend/src/engine/hooks/manager.py`

### Conceito

Inspirado em `hooks.ts` do Claude Code. Hooks são callbacks executados em eventos do engine:
- `pre_tool_use` — antes de executar uma tool
- `post_tool_use` — depois de executar uma tool
- `session_start` — quando uma execução começa
- `session_end` — quando uma execução termina
- `on_error` — quando um erro ocorre
- `on_compact` — quando context é compactado

### 5.1 — `hooks/manager.py`

```python
"""
Hook system for the V4 Engine.
Allows plugins and configurations to react to engine events.
"""
import asyncio
import logging
from typing import Any, Callable, Awaitable, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("ahri.engine.hooks")


class HookEvent(str, Enum):
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    ON_ERROR = "on_error"
    ON_COMPACT = "on_compact"
    ON_LLM_REQUEST = "on_llm_request"
    ON_LLM_RESPONSE = "on_llm_response"
    ON_AGENT_SPAWN = "on_agent_spawn"


# Hook handler type: receives event data dict, returns optional modified data
HookHandler = Callable[[dict[str, Any]], Awaitable[Optional[dict[str, Any]]]]


@dataclass
class HookRegistration:
    """A registered hook handler."""
    event: HookEvent
    handler: HookHandler
    name: str = ""
    priority: int = 0           # Higher runs first
    plugin_name: str = ""       # Which plugin registered this
    timeout: int = 30           # Max execution time in seconds


class HookManager:
    """
    Central hook manager.
    Maintains a registry of handlers per event type.
    Executes handlers in priority order.
    """

    def __init__(self, default_timeout: int = 30):
        self._hooks: dict[HookEvent, list[HookRegistration]] = {
            event: [] for event in HookEvent
        }
        self.default_timeout = default_timeout

    def register(self, registration: HookRegistration):
        """Register a hook handler."""
        self._hooks[registration.event].append(registration)
        self._hooks[registration.event].sort(key=lambda h: -h.priority)
        logger.info(f"Hook registered: {registration.name} on {registration.event.value}")

    def on(self, event: HookEvent, name: str = "", priority: int = 0):
        """Decorator to register a hook handler."""
        def decorator(handler: HookHandler):
            self.register(HookRegistration(
                event=event,
                handler=handler,
                name=name or handler.__name__,
                priority=priority,
            ))
            return handler
        return decorator

    async def emit(self, event: str | HookEvent, data: dict[str, Any] = None) -> dict[str, Any]:
        """
        Emit an event and run all registered handlers.

        Handlers run in priority order. Each handler receives the data dict
        and can optionally return modified data for the next handler.

        Args:
            event: Event type
            data: Event data (mutable, passed through handler chain)

        Returns:
            Final data dict after all handlers have processed it
        """
        if isinstance(event, str):
            try:
                event = HookEvent(event)
            except ValueError:
                logger.warning(f"Unknown hook event: {event}")
                return data or {}

        data = data or {}
        handlers = self._hooks.get(event, [])

        for hook in handlers:
            try:
                result = await asyncio.wait_for(
                    hook.handler(data),
                    timeout=hook.timeout or self.default_timeout,
                )
                # If handler returns modified data, use it
                if result is not None and isinstance(result, dict):
                    data = result
            except asyncio.TimeoutError:
                logger.error(f"Hook '{hook.name}' timed out ({hook.timeout}s)")
            except Exception as e:
                logger.error(f"Hook '{hook.name}' failed: {e}")

        return data

    def clear(self, event: Optional[HookEvent] = None):
        """Clear hooks for an event, or all hooks."""
        if event:
            self._hooks[event] = []
        else:
            for e in HookEvent:
                self._hooks[e] = []

    @property
    def hook_count(self) -> int:
        return sum(len(h) for h in self._hooks.values())
```

---

## Phase 6 - Context Window Management

**Dependências:** Phase 0, Phase 1, Phase 3
**Arquivos a criar:**
- `packages/backend/src/engine/compact/__init__.py`
- `packages/backend/src/engine/compact/manager.py`

### Conceito

Inspirado em `compact/` do Claude Code. Três estratégias de compactação:
1. **Auto-compact**: Ativa quando token usage > threshold (80% do context window)
2. **Reactive compact**: Ativa quando API retorna erro de context window overflow
3. **Snip compact**: Remove blocos de output muito grandes de tool results

### 6.1 — `compact/manager.py`

```python
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
            role=Role.SYSTEM,
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
```

---

## Phase 7 - Agent Spawning & Coordination

**Dependências:** Phase 0-3
**Arquivos a criar:**
- `packages/backend/src/engine/agents/__init__.py`
- `packages/backend/src/engine/agents/spawner.py`
- `packages/backend/src/engine/agents/definitions.py`

### Conceito

Inspirado em `AgentTool/runAgent.ts` do Claude Code. Sub-agentes são QueryEngine instances com:
- Contexto isolado (próprio message history)
- Depth tracking (max 3 levels)
- System prompt customizado por tipo de agente
- Resultado retornado como tool result para o agente pai

### 7.1 — `agents/spawner.py`

```python
"""
Agent spawner - creates and manages sub-agent executions.

Sub-agents are isolated QueryEngine instances that run as tool calls.
The parent agent can spawn sub-agents to handle complex subtasks.

Depth limits prevent infinite recursion (max 3 levels by default).
"""
import logging
from typing import Optional, Any

from ..types import EngineState
from ..events import AgentEvent, EventType
from ..tools.base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)
from ..errors import SubAgentError

logger = logging.getLogger("ahri.engine.agents")


@build_tool(
    name="spawn_agent",
    description="Spawn a sub-agent to handle a complex subtask. The sub-agent has its own context and tools. Use this for tasks that require focused, multi-step work.",
    category=ToolCategory.AGENT,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The specific goal for the sub-agent",
            },
            "agent_type": {
                "type": "string",
                "enum": ["general", "code", "research", "analysis"],
                "description": "Type of sub-agent (affects system prompt)",
                "default": "general",
            },
            "model": {
                "type": "string",
                "description": "Model to use (alias or ID). Default: same as parent.",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Max iterations for sub-agent (default: 20)",
                "default": 20,
            },
        },
        "required": ["goal"],
    },
)
async def spawn_agent(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    """Spawn a sub-agent with isolated context."""
    import json

    goal = args["goal"]
    agent_type = args.get("agent_type", "general")
    model = args.get("model", ctx.default_model)
    max_iterations = args.get("max_iterations", 20)

    # Get current depth from context metadata
    current_depth = ctx.metadata.get("depth", 0)
    max_depth = ctx.metadata.get("max_depth", 3)

    if current_depth >= max_depth:
        return json.dumps({
            "error": f"Max agent depth reached ({max_depth}). Cannot spawn more sub-agents.",
            "depth": current_depth,
        })

    # Get system prompt for agent type
    system_prompt = AGENT_PROMPTS.get(agent_type, AGENT_PROMPTS["general"])

    # Import here to avoid circular import
    from ..query_engine import QueryEngine

    engine = QueryEngine(
        model_registry=ctx.model_registry,
        tool_registry=ctx.tool_registry,
        settings=ctx.settings,
        permission_manager=ctx.permission_manager,
        hook_manager=ctx.hook_manager,
    )

    # Collect results
    final_content = ""
    total_tokens = 0
    iterations = 0

    async for event in engine.run(
        goal=goal,
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
        parent_id=ctx.execution_id,
        depth=current_depth + 1,
    ):
        if event.type == EventType.FINAL_RESPONSE:
            final_content = event.data.get("content", "")
            total_tokens = event.data.get("total_tokens", 0)
            iterations = event.data.get("iterations", 0)
        elif event.type == EventType.ERROR:
            return json.dumps({
                "error": event.data.get("error", "Sub-agent failed"),
                "agent_type": agent_type,
            })

    return json.dumps({
        "result": final_content,
        "agent_type": agent_type,
        "iterations": iterations,
        "total_tokens": total_tokens,
        "depth": current_depth + 1,
    })


# System prompts for different agent types
AGENT_PROMPTS = {
    "general": """You are a sub-agent handling a specific task.
Complete the task efficiently using the available tools.
Return a clear, concise result.""",

    "code": """You are a code-focused sub-agent.
Your job is to analyze, write, or modify code.
Use file_read and file_write tools to work with files.
Use code_analyze for review and code_generate for new code.
Always test your changes when possible.""",

    "research": """You are a research sub-agent.
Your job is to gather and synthesize information.
Use web_search and web_fetch to find information.
Use memory_search to check existing knowledge.
Provide a structured summary of your findings.""",

    "analysis": """You are an analysis sub-agent.
Your job is to deeply analyze data, code, or documents.
Provide structured analysis with clear conclusions.
Use code_analyze for code review.
Be thorough but concise.""",
}


AGENT_TOOLS = [spawn_agent]
```

---

## Phase 8 - Plugin/Skill System

**Dependências:** Phase 0-5
**Arquivos a criar:**
- `packages/backend/src/engine/plugins/__init__.py`
- `packages/backend/src/engine/plugins/loader.py`
- `packages/backend/src/engine/plugins/schema.py`

### Conceito

Inspirado em `pluginLoader.ts` do Claude Code. Plugins são diretórios com:
- `plugin.json` — manifest com nome, versão, tools, hooks, agents
- `tools/` — Python files with `@build_tool` decorated functions
- `hooks/` — Python files with hook handlers
- `agents/` — YAML agent definitions

### 8.1 — `plugins/schema.py`

```python
"""
Plugin manifest schema.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PluginManifest:
    """Schema for plugin.json manifest file."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""

    # Entry points
    tools_dir: str = "tools"        # Directory containing tool modules
    hooks_dir: str = "hooks"        # Directory containing hook modules
    agents_dir: str = "agents"      # Directory containing agent YAML files

    # Dependencies
    requires: list[str] = field(default_factory=list)  # Required plugin names
    python_requires: str = ">=3.11"

    # Capabilities
    enabled: bool = True
    tool_names: list[str] = field(default_factory=list)  # Explicitly declared tools
    hook_events: list[str] = field(default_factory=list)  # Events this plugin hooks into

    # Metadata
    homepage: str = ""
    license: str = ""
```

### 8.2 — `plugins/loader.py`

```python
"""
Plugin loader - discovers, validates, and loads plugins.
"""
import json
import importlib.util
import logging
from pathlib import Path
from typing import Optional

from .schema import PluginManifest
from ..tools.registry import ToolRegistry
from ..tools.base import ToolDefinition
from ..hooks.manager import HookManager

logger = logging.getLogger("ahri.engine.plugins")


class PluginLoader:
    """
    Discovers and loads plugins from configured directories.
    """

    def __init__(self, tool_registry: ToolRegistry, hook_manager: Optional[HookManager] = None):
        self.tool_registry = tool_registry
        self.hook_manager = hook_manager
        self._loaded: dict[str, PluginManifest] = {}

    def discover(self, plugin_dirs: list[str]) -> list[PluginManifest]:
        """Discover all plugins in the given directories."""
        manifests = []
        for dir_path in plugin_dirs:
            p = Path(dir_path)
            if not p.exists():
                logger.warning(f"Plugin directory not found: {dir_path}")
                continue

            for child in p.iterdir():
                if child.is_dir():
                    manifest_file = child / "plugin.json"
                    if manifest_file.exists():
                        try:
                            manifest = self._load_manifest(manifest_file)
                            manifests.append(manifest)
                        except Exception as e:
                            logger.error(f"Failed to load plugin manifest {manifest_file}: {e}")

        return manifests

    def load(self, plugin_dir: Path, manifest: PluginManifest) -> int:
        """
        Load a single plugin.

        Returns:
            Number of tools registered
        """
        if manifest.name in self._loaded:
            logger.warning(f"Plugin already loaded: {manifest.name}")
            return 0

        tools_loaded = 0

        # Load tools
        tools_path = plugin_dir / manifest.tools_dir
        if tools_path.exists():
            for py_file in tools_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                tools = self._load_tools_from_file(py_file, manifest.name)
                tools_loaded += len(tools)

        # Load hooks
        hooks_path = plugin_dir / manifest.hooks_dir
        if hooks_path.exists() and self.hook_manager:
            for py_file in hooks_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                self._load_hooks_from_file(py_file, manifest.name)

        self._loaded[manifest.name] = manifest
        logger.info(f"Loaded plugin '{manifest.name}' v{manifest.version}: {tools_loaded} tools")
        return tools_loaded

    def load_all(self, plugin_dirs: list[str]) -> int:
        """Discover and load all plugins. Returns total tools loaded."""
        total = 0
        manifests = self.discover(plugin_dirs)

        for manifest in manifests:
            # Find the plugin directory
            for dir_path in plugin_dirs:
                p = Path(dir_path)
                plugin_path = None
                for child in p.iterdir():
                    mf = child / "plugin.json"
                    if mf.exists():
                        try:
                            m = self._load_manifest(mf)
                            if m.name == manifest.name:
                                plugin_path = child
                                break
                        except Exception:
                            pass
                if plugin_path:
                    total += self.load(plugin_path, manifest)
                    break

        return total

    def _load_manifest(self, manifest_file: Path) -> PluginManifest:
        """Parse plugin.json into PluginManifest."""
        with open(manifest_file) as f:
            data = json.load(f)
        return PluginManifest(**data)

    def _load_tools_from_file(self, py_file: Path, plugin_name: str) -> list[ToolDefinition]:
        """Dynamically load tools from a Python file."""
        tools = []
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_name}_{py_file.stem}", py_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for exported tool lists (e.g., FILE_TOOLS, MY_TOOLS)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, list):
                    for item in attr:
                        if isinstance(item, ToolDefinition):
                            item.plugin_name = plugin_name
                            item.is_builtin = False
                            self.tool_registry.register(item)
                            tools.append(item)
                elif isinstance(attr, ToolDefinition):
                    attr.plugin_name = plugin_name
                    attr.is_builtin = False
                    self.tool_registry.register(attr)
                    tools.append(attr)

        except Exception as e:
            logger.error(f"Failed to load tools from {py_file}: {e}")

        return tools

    def _load_hooks_from_file(self, py_file: Path, plugin_name: str):
        """Dynamically load hooks from a Python file."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{plugin_name}_hooks_{py_file.stem}", py_file
            )
            module = importlib.util.module_from_spec(spec)

            # Inject hook_manager so the module can register hooks
            module.hook_manager = self.hook_manager
            spec.loader.exec_module(module)

        except Exception as e:
            logger.error(f"Failed to load hooks from {py_file}: {e}")

    @property
    def loaded_plugins(self) -> dict[str, PluginManifest]:
        return dict(self._loaded)
```

---

## Phase 9 - Worker Migration

**Dependências:** Phase 0-2
**Arquivos a criar:**
- `packages/backend/src/engine/migration/__init__.py`
- `packages/backend/src/engine/migration/worker_adapter.py`

### Conceito

Para manter backward-compatibility durante a transição, criamos um adapter que wrappa os workers existentes do V3 como tools do V4. Isso permite que o novo engine use os workers existentes sem reescrevê-los de uma vez.

### 9.1 — `migration/worker_adapter.py`

```python
"""
Adapter to wrap V3 Workers as V4 Tools.

This allows gradual migration: existing workers continue to work
through the adapter while new tools are written natively.

Usage:
    from src.services.workers.code_worker import CodeWorker
    tool = WorkerToolAdapter.from_worker(code_worker, "code_analyze")
    registry.register(tool)
"""
import json
import logging
from typing import Any, Optional

from ..tools.base import (
    ToolDefinition, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)

logger = logging.getLogger("ahri.engine.migration")


class WorkerToolAdapter:
    """
    Wraps a V3 BaseWorker as a V4 ToolDefinition.

    Maps the worker's execute() method to a tool handler function,
    bridging the V3 worker architecture (class-based, LLMService dependency)
    with the V4 tool architecture (function-based, ToolUseContext injection).
    """

    @staticmethod
    def from_worker(
        worker,           # BaseWorker instance
        tool_name: str,
        description: str = "",
        category: ToolCategory = ToolCategory.CUSTOM,
        execution_mode: ExecutionMode = ExecutionMode.SERIAL,
        permission_level: PermissionLevel = PermissionLevel.SAFE,
        parameters: Optional[dict] = None,
    ) -> ToolDefinition:
        """
        Create a ToolDefinition that wraps a V3 worker.

        The handler calls worker.execute_with_correction() which internally
        handles ReAct loops and self-correction if enabled.
        """

        async def handler(ctx: ToolUseContext, args: dict[str, Any]) -> str:
            """Adapted handler that bridges V4 context to V3 worker."""
            try:
                # V3 workers need a db session and execution_id
                db = ctx.db
                execution_id = int(ctx.execution_id) if ctx.execution_id.isdigit() else 0

                # Call the worker's execute method
                task = await worker.execute_with_correction(
                    db=db,
                    execution_id=execution_id,
                    input_data=args,
                )

                return json.dumps({
                    "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
                    "output": task.output_data or {},
                    "tokens_used": task.tokens_used or 0,
                    "error": task.error,
                })
            except Exception as e:
                logger.error(f"Worker adapter error for {tool_name}: {e}")
                return json.dumps({"error": str(e)})

        return ToolDefinition(
            name=tool_name,
            description=description or f"Adapted from V3 {worker.worker_type} worker",
            category=category,
            execution_mode=execution_mode,
            permission_level=permission_level,
            parameters=parameters or {"type": "object", "properties": {}},
            handler=handler,
            is_builtin=False,
        )

    @staticmethod
    def adapt_all_workers(
        workers: dict,    # {"RAG": RAGWorker, "Code": CodeWorker, ...}
    ) -> list[ToolDefinition]:
        """
        Adapt all V3 workers to V4 tools.

        Worker type mapping:
        - RAG → rag_search (concurrent)
        - Code → code_worker (serial)
        - Shell → shell_worker (serial)
        - Memory → memory_worker (concurrent)
        - Web → web_worker (concurrent)
        - Vision → vision_worker (serial)
        - Browser → browser_worker (serial)
        - Router → router_worker (concurrent)
        """
        WORKER_CONFIGS = {
            "RAG": ("v3_rag", "Search and synthesize from RAG documents", ToolCategory.MEMORY, ExecutionMode.CONCURRENT),
            "Code": ("v3_code", "Analyze, generate, or review code (V3)", ToolCategory.CODE, ExecutionMode.SERIAL),
            "Shell": ("v3_shell", "File operations and command execution (V3)", ToolCategory.SHELL, ExecutionMode.SERIAL),
            "Memory": ("v3_memory", "Search episodic/profile memories (V3)", ToolCategory.MEMORY, ExecutionMode.CONCURRENT),
            "Web": ("v3_web", "Fetch URLs and scrape web pages (V3)", ToolCategory.WEB, ExecutionMode.CONCURRENT),
            "Vision": ("v3_vision", "Analyze images (V3)", ToolCategory.VISION, ExecutionMode.SERIAL),
            "Browser": ("v3_browser", "Browser automation (V3)", ToolCategory.BROWSER, ExecutionMode.SERIAL),
            "Router": ("v3_router", "Classify and route tasks (V3)", ToolCategory.SYSTEM, ExecutionMode.CONCURRENT),
        }

        tools = []
        for worker_type, worker in workers.items():
            if worker_type in WORKER_CONFIGS:
                name, desc, cat, mode = WORKER_CONFIGS[worker_type]
                tool = WorkerToolAdapter.from_worker(
                    worker, name, desc, cat, mode,
                )
                tools.append(tool)

        return tools
```

---

## Phase 10 - Database Schema

**Dependências:** Phase 0
**Arquivos a modificar:**
- `packages/backend/src/models/database.py`

### Novas tabelas a adicionar

```python
# Add to packages/backend/src/models/database.py

class EngineExecution(Base):
    """V4 Engine execution record."""
    __tablename__ = "engine_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String, unique=True, nullable=False, index=True)
    goal = Column(Text, nullable=False)
    model = Column(String, nullable=False)
    status = Column(String, default="running")  # running, completed, failed, cancelled
    system_prompt = Column(Text, default="")

    # Metrics
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    iterations = Column(Integer, default=0)
    tool_calls_count = Column(Integer, default=0)

    # Sub-agent info
    parent_id = Column(String, nullable=True)
    depth = Column(Integer, default=0)

    # Result
    final_response = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Relationships
    tool_uses = relationship("EngineToolUse", back_populates="execution", cascade="all, delete-orphan")


class EngineToolUse(Base):
    """V4 Engine tool use record."""
    __tablename__ = "engine_tool_uses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String, ForeignKey("engine_executions.execution_id"), nullable=False)
    tool_name = Column(String, nullable=False)
    arguments = Column(JSON, default={})
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, default=0)
    iteration = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    execution = relationship("EngineExecution", back_populates="tool_uses")


class EnginePlugin(Base):
    """Installed plugin record."""
    __tablename__ = "engine_plugins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    version = Column(String, nullable=False)
    description = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    installed_at = Column(DateTime, default=datetime.utcnow)
    config = Column(JSON, default={})
```

### Migration Script

```python
# packages/backend/src/scripts/migrate_engine_v4.py
"""
Migration script for V4 Engine tables.
Run: python -m src.scripts.migrate_engine_v4
"""
import asyncio
from sqlalchemy import text
from ..models.database import engine, Base

async def migrate():
    async with engine.begin() as conn:
        # Create new tables
        await conn.run_sync(Base.metadata.create_all)
        print("V4 Engine tables created successfully")

if __name__ == "__main__":
    asyncio.run(migrate())
```

---

## Phase 11 - Frontend Changes

**Dependências:** Phase 0-3 (backend must have API endpoints)
**Arquivos a criar/modificar:**

### 11.1 — Novos tipos TypeScript

```typescript
// packages/shared/src/types/engine.ts

export interface EngineEvent {
  type: EngineEventType;
  data: Record<string, any>;
  timestamp: number;
  execution_id: string;
  iteration: number;
}

export type EngineEventType =
  | 'engine_start'
  | 'engine_stop'
  | 'iteration_start'
  | 'iteration_end'
  | 'llm_request'
  | 'llm_response'
  | 'tool_use_start'
  | 'tool_use_end'
  | 'tool_permission_ask'
  | 'compact_start'
  | 'compact_end'
  | 'agent_spawn'
  | 'agent_complete'
  | 'text_chunk'
  | 'final_response'
  | 'error'
  | 'cancelled'
  | 'progress';

export interface EngineExecution {
  execution_id: string;
  goal: string;
  model: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  iterations: number;
  total_tokens: number;
  tool_calls_count: number;
  final_response?: string;
  error?: string;
  created_at: string;
  completed_at?: string;
  duration_ms?: number;
  events: EngineEvent[];
}

export interface EngineToolUse {
  tool_name: string;
  arguments: Record<string, any>;
  output?: string;
  error?: string;
  duration_ms: number;
  iteration: number;
}

export interface EngineConfig {
  enabled: boolean;
  default_model: string;
  max_iterations: number;
  permission_mode: 'auto' | 'ask' | 'trust';
  stream_enabled: boolean;
  compact_threshold: number;
  enable_subagents: boolean;
}
```

### 11.2 — Novo Zustand Store

```typescript
// packages/desktop/src/stores/engine-store.ts

import { create } from 'zustand';
import type { EngineEvent, EngineExecution } from '@ahri/shared';

interface EngineState {
  // Current execution
  currentExecution: EngineExecution | null;
  events: EngineEvent[];
  isRunning: boolean;

  // History
  executions: EngineExecution[];

  // WebSocket
  ws: WebSocket | null;

  // Actions
  startExecution: (goal: string, model?: string) => void;
  cancelExecution: () => void;
  handleEvent: (event: EngineEvent) => void;
  clearEvents: () => void;
  loadHistory: () => Promise<void>;
}

export const useEngineStore = create<EngineState>((set, get) => ({
  currentExecution: null,
  events: [],
  isRunning: false,
  executions: [],
  ws: null,

  startExecution: (goal: string, model?: string) => {
    const ws = new WebSocket(
      `ws://localhost:8742/engine/v2/ws?goal=${encodeURIComponent(goal)}&model=${model || 'fast'}`
    );

    ws.onmessage = (msg) => {
      try {
        const event: EngineEvent = JSON.parse(msg.data);
        get().handleEvent(event);
      } catch (e) {
        console.error('Failed to parse engine event:', e);
      }
    };

    ws.onclose = () => {
      set({ isRunning: false, ws: null });
    };

    set({
      ws,
      isRunning: true,
      events: [],
      currentExecution: {
        execution_id: '',
        goal,
        model: model || 'fast',
        status: 'running',
        iterations: 0,
        total_tokens: 0,
        tool_calls_count: 0,
        events: [],
        created_at: new Date().toISOString(),
      },
    });
  },

  cancelExecution: () => {
    const { ws } = get();
    if (ws) {
      ws.send(JSON.stringify({ type: 'cancel' }));
      ws.close();
    }
    set({ isRunning: false, ws: null });
  },

  handleEvent: (event: EngineEvent) => {
    set((state) => {
      const events = [...state.events, event];
      const execution = state.currentExecution
        ? { ...state.currentExecution, events }
        : null;

      // Update execution state based on event type
      if (execution) {
        switch (event.type) {
          case 'engine_start':
            execution.execution_id = event.execution_id;
            execution.status = 'running';
            break;
          case 'engine_stop':
            execution.status = event.data.reason === 'completed' ? 'completed' : 'failed';
            execution.total_tokens = event.data.total_tokens;
            break;
          case 'iteration_end':
            execution.iterations = event.iteration;
            execution.total_tokens = event.data.total_tokens;
            break;
          case 'tool_use_end':
            execution.tool_calls_count += 1;
            break;
          case 'final_response':
            execution.final_response = event.data.content;
            break;
          case 'error':
            execution.error = event.data.error;
            break;
        }
      }

      return { events, currentExecution: execution };
    });
  },

  clearEvents: () => set({ events: [], currentExecution: null }),

  loadHistory: async () => {
    try {
      const response = await fetch('http://localhost:8742/engine/v2/executions');
      const data = await response.json();
      set({ executions: data });
    } catch (e) {
      console.error('Failed to load engine history:', e);
    }
  },
}));
```

### 11.3 — Novo Router (Backend API)

```python
# packages/backend/src/routers/engine_v2.py
"""
V4 Engine API endpoints.
Only active when engine_v2_enabled = True.
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from pydantic import BaseModel

from ..config import get_settings, Settings
from ..dependencies import AuthDep, DbDep
from ..models.database import AsyncSession

logger = logging.getLogger("ahri.engine.router")

router = APIRouter(prefix="/engine/v2", tags=["engine-v2"])


class ExecuteRequest(BaseModel):
    goal: str
    model: str = "fast"
    system_prompt: str = ""
    max_iterations: int = 50


@router.post("/execute")
async def execute_task(
    request: ExecuteRequest,
    auth: AuthDep,
    db: DbDep,
    settings: Settings = Depends(get_settings),
):
    """Start a new engine execution (non-streaming, returns final result)."""
    if not settings.engine_v2_enabled:
        raise HTTPException(status_code=404, detail="Engine V2 not enabled")

    # Get engine from app state (initialized in lifespan)
    from ..main import get_engine
    engine = get_engine()

    events = []
    final_response = None

    async for event in engine.run(
        goal=request.goal,
        system_prompt=request.system_prompt,
        model=request.model,
        max_iterations=request.max_iterations,
    ):
        events.append(event.to_dict())
        if event.type.value == "final_response":
            final_response = event.data.get("content", "")

    return {
        "execution_id": events[0]["execution_id"] if events else "",
        "final_response": final_response,
        "events": events,
        "event_count": len(events),
    }


@router.websocket("/ws")
async def engine_websocket(
    websocket: WebSocket,
    goal: str = "",
    model: str = "fast",
):
    """
    WebSocket endpoint for real-time engine streaming.

    Connect: ws://localhost:8742/engine/v2/ws?goal=...&model=fast
    Receive: JSON events as they happen
    Send: {"type": "cancel"} to cancel execution
    """
    await websocket.accept()

    if not goal:
        await websocket.send_json({"type": "error", "data": {"error": "No goal provided"}})
        await websocket.close()
        return

    from ..main import get_engine
    engine = get_engine()

    cancel_event = asyncio.Event()

    # Listen for cancel messages from client
    async def listen_for_cancel():
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "cancel":
                    cancel_event.set()
                    break
        except WebSocketDisconnect:
            cancel_event.set()
        except Exception:
            pass

    cancel_task = asyncio.create_task(listen_for_cancel())

    try:
        async for event in engine.run(goal=goal, model=model):
            if cancel_event.is_set():
                await websocket.send_json({
                    "type": "cancelled",
                    "data": {"reason": "User cancelled"},
                })
                break

            await websocket.send_json(event.to_dict())

    except WebSocketDisconnect:
        logger.info("Engine WebSocket disconnected")
    except Exception as e:
        logger.error(f"Engine WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "data": {"error": str(e)}})
        except Exception:
            pass
    finally:
        cancel_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/executions")
async def list_executions(
    auth: AuthDep,
    db: DbDep,
    limit: int = 20,
):
    """List recent engine executions."""
    from sqlalchemy import select, desc
    from ..models.database import EngineExecution

    result = await db.execute(
        select(EngineExecution)
        .order_by(desc(EngineExecution.created_at))
        .limit(limit)
    )
    executions = result.scalars().all()
    return [
        {
            "execution_id": e.execution_id,
            "goal": e.goal,
            "model": e.model,
            "status": e.status,
            "iterations": e.iterations,
            "total_tokens": e.total_input_tokens + e.total_output_tokens,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in executions
    ]
```

### 11.4 — Modificar `main.py` (inicialização do engine)

```python
# Add to packages/backend/src/main.py lifespan

# At top of file, add imports:
# from src.engine.model_registry import create_model_registry
# from src.engine.tools.registry import ToolRegistry
# from src.engine.tools.builtin import register_builtin_tools
# from src.engine.query_engine import QueryEngine
# from src.engine.hooks.manager import HookManager
# from src.engine.compact.manager import CompactManager
# from src.engine.permissions.base import PermissionManager
# from src.engine.plugins.loader import PluginLoader
# from src.engine.agents.spawner import AGENT_TOOLS

# Global engine instance
_engine: QueryEngine | None = None

def get_engine() -> QueryEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized")
    return _engine


# In the lifespan function, add:
async def lifespan(app: FastAPI):
    global _engine
    settings = get_settings()

    # ... existing startup code ...

    # Initialize V4 Engine (if enabled)
    if settings.engine_v2_enabled:
        # 1. Model Registry
        model_registry = create_model_registry(settings)

        # 2. Tool Registry
        tool_registry = ToolRegistry()
        builtin_count = register_builtin_tools(tool_registry)

        # Register agent spawning tool
        for tool in AGENT_TOOLS:
            tool_registry.register(tool)

        # 3. Hook Manager
        hook_manager = HookManager(default_timeout=settings.engine_hook_timeout)

        # 4. Permission Manager
        permission_manager = PermissionManager(mode=settings.engine_permission_mode)

        # 5. Compact Manager
        compact_manager = CompactManager(
            model_registry=model_registry,
            threshold=settings.engine_compact_threshold,
            keep_recent=settings.engine_compact_keep_recent,
        )

        # 6. Plugin Loader
        if settings.engine_plugin_directories:
            plugin_loader = PluginLoader(tool_registry, hook_manager)
            plugins_loaded = plugin_loader.load_all(settings.engine_plugin_directories)
            logger.info(f"Loaded {plugins_loaded} plugin tools")

        # 7. Create Query Engine
        _engine = QueryEngine(
            model_registry=model_registry,
            tool_registry=tool_registry,
            settings=settings,
            permission_manager=permission_manager,
            hook_manager=hook_manager,
            compact_manager=compact_manager,
        )

        logger.info(f"V4 Engine initialized: {tool_registry.enabled_count} tools, "
                     f"{len(model_registry.available_models)} models")

    yield

    # ... existing shutdown code ...

# In app router setup, add:
# from src.routers.engine_v2 import router as engine_v2_router
# app.include_router(engine_v2_router)
```

---

## Rollout Strategy

### Feature Flag Approach

```
engine_v2_enabled = False  (default)
│
├── V1 System (current):
│   └── /agent-mode/* endpoints
│   └── OrchestratorService → Workers
│
└── V2 System (new, when enabled):
    └── /engine/v2/* endpoints
    └── QueryEngine → Tools
```

### Migration Path

1. **Phase A** — Deploy V4 engine alongside V1 (both active)
   - `engine_v2_enabled = True`
   - V1 endpoints still work as before
   - V2 endpoints available for testing

2. **Phase B** — Adapt V3 workers as V4 tools
   - Use `WorkerToolAdapter` to wrap existing workers
   - V4 engine can use V3 workers through adapter

3. **Phase C** — Gradually replace adapted workers with native tools
   - Replace `v3_code` with native `code_analyze` + `code_generate`
   - Replace `v3_shell` with native `file_read` + `file_write` + `shell_execute`
   - etc.

4. **Phase D** — Remove V1 code
   - Remove OrchestratorService
   - Remove BaseWorker and all workers
   - Remove V1 endpoints
   - Remove feature flag

---

## Testing Strategy

### Per-Phase Testing

```bash
# Phase 0: Foundation types
pytest tests/engine/test_types.py -v

# Phase 1: Model registry
pytest tests/engine/test_model_registry.py -v

# Phase 2: Tools
pytest tests/engine/test_tools.py -v

# Phase 3: Query engine
pytest tests/engine/test_query_engine.py -v

# All engine tests
pytest tests/engine/ -v
```

### Integration Testing

```python
# tests/engine/test_integration.py
"""
End-to-end integration test for the V4 Engine.
Uses mock LLM responses to test the full pipeline.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.query_engine import QueryEngine
from src.engine.model_registry import ModelRegistry
from src.engine.tools.registry import ToolRegistry
from src.engine.tools.builtin import register_builtin_tools
from src.engine.types import LLMResponse, ToolCall, StopReason, ModelInfo, ModelCapabilities


@pytest.mark.asyncio
async def test_full_pipeline():
    """Test: user asks to read a file → engine calls file_read → returns content."""
    # Setup
    registry = MagicMock(spec=ModelRegistry)
    registry.resolve.return_value = ModelInfo(
        id="test-model", provider="gemini",
        capabilities=ModelCapabilities(context_window=100000),
    )

    # Mock LLM: first call returns tool_use, second returns text
    registry.call = AsyncMock(side_effect=[
        LLMResponse(
            content="I'll read that file for you.",
            tool_calls=[ToolCall(tool_name="file_read", arguments={"path": "test.txt"})],
            stop_reason=StopReason.TOOL_USE,
            input_tokens=50, output_tokens=30,
        ),
        LLMResponse(
            content="The file contains 'Hello World'.",
            stop_reason=StopReason.END_TURN,
            input_tokens=100, output_tokens=25,
        ),
    ])

    tools = ToolRegistry()
    register_builtin_tools(tools)

    engine = QueryEngine(registry, tools)

    events = []
    async for event in engine.run("Read test.txt"):
        events.append(event)

    # Verify event flow
    types = [e.type.value for e in events]
    assert "engine_start" in types
    assert "engine_stop" in types
    assert "final_response" in types
```

### Manual Testing

```bash
# 1. Set feature flag
# In .env: engine_v2_enabled=true

# 2. Start backend
cd packages/backend
python -m uvicorn src.main:app --reload --port 8742

# 3. Test via curl (non-streaming)
curl -X POST http://localhost:8742/engine/v2/execute \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"goal": "List files in the current directory", "model": "fast"}'

# 4. Test via WebSocket (streaming)
# Use wscat or browser DevTools:
# ws://localhost:8742/engine/v2/ws?goal=Read%20test.txt&model=fast
```

---

## Estrutura Final de Diretórios

```
packages/backend/src/engine/
├── __init__.py
├── types.py                    # Phase 0: Foundation types
├── errors.py                   # Phase 0: Error hierarchy
├── events.py                   # Phase 0: Event types
├── model_registry.py           # Phase 1: Model aliases, fallbacks, key rotation
├── query_engine.py             # Phase 3: Core async generator loop
├── providers/
│   ├── __init__.py
│   ├── base.py                 # Phase 1: Abstract LLM provider
│   ├── gemini_provider.py      # Phase 1: Gemini REST API
│   ├── ollama_provider.py      # Phase 1: Ollama local
│   └── openrouter_provider.py  # Phase 1: OpenRouter/DeepSeek
├── tools/
│   ├── __init__.py
│   ├── base.py                 # Phase 2: ToolDefinition, ToolUseContext, build_tool
│   ├── registry.py             # Phase 2: ToolRegistry with partitioning
│   └── builtin/
│       ├── __init__.py         # Phase 2: register_builtin_tools()
│       ├── file_tools.py       # Phase 2: file_read, file_write, file_list
│       ├── shell_tools.py      # Phase 2: shell_execute
│       ├── code_tools.py       # Phase 2: code_analyze, code_generate
│       ├── web_tools.py        # Phase 2: web_fetch
│       ├── memory_tools.py     # Phase 2: memory_search, memory_store
│       ├── search_tools.py     # Phase 2: web_search
│       └── vision_tools.py     # Phase 2: (future) image analysis
├── permissions/
│   ├── __init__.py
│   └── base.py                 # Phase 4: PermissionManager, rules, dangerous patterns
├── hooks/
│   ├── __init__.py
│   └── manager.py              # Phase 5: HookManager, event-driven handlers
├── compact/
│   ├── __init__.py
│   └── manager.py              # Phase 6: CompactManager, summarization, snipping
├── agents/
│   ├── __init__.py
│   ├── spawner.py              # Phase 7: spawn_agent tool, agent prompts
│   └── definitions.py          # Phase 7: YAML agent type definitions
├── plugins/
│   ├── __init__.py
│   ├── loader.py               # Phase 8: PluginLoader, dynamic import
│   └── schema.py               # Phase 8: PluginManifest dataclass
└── migration/
    ├── __init__.py
    └── worker_adapter.py       # Phase 9: WorkerToolAdapter (V3→V4 bridge)
```

---

## Ordem de Implementação Recomendada

```
Phase 0 (Foundation) ──────────────────────────────┐
  │                                                 │
  ├── Phase 1 (Providers + Registry) ──────┐        │
  │                                        │        │
  ├── Phase 4 (Permissions) ──────────┐    │        │
  │                                   │    │        │
  └── Phase 5 (Hooks) ──────────┐     │    │        │
                                │     │    │        │
Phase 2 (Tools) ────────────────┤     │    │        │
  │                             │     │    │        │
  └── Phase 3 (Query Engine) ───┴─────┴────┘        │
       │                                             │
       ├── Phase 6 (Compaction) ─────────────────────┘
       │
       ├── Phase 7 (Agent Spawning)
       │
       ├── Phase 8 (Plugins)
       │
       ├── Phase 9 (Worker Migration)
       │
       ├── Phase 10 (Database)
       │
       └── Phase 11 (Frontend)
```

**Parallelism opportunities:**
- Phase 4 + 5 can be done in parallel (independent of each other)
- Phase 6 + 7 + 8 can be done in parallel after Phase 3
- Phase 10 can be done anytime (just database tables)
- Phase 11 can start as soon as Phase 3 is done (needs API endpoints)

---

## Checklist de Verificação Final

- [ ] Phase 0: `types.py`, `errors.py`, `events.py` criados e testados
- [ ] Phase 0: `config.py` atualizado com settings `engine_*`
- [ ] Phase 1: 3 providers implementados (Gemini, Ollama, OpenRouter)
- [ ] Phase 1: `ModelRegistry` com aliases, fallback, key rotation
- [ ] Phase 2: `ToolRegistry` com partitioning concurrent/serial
- [ ] Phase 2: 11+ built-in tools implementados
- [ ] Phase 3: `QueryEngine` async generator loop funcional
- [ ] Phase 4: `PermissionManager` com rules e dangerous patterns
- [ ] Phase 5: `HookManager` com event system
- [ ] Phase 6: `CompactManager` com summarization e snipping
- [ ] Phase 7: `spawn_agent` tool funcional com depth limiting
- [ ] Phase 8: `PluginLoader` com dynamic import de tools/hooks
- [ ] Phase 9: `WorkerToolAdapter` wrapping V3 workers
- [ ] Phase 10: 3 novas tabelas no database
- [ ] Phase 11: TypeScript types, Zustand store, WebSocket endpoint
- [ ] Feature flag `engine_v2_enabled` funcionando
- [ ] V1 e V4 coexistindo sem conflitos
- [ ] Testes para cada phase passando
- [ ] API endpoints V2 funcionais (/execute, /ws, /executions)

---

## Apêndice A — `tools/builtin/vision_tools.py`

```python
"""
Vision tools - Image analysis via Gemini Vision.
Replaces VisionWorker.
"""
import json
import base64
from pathlib import Path
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="image_analyze",
    description="Analyze an image for content, objects, text (OCR), or visual descriptions. Supports local files and base64.",
    category=ToolCategory.VISION,
    execution_mode=ExecutionMode.SERIAL,  # Vision calls are expensive
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to local image file (PNG, JPG, WEBP)",
            },
            "image_base64": {
                "type": "string",
                "description": "Base64-encoded image data (alternative to path)",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["describe", "ocr", "objects", "analyze"],
                "description": "Type of analysis to perform",
                "default": "describe",
            },
            "question": {
                "type": "string",
                "description": "Specific question about the image (optional)",
            },
        },
        "required": [],
    },
)
async def image_analyze(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    image_path = args.get("image_path", "")
    image_b64 = args.get("image_base64", "")
    analysis_type = args.get("analysis_type", "describe")
    question = args.get("question", "")

    # Get image data
    if image_path:
        p = Path(image_path)
        if not p.exists():
            return json.dumps({"error": f"Image not found: {image_path}"})
        image_b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower(), "image/png")
    elif not image_b64:
        return json.dumps({"error": "Provide image_path or image_base64"})
    else:
        mime = "image/png"  # Default for base64

    # Build analysis prompt
    prompts = {
        "describe": "Describe this image in detail. What do you see?",
        "ocr": "Extract ALL text visible in this image. Return the text exactly as written.",
        "objects": "List all distinct objects visible in this image with their approximate positions.",
        "analyze": "Provide a comprehensive analysis of this image including: content, mood, colors, composition, and any notable details.",
    }
    prompt = question or prompts.get(analysis_type, prompts["describe"])

    # Call vision-capable model
    # Use "best" or "flash" since they support vision
    vision_model = "flash"  # Gemini Flash supports vision
    try:
        # Build multimodal message for Gemini
        messages = [{
            "role": "user",
            "content": prompt,
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ],
        }]

        result = await ctx.call_llm(
            messages=messages,
            model=vision_model,
        )

        return json.dumps({
            "analysis_type": analysis_type,
            "result": result.content if hasattr(result, 'content') else str(result),
            "image_path": image_path or "(base64 input)",
        })
    except Exception as e:
        return json.dumps({"error": f"Vision analysis failed: {e}"})


VISION_TOOLS = [image_analyze]
```

**Atualizar `tools/builtin/__init__.py`** para incluir:
```python
from .vision_tools import VISION_TOOLS

# Na função register_builtin_tools, adicionar:
# all_tools = FILE_TOOLS + SHELL_TOOLS + CODE_TOOLS + WEB_TOOLS + MEMORY_TOOLS + SEARCH_TOOLS + VISION_TOOLS
```

---

## Apêndice B — Data Flow Detalhado

### B.1 — Fluxo de Execução Completo (Single Request)

```
Usuário envia "Leia o arquivo config.py e analise bugs"
    │
    ▼
[FastAPI Router: /engine/v2/ws]
    │
    ▼
[QueryEngine.run(goal="Leia o arquivo...")]
    │
    ├── yield ENGINE_START event
    │
    ├── ITERATION 1:
    │   │
    │   ├── _call_llm(messages=[user_msg], tools=[12 declarations])
    │   │   │
    │   │   ├── ModelRegistry.resolve("fast") → ModelInfo(gemini-3.1-flash-lite)
    │   │   ├── ModelRegistry.get_next_key("gemini") → "key-3" (round-robin)
    │   │   └── GeminiProvider.generate(messages, model, key, tools)
    │   │       └── POST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent
    │   │           └── Response: {functionCall: {name: "file_read", args: {path: "config.py"}}}
    │   │
    │   ├── yield LLM_RESPONSE event (has_tool_calls=true)
    │   │
    │   ├── _execute_tools([ToolCall(file_read, {path: "config.py"})])
    │   │   │
    │   │   ├── PermissionManager.check("file_read", {path: "config.py"})
    │   │   │   ├── mode="auto" → check rules → no match
    │   │   │   ├── check dangerous patterns → no match
    │   │   │   └── tool.permission_level=SAFE → ALLOW
    │   │   │
    │   │   ├── HookManager.emit("pre_tool_use", {tool_name: "file_read", ...})
    │   │   │
    │   │   ├── ToolRegistry.partition_tools([file_read])
    │   │   │   └── concurrent=[file_read], serial=[]
    │   │   │
    │   │   ├── asyncio.gather(file_read.handler(ctx, args))
    │   │   │   └── Returns: {path: "config.py", content: "...", lines: 167}
    │   │   │
    │   │   ├── yield TOOL_USE_END event
    │   │   │
    │   │   └── HookManager.emit("post_tool_use", {output: ...})
    │   │
    │   ├── Add tool result to messages[]
    │   │
    │   └── _decide_continuation(state)
    │       ├── tokens_used=1200, context_window=262144
    │       └── ratio=0.004 < threshold=0.80 → CONTINUE
    │
    ├── ITERATION 2:
    │   │
    │   ├── _call_llm(messages=[user_msg, assistant+tool_call, tool_result], tools)
    │   │   └── Response: {functionCall: {name: "code_analyze", args: {code: "...", analysis_type: "bugs"}}}
    │   │
    │   ├── _execute_tools([ToolCall(code_analyze, {...})])
    │   │   │
    │   │   └── code_analyze.handler(ctx, args)
    │   │       ├── ctx.call_llm(messages=[analyze prompt], json_mode=True)
    │   │       │   └── ModelRegistry.call("fast", ...) → analysis JSON
    │   │       └── Returns: {issues: [...], summary: "...", score: 8}
    │   │
    │   └── CONTINUE
    │
    ├── ITERATION 3:
    │   │
    │   ├── _call_llm(messages=[...full history...], tools)
    │   │   └── Response: {text: "Analisei o config.py e encontrei...", no tool_calls}
    │   │
    │   ├── yield TEXT_CHUNK event
    │   ├── yield FINAL_RESPONSE event
    │   └── STOP (no tool_calls = end turn)
    │
    └── yield ENGINE_STOP event (total_tokens=3500, iterations=3)
```

### B.2 — Fluxo de Sub-Agent Spawning

```
[Parent QueryEngine (depth=0)]
    │
    ├── LLM calls spawn_agent(goal="Research Python best practices", agent_type="research")
    │
    ├── spawn_agent handler:
    │   ├── Check depth: 0 < max_depth(3) → OK
    │   │
    │   ├── Create new QueryEngine instance
    │   │   ├── Same model_registry (shared providers + keys)
    │   │   ├── Same tool_registry (shared tools)
    │   │   ├── Isolated message history (own EngineState)
    │   │   └── Custom system_prompt (AGENT_PROMPTS["research"])
    │   │
    │   └── async for event in child_engine.run(goal, depth=1):
    │       ├── Child ITERATION 1: web_search("python best practices 2026")
    │       ├── Child ITERATION 2: web_fetch(top_3_urls)
    │       ├── Child ITERATION 3: final synthesis
    │       └── Returns: {result: "...", iterations: 3, total_tokens: 2000}
    │
    ├── Parent receives tool result with research summary
    │
    └── Parent ITERATION N: LLM uses research to answer user
```

### B.3 — Fluxo de Compaction

```
[QueryEngine iteration 15, total_tokens=200000]
    │
    ├── _decide_continuation(state)
    │   ├── tokens_used=200000, context_window=262144
    │   └── ratio=0.76 > threshold(0.80)? NO, but close
    │
    ├── [QueryEngine iteration 18, total_tokens=220000]
    │   ├── ratio=0.84 > 0.80 → COMPACT
    │   │
    │   └── _compact_context(state)
    │       │
    │       ├── CompactManager.compact(messages, keep_recent=4)
    │       │   │
    │       │   ├── Step 1: _snip_large_outputs()
    │       │   │   └── Tool result with 5000+ chars → keep first/last 20 lines
    │       │   │
    │       │   ├── Step 2: Separate messages
    │       │   │   ├── first_msg = messages[0] (original user goal)
    │       │   │   ├── middle = messages[1:-4] (14 messages to summarize)
    │       │   │   └── recent = messages[-4:] (keep as-is)
    │       │   │
    │       │   ├── Step 3: _summarize(middle)
    │       │   │   ├── ModelRegistry.call("lite", summarize_prompt)
    │       │   │   └── Returns: "Summary: The agent read 5 files, analyzed code..."
    │       │   │
    │       │   └── Return: [first_msg, summary_msg, recent[0..3]]
    │       │       └── 6 messages instead of 18 (67% reduction)
    │       │
    │       └── state.messages = compacted_messages
    │
    └── Continue with reduced context → more room for iterations
```

### B.4 — Fluxo de Plugin Loading

```
[App Startup / lifespan()]
    │
    ├── PluginLoader.load_all(["./plugins", "~/.ahri/plugins"])
    │   │
    │   ├── discover("./plugins")
    │   │   ├── ./plugins/spotify-context/plugin.json → PluginManifest(name="spotify-context")
    │   │   └── ./plugins/japanese-tutor/plugin.json → PluginManifest(name="japanese-tutor")
    │   │
    │   ├── load(./plugins/spotify-context, manifest)
    │   │   ├── Load tools: ./plugins/spotify-context/tools/spotify.py
    │   │   │   ├── @build_tool(name="spotify_now_playing", ...)
    │   │   │   └── @build_tool(name="spotify_recommend", ...)
    │   │   │   → ToolRegistry.register(spotify_now_playing)
    │   │   │   → ToolRegistry.register(spotify_recommend)
    │   │   │
    │   │   └── Load hooks: ./plugins/spotify-context/hooks/auto_persona.py
    │   │       └── @hook_manager.on(HookEvent.SESSION_START)
    │   │           async def auto_switch_persona(data):
    │   │               # Check current Spotify track → switch persona
    │   │               ...
    │   │
    │   └── load(./plugins/japanese-tutor, manifest)
    │       └── Load tools: japanese_quiz, kanji_lookup, grammar_explain
    │
    └── Log: "Loaded 2 plugins, 5 plugin tools, 1 plugin hook"
```

---

## Apêndice C — Exemplo de Plugin Completo

### Estrutura do plugin `spotify-context`

```
plugins/spotify-context/
├── plugin.json
├── tools/
│   └── spotify.py
└── hooks/
    └── auto_persona.py
```

### `plugin.json`

```json
{
    "name": "spotify-context",
    "version": "1.0.0",
    "description": "Integrates Spotify context into agent conversations",
    "author": "ahri-team",
    "tools_dir": "tools",
    "hooks_dir": "hooks",
    "enabled": true,
    "tool_names": ["spotify_now_playing", "spotify_recommend"],
    "hook_events": ["session_start"]
}
```

### `tools/spotify.py`

```python
"""
Spotify integration tools for the V4 Engine.
"""
import json
from typing import Any
from src.engine.tools.base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="spotify_now_playing",
    description="Get the currently playing track on Spotify. Returns track name, artist, album, and playback state.",
    category=ToolCategory.CUSTOM,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def spotify_now_playing(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    """Get current Spotify track."""
    spotify_svc = ctx.metadata.get("spotify_service")
    if not spotify_svc:
        return json.dumps({"error": "Spotify service not available"})

    try:
        track = spotify_svc.get_current_track()
        if not track:
            return json.dumps({"playing": False, "message": "Nothing is playing"})
        return json.dumps({
            "playing": True,
            "track": track.get("name", ""),
            "artist": track.get("artist", ""),
            "album": track.get("album", ""),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@build_tool(
    name="spotify_recommend",
    description="Get music recommendations based on current listening context.",
    category=ToolCategory.CUSTOM,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "mood": {"type": "string", "description": "Desired mood (happy, chill, energetic, etc.)"},
            "genre": {"type": "string", "description": "Genre preference"},
        },
        "required": [],
    },
)
async def spotify_recommend(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    mood = args.get("mood", "")
    genre = args.get("genre", "")

    prompt = f"Recommend 5 songs that match: mood={mood or 'any'}, genre={genre or 'any'}"

    result = await ctx.call_llm(
        messages=[{"role": "user", "content": prompt}],
        model="lite",
    )

    return json.dumps({
        "recommendations": result.content if hasattr(result, 'content') else str(result),
        "mood": mood,
        "genre": genre,
    })


SPOTIFY_TOOLS = [spotify_now_playing, spotify_recommend]
```

### `hooks/auto_persona.py`

```python
"""
Auto-persona hook: switches persona based on Spotify context at session start.
"""
from src.engine.hooks.manager import HookEvent, HookRegistration

async def auto_switch_persona(data: dict) -> dict:
    """
    On session start, check Spotify and suggest persona switch.
    """
    # This hook could query Spotify and add context to the system prompt
    # For now, it's a placeholder showing the pattern
    data["spotify_context"] = "Hook executed - persona check would happen here"
    return data

# Register when the module is loaded by PluginLoader
# (PluginLoader injects hook_manager into the module namespace)
try:
    hook_manager.register(HookRegistration(
        event=HookEvent.SESSION_START,
        handler=auto_switch_persona,
        name="spotify_auto_persona",
        priority=10,
        plugin_name="spotify-context",
    ))
except NameError:
    pass  # hook_manager not injected (module loaded outside plugin context)
```

---

## Apêndice D — Testes de Integração Avançados

### D.1 — Teste de Permission + Hook Integration

```python
# tests/engine/test_permission_hooks.py
import pytest
from src.engine.permissions.base import PermissionManager, PermissionRule, RuleAction
from src.engine.hooks.manager import HookManager, HookEvent
from src.engine.types import PermissionDecision


@pytest.mark.asyncio
async def test_permission_blocks_dangerous():
    pm = PermissionManager(mode="auto")

    # rm -rf in shell command should be denied
    decision = await pm.check("shell_execute", {"command": "rm -rf /home"})
    assert decision == PermissionDecision.DENY


@pytest.mark.asyncio
async def test_permission_allows_safe_reads():
    pm = PermissionManager(mode="auto")

    decision = await pm.check("file_read", {"path": "/tmp/test.txt"})
    assert decision == PermissionDecision.ALLOW


@pytest.mark.asyncio
async def test_permission_custom_rule():
    pm = PermissionManager(mode="auto")
    pm.add_rule(PermissionRule(
        tool_pattern="file_write",
        action=RuleAction.DENY,
        arg_patterns={"path": r"\.env$"},
        reason="Never write to .env files",
        priority=100,
    ))

    # Writing to .env should be denied
    decision = await pm.check("file_write", {"path": "/app/.env"})
    assert decision == PermissionDecision.DENY

    # Writing to other files should be allowed
    decision = await pm.check("file_write", {"path": "/app/test.txt"})
    assert decision == PermissionDecision.ALLOW


@pytest.mark.asyncio
async def test_hook_chain():
    hm = HookManager()
    call_order = []

    @hm.on(HookEvent.PRE_TOOL_USE, name="logger", priority=10)
    async def log_hook(data):
        call_order.append("logger")
        data["logged"] = True
        return data

    @hm.on(HookEvent.PRE_TOOL_USE, name="validator", priority=5)
    async def validate_hook(data):
        call_order.append("validator")
        data["validated"] = True
        return data

    result = await hm.emit(HookEvent.PRE_TOOL_USE, {"tool_name": "file_read"})

    # Higher priority runs first
    assert call_order == ["logger", "validator"]
    assert result["logged"] is True
    assert result["validated"] is True


@pytest.mark.asyncio
async def test_hook_timeout():
    import asyncio
    hm = HookManager(default_timeout=1)

    @hm.on(HookEvent.PRE_TOOL_USE, name="slow_hook")
    async def slow_hook(data):
        await asyncio.sleep(5)  # Exceeds 1s timeout
        return data

    # Should not raise, just log warning and continue
    result = await hm.emit(HookEvent.PRE_TOOL_USE, {"tool_name": "test"})
    assert result == {"tool_name": "test"}  # Original data unchanged
```

### D.2 — Teste de Compaction

```python
# tests/engine/test_compaction.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.compact.manager import CompactManager
from src.engine.types import Message, Role, LLMResponse


@pytest.fixture
def compact_manager():
    registry = MagicMock()
    registry.call = AsyncMock(return_value=LLMResponse(
        content="Summary: The agent read 3 files and found 2 bugs.",
    ))
    return CompactManager(
        model_registry=registry,
        compact_model="lite",
        keep_recent=3,
    )


@pytest.mark.asyncio
async def test_compact_reduces_messages(compact_manager):
    # Create 10 messages
    messages = [
        Message(role=Role.USER, content="Analyze my project"),
    ]
    for i in range(8):
        messages.append(Message(role=Role.ASSISTANT, content=f"Step {i} result"))
    messages.append(Message(role=Role.ASSISTANT, content="Final result"))

    result = await compact_manager.compact(messages, keep_recent=3)

    # Should be: first_msg + summary + last 3 = 5
    assert len(result) == 5
    assert result[0].role == Role.USER
    assert result[0].content == "Analyze my project"
    assert "compacted" in result[1].content.lower() or "summary" in result[1].content.lower()


@pytest.mark.asyncio
async def test_snip_large_outputs(compact_manager):
    messages = [
        Message(role=Role.TOOL_RESULT, content="x\n" * 10000),
    ]
    snipped = compact_manager._snip_large_outputs(messages)
    assert len(snipped[0].content) < len(messages[0].content)
    assert "snipped" in snipped[0].content.lower()


def test_should_compact():
    registry = MagicMock()
    cm = CompactManager(registry, threshold=0.80)

    assert cm.should_compact(80000, 100000) is True   # 80%
    assert cm.should_compact(70000, 100000) is False   # 70%
    assert cm.should_compact(0, 0) is False            # Edge case
```

### D.3 — Teste End-to-End com Worker Adapter

```python
# tests/engine/test_worker_adapter.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.engine.migration.worker_adapter import WorkerToolAdapter
from src.engine.tools.base import ToolUseContext, ToolCategory, ExecutionMode
from src.engine.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_adapt_single_worker():
    """Test adapting a V3 worker as a V4 tool."""
    # Mock V3 worker
    mock_worker = MagicMock()
    mock_worker.worker_type = "Code"

    mock_task = MagicMock()
    mock_task.status.value = "completed"
    mock_task.output_data = {"code": "print('hello')"}
    mock_task.tokens_used = 100
    mock_task.error = None

    mock_worker.execute_with_correction = AsyncMock(return_value=mock_task)

    # Adapt to V4 tool
    tool = WorkerToolAdapter.from_worker(
        mock_worker,
        tool_name="v3_code",
        description="Code worker (adapted)",
        category=ToolCategory.CODE,
    )

    assert tool.name == "v3_code"
    assert tool.handler is not None

    # Execute through the adapter
    ctx = ToolUseContext(
        model_registry=MagicMock(),
        tool_registry=MagicMock(),
        execution_id="123",
    )

    import json
    result = await tool.handler(ctx, {"task": "generate hello world"})
    parsed = json.loads(result)

    assert parsed["status"] == "completed"
    assert parsed["output"]["code"] == "print('hello')"


@pytest.mark.asyncio
async def test_adapt_all_workers():
    """Test batch adaptation of V3 workers."""
    workers = {
        "RAG": MagicMock(worker_type="RAG"),
        "Code": MagicMock(worker_type="Code"),
        "Shell": MagicMock(worker_type="Shell"),
    }

    tools = WorkerToolAdapter.adapt_all_workers(workers)

    assert len(tools) == 3
    names = {t.name for t in tools}
    assert "v3_rag" in names
    assert "v3_code" in names
    assert "v3_shell" in names

    # RAG should be concurrent, Shell should be serial
    rag_tool = next(t for t in tools if t.name == "v3_rag")
    shell_tool = next(t for t in tools if t.name == "v3_shell")
    assert rag_tool.execution_mode == ExecutionMode.CONCURRENT
    assert shell_tool.execution_mode == ExecutionMode.SERIAL
```

---

## Apêndice E — Notas para o Gemini (Implementador)

### E.1 — Ordem de Execução dos Testes

```bash
# Execute nesta ordem para validar cada fase:
cd packages/backend

# 1. Foundation
pytest tests/engine/test_types.py -v

# 2. Model Registry (requer providers)
pytest tests/engine/test_model_registry.py -v

# 3. Tools (requer base + registry)
pytest tests/engine/test_tools.py -v

# 4. Query Engine (requer tudo acima)
pytest tests/engine/test_query_engine.py -v

# 5. Permissions + Hooks
pytest tests/engine/test_permission_hooks.py -v

# 6. Compaction
pytest tests/engine/test_compaction.py -v

# 7. Worker Adapter
pytest tests/engine/test_worker_adapter.py -v

# 8. Full integration
pytest tests/engine/test_integration.py -v

# ALL
pytest tests/engine/ -v --tb=short
```

### E.2 — Gotchas Importantes

1. **Imports circulares**: `query_engine.py` importa `tools/`, que pode importar de volta. Use `TYPE_CHECKING` guards e imports dentro de funções onde necessário.

2. **Thread safety**: Os providers usam `httpx.AsyncClient` que é async-safe. NÃO usar `requests` (blocking). NÃO usar `genai.configure()` (global state).

3. **Gemini function calling format**: Gemini usa `functionDeclarations` dentro de `tools[0]`, não o formato OpenAI. O `GeminiProvider.format_tools()` já lida com isso.

4. **Ollama tool calling**: Nem todos os modelos Ollama suportam tools. Qwen3 e Llama3.1+ suportam. Se o modelo não suportar, o provider deve retornar `LLMResponse` sem `tool_calls` e incluir instruções de tool use no prompt.

5. **WebSocket close race**: Sempre use try/except ao enviar no WebSocket — o cliente pode desconectar a qualquer momento. O router `engine_v2.py` já tem essa proteção.

6. **Pydantic V2**: O projeto usa Pydantic V2 com `pydantic_settings`. Dataclasses (usadas no engine) são separadas dos schemas Pydantic (usados nos routers).

7. **JSON na resposta do Gemini**: Quando `json_mode=True`, o Gemini retorna JSON válido mas às vezes wrappado em markdown code blocks. Strip ` ```json ` e ` ``` ` antes de parsear.

8. **Depth limit em sub-agents**: O `spawn_agent` tool verifica `depth < max_depth` ANTES de criar o engine. Isso previne recursão infinita. O depth é passado no `context.metadata["depth"]`.

9. **API key rotation timing**: O `ModelRegistry` faz round-robin sequencial. Se uma key atingir rate limit, a próxima chamada usa a próxima key automaticamente. O `RateLimitError` handler no `QueryEngine` já faz retry.

10. **Config reload**: O `get_settings()` usa `@lru_cache`, então mudanças no `.env` requerem restart. Para hot-reload, limpe o cache: `get_settings.cache_clear()`.

### E.3 — Resumo das Dependências Python Necessárias

```
# Adicionar ao requirements.txt ou pyproject.toml:
httpx>=0.25.0          # Async HTTP client (providers)
# jsonschema já existe (usado pelos workers)
# sqlalchemy já existe (database)
# fastapi já existe (routers)
# pydantic-settings já existe (config)
```

`httpx` é a única dependência nova. Todo o resto já está no projeto.

---

*Gerado a partir de análise profunda do Claude Code (Anthropic) source code e adaptado para o stack Python/FastAPI do Ahri V3.*
*Última atualização: 2026-04-01*
