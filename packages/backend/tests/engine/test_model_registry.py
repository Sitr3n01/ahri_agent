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
