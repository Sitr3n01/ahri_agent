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
