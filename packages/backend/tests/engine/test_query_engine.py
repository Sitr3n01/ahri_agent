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
    assert EventType.FINAL_RESPONSE in event_types
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
