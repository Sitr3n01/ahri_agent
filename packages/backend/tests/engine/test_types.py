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
