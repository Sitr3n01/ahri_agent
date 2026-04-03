"""
EventLog - In-memory event stream for agent execution observability.

Inspired by OpenHands' event-stream architecture: captures actions and
observations as a perception-action log for real-time streaming to clients.

Events are NOT persisted to database — AgentWorkerTask records capture
final state. This is for real-time WebSocket streaming only.

Usage:
    log = EventLog(execution_id=42)
    log.subscribe(websocket_handler)
    log.emit(EventType.WORKER_STARTED, {"worker": "Code", "step": 0})
"""
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("ahri.event_log")


class EventType(Enum):
    # Planning phase
    PLAN_CREATED = "plan_created"
    PLAN_DELIBERATED = "plan_deliberated"
    PLAN_REVISED = "plan_revised"

    # Worker execution
    WORKER_STARTED = "worker_started"
    WORKER_TOOL_CALLED = "worker_tool_called"      # ReAct tool call
    WORKER_TOOL_RESULT = "worker_tool_result"       # ReAct tool result
    WORKER_COMPLETED = "worker_completed"
    WORKER_FAILED = "worker_failed"
    WORKER_RETRY = "worker_retry"                   # Self-correction retry

    # Evaluation
    EVALUATION_RESULT = "evaluation_result"

    # Replanning
    REPLAN_TRIGGERED = "replan_triggered"

    # Synthesis
    SYNTHESIS_STARTED = "synthesis_started"

    # Execution lifecycle
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"

    # Rate limiting
    RATE_LIMIT_WAIT = "rate_limit_wait"
    TPM_STATUS = "tpm_status"


@dataclass
class AgentEvent:
    """A single event in the execution stream."""
    id: int
    execution_id: int
    event_type: EventType
    timestamp: float
    data: dict = field(default_factory=dict)
    worker_type: Optional[str] = None
    step_index: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "worker_type": self.worker_type,
            "step_index": self.step_index,
        }


class EventLog:
    """
    In-memory per-execution event log with pub/sub support.

    Each execution gets its own EventLog instance. WebSocket handlers
    subscribe to receive events in real-time. Events are stored in-memory
    and cleaned up when the execution completes.
    """

    def __init__(self, execution_id: int):
        self.execution_id = execution_id
        self.events: list[AgentEvent] = []
        self._subscribers: list[Callable] = []
        self._counter = 0

    def emit(
        self,
        event_type: EventType,
        data: Optional[dict] = None,
        worker_type: Optional[str] = None,
        step_index: Optional[int] = None,
    ) -> AgentEvent:
        """
        Emit a new event and notify all subscribers.

        Args:
            event_type: Type of event
            data: Event payload
            worker_type: Worker type (if worker-related)
            step_index: Step index in the execution plan

        Returns:
            The created AgentEvent
        """
        self._counter += 1
        event = AgentEvent(
            id=self._counter,
            execution_id=self.execution_id,
            event_type=event_type,
            timestamp=time.time(),
            data=data or {},
            worker_type=worker_type,
            step_index=step_index,
        )
        self.events.append(event)

        # Notify subscribers (non-blocking)
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"[EventLog] Subscriber callback failed: {e}")

        return event

    def subscribe(self, callback: Callable[[AgentEvent], Any]) -> None:
        """Register a callback for new events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        """Remove a callback."""
        self._subscribers = [cb for cb in self._subscribers if cb is not callback]

    def get_events_since(self, last_id: int = 0) -> list[AgentEvent]:
        """Get all events after the given ID (for polling fallback)."""
        return [e for e in self.events if e.id > last_id]

    def clear(self) -> None:
        """Clear all events and subscribers."""
        self.events.clear()
        self._subscribers.clear()
        self._counter = 0


# ── Global Registry ───────────────────────────────────────────────────
# Maps execution_id -> EventLog for active executions.
# WebSocket handlers look up the log by execution_id.

_active_logs: dict[int, EventLog] = {}


def get_or_create_log(execution_id: int) -> EventLog:
    """Get or create an EventLog for an execution."""
    if execution_id not in _active_logs:
        _active_logs[execution_id] = EventLog(execution_id)
    return _active_logs[execution_id]


def get_log(execution_id: int) -> Optional[EventLog]:
    """Get an existing EventLog, or None if not found."""
    return _active_logs.get(execution_id)


def cleanup_log(execution_id: int) -> None:
    """Remove an EventLog after execution completes."""
    log = _active_logs.pop(execution_id, None)
    if log:
        log.clear()


# Worker fallback strategies (used by replanning)
WORKER_FALLBACKS = {
    "Web": ["Search", "Dynamic"],       # 403/404 → try search API
    "Browser": ["Web", "Dynamic"],      # Playwright unavailable → simple fetch
    "Code": ["Dynamic"],                # Code execution disabled → text reasoning
    "Search": ["Web", "Dynamic"],       # Search quota exceeded → web scraping
}
