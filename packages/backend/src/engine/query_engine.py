"""
Core Query Engine - The agentic loop.

This is the heart of the V4 Engine. It implements an async generator
that yields AgentEvent objects for real-time streaming to the frontend.

Inspired by Claude Code's query.ts:
1. Build system prompt + history
2. Call LLM with tools
3. If tool_calls in response → execute tools → add results to history → loop
4. If no tool_calls → yield final response → stop
5. If context too large → compact → continue
6. If max iterations → force stop

The async generator pattern allows the frontend to consume events
in real-time via WebSocket without blocking.
"""
import asyncio
import logging
import time
from typing import AsyncGenerator, Optional

from .types import (
    Message, Role, ToolCall, ToolResult, LLMResponse,
    EngineState, StopReason, ContinuationDecision
)
from .events import AgentEvent, EventType
from .errors import (
    EngineError, ProviderError, RateLimitError,
    ContextWindowError, MaxIterationsError,
    ToolExecutionError,
)
from .model_registry import ModelRegistry
from .tools.registry import ToolRegistry
from .tools.base import ToolUseContext

logger = logging.getLogger("ahri.engine.query")


class QueryEngine:
    """
    The core agentic loop as an async generator.

    Usage:
        engine = QueryEngine(model_registry, tool_registry, settings)
        async for event in engine.run(goal, system_prompt, model):
            send_to_websocket(event.to_dict())
    """

    def __init__(
        self,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        settings=None,
        permission_manager=None,
        hook_manager=None,
        compact_manager=None,
    ):
        self.model_registry = model_registry
        self.tool_registry = tool_registry
        self.settings = settings
        self.permission_manager = permission_manager
        self.hook_manager = hook_manager
        self.compact_manager = compact_manager

    async def run(
        self,
        goal: str,
        system_prompt: str = "",
        model: str = "fast",
        max_iterations: int = 50,
        context: Optional[dict] = None,
        parent_id: Optional[str] = None,
        depth: int = 0,
        input_queue: Optional[asyncio.Queue] = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Run the agentic loop.

        Args:
            goal: User's goal/message
            system_prompt: System prompt for the LLM
            model: Model alias or ID
            max_iterations: Safety limit
            context: Additional context (dependencies, etc.)
            parent_id: Parent execution ID (for sub-agents)
            depth: Nesting depth (0 = root)

        Yields:
            AgentEvent objects for real-time streaming
        """
        # Initialize state
        state = self._init_state(goal, system_prompt, model, max_iterations, parent_id, depth)

        yield AgentEvent.engine_start(state.execution_id, model, goal)

        try:
            # Main agentic loop
            while state.iteration < state.max_iterations and not state.is_cancelled:
                state.iteration += 1

                yield AgentEvent(
                    type=EventType.ITERATION_START,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={"total_tokens": state.total_tokens},
                )

                # ── Step 1: Call LLM ──
                try:
                    tools = self.tool_registry.get_function_declarations()

                    yield AgentEvent(
                        type=EventType.LLM_REQUEST,
                        execution_id=state.execution_id,
                        iteration=state.iteration,
                        data={"model": state.model, "message_count": len(state.messages)},
                    )

                    llm_response = await self._call_llm(state, tools)

                    state.total_input_tokens += llm_response.input_tokens
                    state.total_output_tokens += llm_response.output_tokens

                    has_tool_calls = bool(llm_response.tool_calls)

                    yield AgentEvent(
                        type=EventType.LLM_RESPONSE,
                        execution_id=state.execution_id,
                        iteration=state.iteration,
                        data={
                            "has_tool_calls": has_tool_calls,
                            "tool_count": len(llm_response.tool_calls) if has_tool_calls else 0,
                            "content_preview": llm_response.content[:200] if llm_response.content else "",
                            "input_tokens": llm_response.input_tokens,
                            "output_tokens": llm_response.output_tokens,
                            "thinking": llm_response.thinking[:500] if getattr(llm_response, 'thinking', None) else None,
                        },
                    )

                except RateLimitError as e:
                    yield AgentEvent.error(state.execution_id, f"Rate limit: {e}", "RATE_LIMIT")
                    await asyncio.sleep(getattr(e, 'retry_after', 5))
                    continue

                except ContextWindowError:
                    # Auto-compact and retry
                    yield AgentEvent(type=EventType.COMPACT_START, execution_id=state.execution_id)
                    await self._compact_context(state)
                    yield AgentEvent(type=EventType.COMPACT_END, execution_id=state.execution_id)
                    continue

                except ProviderError as e:
                    yield AgentEvent.error(state.execution_id, str(e), getattr(e, 'code', 'PROVIDER_ERROR'))
                    if getattr(e, 'retryable', False):
                        await asyncio.sleep(2)
                        continue
                    break

                # ── Step 2: Check if LLM wants to use tools ──
                if not getattr(llm_response, 'tool_calls', None):
                    # No tools → final response
                    if llm_response.content:
                        # Stream the text content
                        yield AgentEvent.text_chunk(
                            state.execution_id,
                            llm_response.content,
                            state.iteration,
                        )

                    # Add assistant message to history
                    state.add_message(Message(
                        role=Role.ASSISTANT,
                        content=llm_response.content,
                        token_count=llm_response.output_tokens,
                    ))

                    yield AgentEvent(
                        type=EventType.FINAL_RESPONSE,
                        execution_id=state.execution_id,
                        data={
                            "content": llm_response.content,
                            "total_tokens": state.total_tokens,
                            "iterations": state.iteration,
                        },
                    )
                    break

                # ── Step 3: Execute tool calls ──
                # Add assistant message with tool calls
                state.add_message(Message(
                    role=Role.ASSISTANT,
                    content=llm_response.content,
                    tool_calls=llm_response.tool_calls,
                    token_count=llm_response.output_tokens,
                ))

                # Execute each tool with events
                tool_results = []
                async for event in self._execute_tools(state, llm_response.tool_calls, input_queue):
                    if isinstance(event, list):
                        tool_results = event
                        break
                    yield event

                # Add tool results to history
                for result in tool_results:
                    state.add_message(Message(
                        role=Role.TOOL_RESULT,
                        content=str(result.output) if not result.is_error else f"Error: {result.error}",
                        tool_results=[result],
                        metadata={"tool_name": result.tool_name},
                    ))

                # ── Step 4: Check if compaction needed ──
                decision = self._decide_continuation(state)
                if decision == ContinuationDecision.COMPACT:
                    yield AgentEvent(type=EventType.COMPACT_START, execution_id=state.execution_id)
                    await self._compact_context(state)
                    yield AgentEvent(type=EventType.COMPACT_END, execution_id=state.execution_id)

                yield AgentEvent(
                    type=EventType.ITERATION_END,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={"total_tokens": state.total_tokens},
                )

            # Loop ended
            if state.iteration >= state.max_iterations:
                yield AgentEvent.error(
                    state.execution_id,
                    f"Max iterations reached ({state.max_iterations})",
                    "MAX_ITERATIONS",
                )

        except asyncio.CancelledError:
            yield AgentEvent(
                type=EventType.CANCELLED,
                execution_id=state.execution_id,
                data={"reason": "User cancelled"},
            )

        except Exception as e:
            logger.exception(f"Engine error: {e}")
            yield AgentEvent.error(state.execution_id, str(e), "INTERNAL_ERROR")

        finally:
            yield AgentEvent.engine_stop(
                state.execution_id,
                "completed" if not state.is_cancelled else "cancelled",
                state.total_tokens,
            )

    def _init_state(
        self, goal: str, system_prompt: str, model: str,
        max_iterations: int, parent_id: Optional[str], depth: int,
    ) -> EngineState:
        """Initialize engine state for a new execution."""
        state = EngineState(
            model=model,
            system_prompt=system_prompt or self._build_default_system_prompt(),
            max_iterations=max_iterations,
            depth=depth,
            parent_id=parent_id,
        )

        # Add user message
        state.add_message(Message(role=Role.USER, content=goal))

        return state

    def _build_default_system_prompt(self) -> str:
        """Build a default system prompt listing available tools."""
        tools = self.tool_registry.get_enabled()
        tool_list = "\n".join(f"- {t.name}: {t.description}" for t in tools)

        return f"""You are Ahri, an AI assistant with access to tools.

Available tools:
{tool_list}

Use tools when needed to complete the user's request.
Always explain what you're doing before and after using tools.
If a tool fails, try an alternative approach.
"""

    async def _call_llm(self, state: EngineState, tools: list[dict]) -> LLMResponse:
        """Call the LLM with current state."""
        # Build messages in provider format
        messages = []

        # System prompt as first message
        if state.system_prompt:
            messages.append({"role": "system", "content": state.system_prompt})

        # Conversation history
        for msg in state.messages:
            if msg.role == Role.TOOL_RESULT:
                messages.append({
                    "role": "tool_result",
                    "content": msg.content,
                    "tool_name": msg.metadata.get("tool_name", ""),
                })
            else:
                entry = {"role": msg.role.value, "content": msg.content}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {"name": tc.tool_name, "arguments": tc.arguments}
                        for tc in msg.tool_calls
                    ]
                messages.append(entry)

        # Call model registry
        return await self.model_registry.call(
            model_or_alias=state.model,
            messages=messages,
            tools=tools if tools else None,
        )

    async def _execute_tools(
        self, state: EngineState, tool_calls: list[ToolCall], input_queue: asyncio.Queue,
    ) -> AsyncGenerator[AgentEvent | list[ToolResult], None]:
        """Execute tool calls with permission checks and events.
        
        Yields AgentEvent objects for real-time progress.
        Finally yields the list of ToolResult objects.
        """
        # Build context for tools
        context = ToolUseContext(
            model_registry=self.model_registry,
            tool_registry=self.tool_registry,
            permission_manager=self.permission_manager,
            hook_manager=self.hook_manager,
            execution_id=state.execution_id,
            default_model=state.model,
            settings=self.settings,
        )

        # Result tracking
        results_map: dict[str, ToolResult] = {}
        pending_calls: list[ToolCall] = []

        # Phase 1: Permission evaluations
        for call in tool_calls:
            decision = PermissionDecision.ALLOW
            if self.permission_manager:
                decision = await self.permission_manager.check(call.tool_name, call.arguments)

            if decision == PermissionDecision.DENY:
                results_map[call.id] = ToolResult(
                    tool_call_id=call.id,
                    tool_name=call.tool_name,
                    error=f"Permission denied for tool: {call.tool_name}",
                    metadata={"status": "denied"}
                )
                logger.warning(f"Permission denied for tool: {call.tool_name}")
                continue

            if decision == PermissionDecision.ASK:
                # Emit event and WAIT for response from input_queue
                yield AgentEvent(
                    type=EventType.TOOL_PERMISSION_ASK,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={
                        "tool_call_id": call.id,
                        "tool_name": call.tool_name,
                        "arguments": call.arguments,
                        "tool_kwargs": call.arguments, # Web-compat alias
                    },
                )
                
                # Wait for user input
                logger.info(f"Awaiting user permission for tool: {call.tool_name}")
                response = await input_queue.get()
                
                approved = response.get("approved", False) if isinstance(response, dict) else False
                if not approved:
                    results_map[call.id] = ToolResult(
                        tool_call_id=call.id,
                        tool_name=call.tool_name,
                        error=f"User rejected execution of tool: {call.tool_name}",
                        metadata={"status": "rejected"}
                    )
                    logger.info(f"User rejected tool: {call.tool_name}")
                    continue

            # If we are here, it's allowed or approved
            pending_calls.append(call)

        # Phase 2: Execution (Batch)
        if pending_calls:
            # Pre-hooks + TOOL_USE_START
            for call in pending_calls:
                if self.hook_manager:
                    await self.hook_manager.emit("pre_tool_use", {
                        "tool_name": call.tool_name,
                        "arguments": call.arguments,
                    })
                yield AgentEvent(
                    type=EventType.TOOL_USE_START,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={
                        "tool_name": call.tool_name,
                        "arguments": call.arguments,
                        "tool_kwargs": call.arguments,
                    }
                )

            # Actual execution
            batch_results = await self.tool_registry.execute_batch(pending_calls, context)
            
            # Post-hooks + TOOL_USE_END
            for call, result in zip(pending_calls, batch_results):
                results_map[call.id] = result
                if self.hook_manager:
                    await self.hook_manager.emit("post_tool_use", {
                        "tool_name": result.tool_name,
                        "output": result.output,
                        "error": result.error,
                        "duration_ms": result.duration_ms,
                    })
                yield AgentEvent(
                    type=EventType.TOOL_USE_END,
                    execution_id=state.execution_id,
                    iteration=state.iteration,
                    data={
                        "tool_name": result.tool_name,
                        "output": result.output,
                        "error": result.error,
                        "duration_ms": result.duration_ms,
                    }
                )

        # Phase 3: Final Merge in original order
        final_results: list[ToolResult] = []
        for call in tool_calls:
            final_results.append(results_map.get(call.id) or ToolResult(
                tool_call_id=call.id,
                tool_name=call.tool_name,
                error="Internal error: Tool execution skipped unexpectedly"
            ))

        yield final_results

    def _decide_continuation(self, state: EngineState) -> ContinuationDecision:
        """
        Decide whether to continue, stop, or compact.
        Inspired by Claude Code's continuation logic.
        """
        # Check context window usage
        threshold = getattr(self.settings, 'engine_compact_threshold', 0.80) if self.settings else 0.80

        # Estimate context usage
        try:
            model_info = self.model_registry.resolve(state.model)
            context_window = getattr(model_info.capabilities, 'context_window', 0)
            usage_ratio = state.total_tokens / context_window if context_window > 0 else 0

            if usage_ratio > threshold:
                return ContinuationDecision.COMPACT
        except KeyError:
            pass

        return ContinuationDecision.CONTINUE

    async def _compact_context(self, state: EngineState):
        """
        Compact the conversation history to free context window space.

        Strategy: Keep system prompt + first user message + last N messages.
        Summarize the middle using the cheapest available model.
        """
        if self.compact_manager:
            keep_recent = getattr(self.settings, 'engine_compact_keep_recent', 4) if self.settings else 4
            state.messages = await self.compact_manager.compact(
                state.messages,
                keep_recent=keep_recent,
            )
        else:
            # Simple fallback: keep first message + last N messages
            # Use Role.USER for summary to avoid Gemini silently dropping system role
            keep = getattr(self.settings, 'engine_compact_keep_recent', 4) if self.settings else 4
            if len(state.messages) > keep + 1:
                first_msg = state.messages[0]
                recent = state.messages[-keep:]
                summary = Message(
                    role=Role.USER,
                    content=f"[Context summary: Previous {len(state.messages) - keep - 1} messages were compacted. "
                            f"Key context has been preserved in the remaining messages.]",
                )
                state.messages = [first_msg, summary] + recent

        logger.info(f"Compacted context to {len(state.messages)} messages")
