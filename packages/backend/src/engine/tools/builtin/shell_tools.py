"""
Shell command execution tool.
Replaces ShellWorker.execute_command().

IMPORTANT: Only allowed commands are executed. Uses allowlist approach.
"""
import asyncio
import json
import os
import subprocess
from typing import Any

from ..base import (
    build_tool, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)

# Commands that are safe to execute without confirmation
SAFE_COMMANDS = {
    "ls", "dir", "pwd", "whoami", "date", "echo",
    "cat", "head", "tail", "wc", "sort", "uniq",
    "find", "grep", "which", "type", "where",
    "python", "pip", "node", "npm", "git",
}

# Commands that are NEVER allowed
BLOCKED_COMMANDS = {
    "rm", "rmdir", "del", "format", "mkfs",
    "shutdown", "reboot", "kill", "taskkill",
    "curl", "wget",  # Use web_fetch tool instead
}


@build_tool(
    name="shell_execute",
    description="Execute a shell command and return stdout/stderr. Use for system commands, running scripts, git operations, package management, etc.",
    category=ToolCategory.SHELL,
    execution_mode=ExecutionMode.SERIAL,
    permission_level=PermissionLevel.CONFIRM,
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory (default: current)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        "required": ["command"],
    },
)
async def shell_execute(ctx: ToolUseContext, args: dict[str, Any]) -> str:
    command = args["command"]
    working_dir = args.get("working_dir", ctx.working_directory)
    timeout = args.get("timeout", 30)

    # Extract base command for safety check
    base_cmd = command.strip().split()[0].lower() if command.strip() else ""

    if base_cmd in BLOCKED_COMMANDS:
        return json.dumps({
            "error": f"Command '{base_cmd}' is blocked for safety. Use dedicated tools instead.",
            "blocked": True,
        })

    try:
        loop = asyncio.get_running_loop()

        def _run():
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir or None,
            )
            return result

        result = await loop.run_in_executor(None, _run)

        return json.dumps({
            "command": command,
            "stdout": result.stdout[:10000],  # Limit output size
            "stderr": result.stderr[:5000],
            "return_code": result.returncode,
            "success": result.returncode == 0,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s", "command": command})
    except Exception as e:
        return json.dumps({"error": f"Command execution failed: {e}", "command": command})


SHELL_TOOLS = [shell_execute]
