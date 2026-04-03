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
