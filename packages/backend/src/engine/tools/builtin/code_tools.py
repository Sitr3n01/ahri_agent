"""
Code analysis and generation tools.
Replaces CodeWorker functionality.
"""
import json
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="code_analyze",
    description="Analyze code for bugs, quality issues, security vulnerabilities, or understanding. Provide the code or a file path.",
    category=ToolCategory.CODE,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code to analyze (if not using file_path)"},
            "file_path": {"type": "string", "description": "Path to file to analyze"},
            "analysis_type": {
                "type": "string",
                "enum": ["bugs", "security", "quality", "explain", "review"],
                "description": "Type of analysis",
                "default": "review",
            },
            "language": {"type": "string", "description": "Programming language (auto-detected if not provided)"},
        },
        "required": [],
    },
)
async def code_analyze(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    code = args.get("code", "")
    file_path = args.get("file_path", "")
    analysis_type = args.get("analysis_type", "review")
    language = args.get("language", "")

    # If file_path provided, read the file
    if file_path and not code:
        from pathlib import Path
        p = Path(file_path)
        if p.exists():
            code = p.read_text(encoding="utf-8")
            if not language:
                ext_map = {".py": "python", ".js": "javascript", ".ts": "typescript", ".rs": "rust"}
                language = ext_map.get(p.suffix, p.suffix[1:])

    if not code:
        return json.dumps({"error": "No code provided. Use 'code' or 'file_path' parameter."})

    prompt = f"""Analyze the following {language} code. Focus on: {analysis_type}

```{language}
{code}
```

Return a JSON object with:
- "issues": list of {{"severity", "line", "description", "suggestion"}}
- "summary": brief overall assessment
- "score": quality score 1-10
"""

    result = await ctx.call_llm(
        messages=[{"role": "user", "content": prompt}],
        json_mode=True,
    )

    return result.content if hasattr(result, 'content') else str(result)


@build_tool(
    name="code_generate",
    description="Generate code based on a description. Specify the language, requirements, and any constraints.",
    category=ToolCategory.CODE,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "What the code should do"},
            "language": {"type": "string", "description": "Programming language"},
            "context": {"type": "string", "description": "Additional context or requirements"},
            "style": {
                "type": "string",
                "enum": ["minimal", "production", "documented"],
                "default": "production",
            },
        },
        "required": ["description", "language"],
    },
)
async def code_generate(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    description = args["description"]
    language = args["language"]
    context = args.get("context", "")
    style = args.get("style", "production")

    prompt = f"""Generate {language} code that: {description}

Style: {style}
{f"Context: {context}" if context else ""}

Return ONLY the code, no explanations. Use best practices for {language}.
"""

    result = await ctx.call_llm(
        messages=[{"role": "user", "content": prompt}],
    )

    return json.dumps({
        "language": language,
        "code": result.content if hasattr(result, 'content') else str(result),
        "description": description,
    })


CODE_TOOLS = [code_analyze, code_generate]
