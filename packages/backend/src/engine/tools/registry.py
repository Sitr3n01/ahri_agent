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
