"""
Web tools - HTTP fetch, scraping.
Replaces WebWorker.
"""
import json
from typing import Any

import httpx

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="web_fetch",
    description="Fetch content from a URL. Returns the text content of the page. Supports HTML, JSON, plain text.",
    category=ToolCategory.WEB,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "default": "GET",
            },
            "headers": {"type": "object", "description": "Custom headers"},
            "extract_text": {
                "type": "boolean",
                "description": "Extract text from HTML (default: true)",
                "default": True,
            },
            "max_length": {
                "type": "integer",
                "description": "Max content length in chars (default: 10000)",
                "default": 10000,
            },
        },
        "required": ["url"],
    },
)
async def web_fetch(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    url = args["url"]
    method = args.get("method", "GET")
    headers = args.get("headers", {})
    extract_text = args.get("extract_text", True)
    max_length = args.get("max_length", 10000)

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.request(method, url, headers=headers)

            content = response.text
            content_type = response.headers.get("content-type", "")

            # Extract text from HTML
            if extract_text and "html" in content_type:
                try:
                    from html.parser import HTMLParser
                    class TextExtractor(HTMLParser):
                        def __init__(self):
                            super().__init__()
                            self.result = []
                            self._skip = False
                        def handle_starttag(self, tag, _):
                            if tag in ("script", "style", "noscript"):
                                self._skip = True
                        def handle_endtag(self, tag):
                            if tag in ("script", "style", "noscript"):
                                self._skip = False
                        def handle_data(self, data):
                            if not self._skip:
                                text = data.strip()
                                if text:
                                    self.result.append(text)

                    extractor = TextExtractor()
                    extractor.feed(content)
                    content = "\n".join(extractor.result)
                except Exception:
                    pass  # Fall back to raw content

            # Truncate
            if len(content) > max_length:
                content = content[:max_length] + f"\n... (truncated, {len(response.text)} total chars)"

            return json.dumps({
                "url": url,
                "status_code": response.status_code,
                "content_type": content_type,
                "content": content,
                "content_length": len(content),
            })
    except httpx.TimeoutException:
        return json.dumps({"error": f"Request timed out: {url}"})
    except Exception as e:
        return json.dumps({"error": f"Fetch failed: {e}"})


WEB_TOOLS = [web_fetch]
