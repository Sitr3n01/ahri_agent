"""
Model Registry - Resolve model aliases, manage fallbacks, rotate API keys.

Inspired by Claude Code's model.ts:
- Aliases: "fast" → "gemini-3.1-flash-lite-preview"
- Fallback chains: if model A fails → try model B
- Round-robin API key rotation for rate limit management

IMPORTANT: This replaces the set_mode() pattern from V3 LLMService.
"""
import logging
import asyncio
from typing import Optional
from collections import defaultdict

from .types import ModelInfo, ModelCapabilities, LLMResponse
from .providers.base import LLMProvider
from .providers.gemini_provider import GeminiProvider
from .providers.ollama_provider import OllamaProvider
from .providers.openrouter_provider import OpenRouterProvider
from .errors import ProviderError, RateLimitError

logger = logging.getLogger("ahri.engine.registry")


class ModelRegistry:
    """
    Central model registry.

    Resolves aliases, manages providers, handles fallbacks, rotates API keys.
    Thread-safe: all mutable state is accessed through async locks.
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}
        self._models: dict[str, ModelInfo] = {}
        self._aliases: dict[str, str] = {}       # alias → model_id
        self._api_keys: dict[str, list[str]] = defaultdict(list)  # provider → [keys]
        self._key_index: dict[str, int] = defaultdict(int)        # provider → current index
        self._lock = asyncio.Lock()

    def register_provider(self, name: str, provider: LLMProvider):
        """Register an LLM provider."""
        self._providers[name] = provider
        logger.info(f"Registered provider: {name}")

    def register_model(self, model: ModelInfo):
        """Register a model with its metadata."""
        self._models[model.id] = model
        for alias in model.aliases:
            self._aliases[alias] = model.id
        logger.info(f"Registered model: {model.id} (aliases: {model.aliases})")

    def add_api_key(self, provider: str, key: str):
        """Add an API key for round-robin rotation."""
        if key and key not in self._api_keys[provider]:
            self._api_keys[provider].append(key)

    def resolve(self, model_or_alias: str) -> ModelInfo:
        """
        Resolve a model alias to full ModelInfo.

        Args:
            model_or_alias: "fast", "best", "local", or full model ID

        Returns:
            ModelInfo for the resolved model

        Raises:
            KeyError if model not found
        """
        # Direct model ID
        if model_or_alias in self._models:
            return self._models[model_or_alias]

        # Alias resolution
        if model_or_alias in self._aliases:
            model_id = self._aliases[model_or_alias]
            return self._models[model_id]

        raise KeyError(f"Unknown model or alias: {model_or_alias}")

    async def get_next_key(self, provider: str) -> str:
        """Get next API key in round-robin rotation (thread-safe)."""
        async with self._lock:
            keys = self._api_keys.get(provider, [])
            if not keys:
                raise ProviderError(f"No API keys for provider: {provider}", provider=provider)

            idx = self._key_index[provider] % len(keys)
            self._key_index[provider] = idx + 1
            return keys[idx]

    async def call(
        self,
        model_or_alias: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        thinking_budget: int = 0,
        json_mode: bool = False,
        api_key: Optional[str] = None,
    ) -> LLMResponse:
        """
        Call an LLM model with automatic fallback and key rotation.

        Args:
            model_or_alias: Model identifier or alias
            messages: Conversation messages
            tools: Tool definitions for function calling
            api_key: Specific API key (skips rotation if provided)

        Returns:
            LLMResponse from the model
        """
        model_info = self.resolve(model_or_alias)
        provider = self._providers.get(model_info.provider)
        if not provider:
            raise ProviderError(f"Provider not found: {model_info.provider}", provider=model_info.provider)

        # Get API key (provided > rotated)
        key = api_key or await self.get_next_key(model_info.provider)

        try:
            return await provider.generate(
                messages=messages,
                model=model_info.id,
                api_key=key,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking_budget=thinking_budget,
                json_mode=json_mode,
            )
        except RateLimitError:
            # Try fallback model if available
            if model_info.fallback_to:
                logger.warning(f"Rate limit on {model_info.id}, falling back to {model_info.fallback_to}")
                return await self.call(
                    model_info.fallback_to, messages, tools,
                    temperature, max_tokens, thinking_budget, json_mode,
                )
            raise
        except ProviderError as e:
            if e.retryable and model_info.fallback_to:
                logger.warning(f"Error on {model_info.id}: {e}, falling back to {model_info.fallback_to}")
                return await self.call(
                    model_info.fallback_to, messages, tools,
                    temperature, max_tokens, thinking_budget, json_mode,
                )
            raise

    @property
    def available_models(self) -> list[ModelInfo]:
        return list(self._models.values())

    @property
    def available_aliases(self) -> dict[str, str]:
        return dict(self._aliases)


def create_model_registry(settings) -> ModelRegistry:
    """
    Factory function to create a fully configured ModelRegistry.
    Called once at app startup in main.py lifespan.

    Args:
        settings: Pydantic Settings instance from config.py
    """
    registry = ModelRegistry()

    # ── Register providers ──
    registry.register_provider("gemini", GeminiProvider())
    registry.register_provider("ollama", OllamaProvider(base_url=settings.ollama_base_url))

    if settings.openrouter_api_key:
        registry.register_provider("openrouter", OpenRouterProvider())

    # ── Register models ──

    # Gemini Flash Lite (cheapest, fastest — for agents/workers)
    registry.register_model(ModelInfo(
        id=settings.google_model_lite,
        provider="gemini",
        display_name="Gemini Flash Lite",
        aliases=["fast", "lite", "agent", "LITE", "gemini-flash-lite"],
        capabilities=ModelCapabilities(
            max_tokens=8192, supports_tools=True, supports_vision=False,
            supports_thinking=False, context_window=262144,
        ),
        fallback_to=settings.google_model_flash,
    ))

    # Gemini Flash (balanced — default for orchestration)
    registry.register_model(ModelInfo(
        id=settings.google_model_flash,
        provider="gemini",
        display_name="Gemini Flash",
        aliases=["default", "balanced", "flash", "FLASH", "GOOGLE"],
        capabilities=ModelCapabilities(
            max_tokens=65536, supports_tools=True, supports_vision=True,
            supports_thinking=True, context_window=1048576,
        ),
        fallback_to=settings.google_model_lite,
    ))

    # Gemini Pro (best — for complex reasoning)
    registry.register_model(ModelInfo(
        id=settings.google_model_pro,
        provider="gemini",
        display_name="Gemini Pro",
        aliases=["best", "pro", "smart", "PRO"],
        capabilities=ModelCapabilities(
            max_tokens=65536, supports_tools=True, supports_vision=True,
            supports_thinking=True, context_window=1048576,
        ),
        fallback_to=settings.google_model_flash,
    ))

    # Ollama local model
    registry.register_model(ModelInfo(
        id=settings.ollama_chat_model,
        provider="ollama",
        display_name="Local (Ollama)",
        aliases=["local", "LOCAL", "ollama", "qwen-3.5-local"],
        capabilities=ModelCapabilities(
            max_tokens=8192, supports_tools=True, supports_vision=False,
            supports_thinking=True, context_window=32768,
        ),
    ))

    # DeepSeek via OpenRouter (optional)
    if settings.openrouter_api_key:
        registry.register_model(ModelInfo(
            id=settings.openrouter_model_name,
            provider="openrouter",
            display_name="DeepSeek R1 (OpenRouter)",
            aliases=["deepseek", "DEEPSEEK", "reasoning"],
            capabilities=ModelCapabilities(
                max_tokens=8192, supports_tools=True, supports_thinking=True,
                context_window=128000,
            ),
            fallback_to=settings.google_model_flash,
        ))
        registry.add_api_key("openrouter", settings.openrouter_api_key)

    # ── Register API keys (round-robin) ──
    for key in settings.agent_api_keys:
        registry.add_api_key("gemini", key)

    # Add primary keys too
    if settings.gemini_api_key_paid:
        registry.add_api_key("gemini", settings.gemini_api_key_paid)
    if settings.gemini_api_key_free:
        registry.add_api_key("gemini", settings.gemini_api_key_free)

    logger.info(
        f"ModelRegistry initialized: {len(registry.available_models)} models, "
        f"{len(registry._api_keys.get('gemini', []))} Gemini keys"
    )

    return registry
