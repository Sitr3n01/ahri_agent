"""
File system tools - Read, write, list files.
Replaces ShellWorker.read_file(), write_file(), list_directory().

Permission levels:
- file_read: SAFE (read-only, concurrent)
- file_write: CONFIRM (modifies disk)
- file_list: SAFE (read-only, concurrent)
"""
import os
import json
from pathlib import Path
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)


@build_tool(
    name="file_read",
    description="Read the contents of a file. Returns the text content. Supports text files (txt, py, js, ts, md, json, yaml, etc).",
    category=ToolCategory.FILE_SYSTEM,
    execution_mode=ExecutionMode.CONCURRENT,  # Safe to read in parallel
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or relative file path to read",
            },
            "encoding": {
                "type": "string",
                "description": "File encoding (default: utf-8)",
                "default": "utf-8",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines to read (0 = all, default: 500)",
                "default": 500,
            },
        },
        "required": ["path"],
    },
)
async def file_read(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    path = _resolve_path(args["path"], ctx.working_directory)
    encoding = args.get("encoding", "utf-8")
    max_lines = args.get("max_lines", 500)

    if not path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    if not path.is_file():
        return json.dumps({"error": f"Not a file: {path}"})

    try:
        content = path.read_text(encoding=encoding)
        lines = content.split("\n")

        if max_lines > 0 and len(lines) > max_lines:
            content = "\n".join(lines[:max_lines])
            content += f"\n\n... (truncated, {len(lines)} total lines)"

        return json.dumps({
            "path": str(path),
            "content": content,
            "lines": min(len(lines), max_lines) if max_lines > 0 else len(lines),
            "total_lines": len(lines),
            "size_bytes": path.stat().st_size,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to read file: {e}"})


@build_tool(
    name="file_write",
    description="Write content to a file. Creates the file if it doesn't exist. Creates parent directories if needed.",
    category=ToolCategory.FILE_SYSTEM,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to write to",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
            "mode": {
                "type": "string",
                "enum": ["overwrite", "append"],
                "description": "Write mode (default: overwrite)",
                "default": "overwrite",
            },
        },
        "required": ["path", "content"],
    },
)
async def file_write(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    path = _resolve_path(args["path"], ctx.working_directory)
    content = args["content"]
    mode = args.get("mode", "overwrite")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        else:
            path.write_text(content, encoding="utf-8")

        return json.dumps({
            "path": str(path),
            "bytes_written": len(content.encode("utf-8")),
            "mode": mode,
            "success": True,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to write file: {e}"})


@build_tool(
    name="file_list",
    description="List files and directories in a given path. Returns names, sizes, and types.",
    category=ToolCategory.FILE_SYSTEM,
    execution_mode=ExecutionMode.CONCURRENT,
    permission_level=PermissionLevel.SAFE,
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list",
            },
            "recursive": {
                "type": "boolean",
                "description": "List recursively (default: false)",
                "default": False,
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern to filter (e.g., '*.py')",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results (default: 100)",
                "default": 100,
            },
        },
        "required": ["path"],
    },
)
async def file_list(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    path = _resolve_path(args["path"], ctx.working_directory)
    recursive = args.get("recursive", False)
    pattern = args.get("pattern", "*")
    max_results = args.get("max_results", 100)

    if not path.exists():
        return json.dumps({"error": f"Path not found: {path}"})

    if not path.is_dir():
        return json.dumps({"error": f"Not a directory: {path}"})

    try:
        entries = []
        glob_method = path.rglob if recursive else path.glob
        for i, entry in enumerate(glob_method(pattern)):
            if i >= max_results:
                break
            info = {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
            }
            if entry.is_file():
                info["size_bytes"] = entry.stat().st_size
            entries.append(info)

        return json.dumps({
            "path": str(path),
            "entries": entries,
            "count": len(entries),
            "truncated": len(entries) >= max_results,
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to list directory: {e}"})


def _resolve_path(path_str: str, working_dir: str) -> Path:
    """Resolve path, making relative paths relative to working_dir."""
    p = Path(path_str)
    if not p.is_absolute() and working_dir:
        p = Path(working_dir) / p
    return p.resolve()


# Export all tools for registration
FILE_TOOLS = [file_read, file_write, file_list]
