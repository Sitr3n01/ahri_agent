"""
Agent spawner - creates and manages sub-agent executions.

Sub-agents are isolated QueryEngine instances that run as tool calls.
The parent agent can spawn sub-agents to handle complex subtasks.

Depth limits prevent infinite recursion (max 3 levels by default).
"""
import logging
from typing import Optional, Any

from ..types import EngineState
from ..events import AgentEvent, EventType
from ..tools.base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)

logger = logging.getLogger("ahri.engine.agents")

# System prompts for different agent types
AGENT_PROMPTS = {
    "general": """You are a sub-agent handling a specific task.
Complete the task efficiently using the available tools.
Return a clear, concise result.""",

    "code": """You are a code-focused sub-agent.
Your job is to analyze, write, or modify code.
Use file_read and file_write tools to work with files.
Use code_analyze for review and code_generate for new code.
Always test your changes when possible.""",

    "research": """You are a research sub-agent.
Your job is to gather and synthesize information.
Use web_search and web_fetch to find information.
Use memory_search to check existing knowledge.
Provide a structured summary of your findings.""",

    "analysis": """You are an analysis sub-agent.
Your job is to deeply analyze data, code, or documents.
Provide structured analysis with clear conclusions.
Use code_analyze for code review.
Be thorough but concise.""",
}

@build_tool(
    name="spawn_agent",
    description="Spawn a sub-agent to handle a complex subtask. The sub-agent has its own context and tools. Use this for tasks that require focused, multi-step work.",
    category=ToolCategory.AGENT,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The specific goal for the sub-agent",
            },
            "agent_type": {
                "type": "string",
                "enum": ["general", "code", "research", "analysis"],
                "description": "Type of sub-agent (affects system prompt)",
                "default": "general",
            },
            "model": {
                "type": "string",
                "description": "Model to use (alias or ID). Default: same as parent.",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Max iterations for sub-agent (default: 20)",
                "default": 20,
            },
        },
        "required": ["goal"],
    },
)
async def spawn_agent(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    """Spawn a sub-agent with isolated context."""
    import json

    goal = args["goal"]
    agent_type = args.get("agent_type", "general")
    model = args.get("model", ctx.default_model)
    max_iterations = args.get("max_iterations", 20)

    # Get current depth from context metadata
    current_depth = ctx.metadata.get("depth", 0)
    max_depth = ctx.metadata.get("max_depth", 3)

    if current_depth >= max_depth:
        return json.dumps({
            "error": f"Max agent depth reached ({max_depth}). Cannot spawn more sub-agents.",
            "depth": current_depth,
        })

    # Get system prompt for agent type
    system_prompt = AGENT_PROMPTS.get(agent_type, AGENT_PROMPTS["general"])

    # Import here to avoid circular import
    from ..query_engine import QueryEngine

    engine = QueryEngine(
        model_registry=ctx.model_registry,
        tool_registry=ctx.tool_registry,
        settings=ctx.settings,
        permission_manager=ctx.permission_manager,
        hook_manager=ctx.hook_manager,
        compact_manager=ctx.metadata.get("compact_manager"),
    )

    # Collect results
    final_content = ""
    total_tokens = 0
    iterations = 0

    async for event in engine.run(
        goal=goal,
        system_prompt=system_prompt,
        model=model,
        max_iterations=max_iterations,
        parent_id=ctx.execution_id,
        depth=current_depth + 1,
    ):
        if event.type == EventType.FINAL_RESPONSE:
            final_content = event.data.get("content", "")
            total_tokens = event.data.get("total_tokens", 0)
            iterations = event.data.get("iterations", 0)
        elif event.type == EventType.ERROR:
            return json.dumps({
                "error": event.data.get("error", "Sub-agent failed"),
                "agent_type": agent_type,
            })

    return json.dumps({
        "result": final_content,
        "agent_type": agent_type,
        "iterations": iterations,
        "total_tokens": total_tokens,
        "depth": current_depth + 1,
    })

AGENT_TOOLS = [spawn_agent]
