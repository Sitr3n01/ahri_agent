"""
Search tools - Google Custom Search.
"""
import json
from typing import Any
import httpx

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="web_search",
    description="Search the web using Google Custom Search. Returns relevant results with titles, URLs, and snippets.",
    category=ToolCategory.SEARCH,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {
                "type": "integer",
                "description": "Number of results (max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def web_search(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    query = args["query"]
    num = min(args.get("num_results", 5), 10)

    settings = ctx.settings
    if not settings or not settings.cse_api_key:
        return json.dumps({"error": "Google Search API not configured", "results": []})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.cse_api_key,
                    "cx": settings.cse_cx,
                    "q": query,
                    "num": num,
                },
            )
            data = response.json()
            items = data.get("items", [])

            results = []
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })

            return json.dumps({"query": query, "results": results, "count": len(results)})

    except Exception as e:
        return json.dumps({"error": f"Search failed: {e}", "results": []})


SEARCH_TOOLS = [web_search]
