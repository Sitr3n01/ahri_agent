"""
Memory tools - Search and store memories.
Replaces MemoryWorker.
"""
import json
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="memory_search",
    description="Search through persona memories (episodic, profile, and session memories). Uses semantic search via ChromaDB.",
    category=ToolCategory.MEMORY,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "memory_type": {
                "type": "string",
                "enum": ["all", "episodic", "profile", "session"],
                "default": "all",
            },
            "max_results": {
                "type": "integer",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def memory_search(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    query = args["query"]
    memory_type = args.get("memory_type", "all")
    max_results = args.get("max_results", 5)

    # Use VectorService if available in context
    vector_svc = ctx.metadata.get("vector_service")
    if not vector_svc:
        return json.dumps({"error": "Vector service not available", "results": []})

    try:
        results = vector_svc.search(query, n_results=max_results)
        return json.dumps({
            "query": query,
            "results": results,
            "count": len(results),
        })
    except Exception as e:
        return json.dumps({"error": f"Memory search failed: {e}", "results": []})


@build_tool(
    name="memory_store",
    description="Store a new memory. The memory will be semantically searchable later.",
    category=ToolCategory.MEMORY,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Memory content to store"},
            "memory_type": {
                "type": "string",
                "enum": ["episodic", "profile", "knowledge"],
                "default": "episodic",
            },
            "importance": {
                "type": "string",
                "enum": ["critical", "important", "useful", "trivial"],
                "default": "useful",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for categorization",
            },
        },
        "required": ["content"],
    },
)
async def memory_store(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    content = args["content"]
    memory_type = args.get("memory_type", "episodic")
    importance = args.get("importance", "useful")
    tags = args.get("tags", [])

    vector_svc = ctx.metadata.get("vector_service")
    if not vector_svc:
        return json.dumps({"error": "Vector service not available"})

    try:
        doc_id = vector_svc.add(content, metadata={
            "type": memory_type,
            "importance": importance,
            "tags": tags,
        })
        return json.dumps({
            "stored": True,
            "id": doc_id,
            "memory_type": memory_type,
            "importance": importance,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to store memory: {e}"})


MEMORY_TOOLS = [memory_search, memory_store]
