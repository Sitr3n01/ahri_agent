"""
Engine-specific errors.
Inspired by Claude Code's error handling patterns.
"""
from typing import Optional


class EngineError(Exception):
    """Base error for all engine operations."""
    def __init__(self, message: str, code: str = "ENGINE_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderError(EngineError):
    """LLM provider returned an error."""
    def __init__(self, message: str, provider: str, status_code: Optional[int] = None, retryable: bool = True):
        super().__init__(message, code="PROVIDER_ERROR", retryable=retryable)
        self.provider = provider
        self.status_code = status_code


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    def __init__(self, message: str, provider: str, retry_after: Optional[float] = None):
        super().__init__(message, provider=provider, retryable=True)
        self.code = "RATE_LIMIT"
        self.retry_after = retry_after


class ContextWindowError(EngineError):
    """Context window exceeded."""
    def __init__(self, message: str, tokens_used: int = 0, max_tokens: int = 0):
        super().__init__(message, code="CONTEXT_WINDOW", retryable=True)
        self.tokens_used = tokens_used
        self.max_tokens = max_tokens


class ToolExecutionError(EngineError):
    """Tool execution failed."""
    def __init__(self, message: str, tool_name: str, retryable: bool = False):
        super().__init__(message, code="TOOL_ERROR", retryable=retryable)
        self.tool_name = tool_name


class PermissionDeniedError(EngineError):
    """Permission denied for tool/action."""
    def __init__(self, message: str, tool_name: str, rule: str = ""):
        super().__init__(message, code="PERMISSION_DENIED", retryable=False)
        self.tool_name = tool_name
        self.rule = rule


class MaxIterationsError(EngineError):
    """Max iterations reached."""
    def __init__(self, iterations: int):
        super().__init__(f"Max iterations reached: {iterations}", code="MAX_ITERATIONS", retryable=False)
        self.iterations = iterations


class SubAgentError(EngineError):
    """Sub-agent execution failed."""
    def __init__(self, message: str, agent_id: str, depth: int):
        super().__init__(message, code="SUBAGENT_ERROR", retryable=False)
        self.agent_id = agent_id
        self.depth = depth
