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
                logger.error(f"Unknown hook event: '{event}' — check for typos in event name")
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
