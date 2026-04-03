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
