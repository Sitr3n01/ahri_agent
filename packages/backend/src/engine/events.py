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
