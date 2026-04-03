"""
Shell Worker - Specialized agent for shell command execution and file operations.
Uses the configured agent model for command interpretation and safety checks.

Capabilities:
- Execute shell commands (with safety validation)
- File operations (create, read, move, delete)
- Directory operations
- Process management
- System information gathering

ReAct mode: Iteratively read → write → execute → verify file operations.
"""
import subprocess
import shutil
import os
import json
from pathlib import Path
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker
from src.services.workers.react_loop import ToolDefinition, ToolResult


class ShellWorker(BaseWorker):
    """Worker for shell command execution and file operations with ReAct loop."""

    # ── ReAct Configuration ──
    REACT_ENABLED = True
    REACT_MAX_ITERATIONS = 5
    REACT_TOKEN_BUDGET = 4000

    ROLE_PROMPT = (
        "[ROLE: System Operations Agent]\n"
        "You execute file operations and shell commands safely.\n"
        "NEVER run destructive commands (rm -rf, format, dd, etc.).\n"
        "Always validate paths before operations. Report exact output.\n"
        "For file reads: return content. For writes: confirm success.\n"
        "When using tools, verify operations by reading files or listing directories after writing."
    )

    def get_tools(self) -> list[ToolDefinition]:
        """Define tools for ReAct mode."""
        return [
            ToolDefinition(
                name="run_command",
                description="Run a shell command (blocked: rm, del, format, shutdown, curl, wget). Input: {\"command\": str}",
                parameters={
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]
                },
                handler=self._tool_run_command,
            ),
            ToolDefinition(
                name="read_file",
                description="Read file contents. Input: {\"path\": str}",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"]
                },
                handler=self._tool_read_file,
            ),
            ToolDefinition(
                name="write_file",
                description="Write content to a file, creating parent dirs if needed. Input: {\"path\": str, \"content\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                },
                handler=self._tool_write_file,
            ),
            ToolDefinition(
                name="list_directory",
                description="List files/folders in a directory. Input: {\"path\": str, \"recursive\": bool}",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "recursive": {"type": "boolean"}
                    },
                    "required": ["path"]
                },
                handler=self._tool_list_directory,
            ),
        ]

    # ── ReAct Tool Handlers ──────────────────────────────────────────

    async def _tool_run_command(self, params: dict) -> ToolResult:
        """Tool wrapper for command execution."""
        try:
            result = await self._execute_command({"command": params.get("command", "")}, None)
            if result.get("blocked"):
                return ToolResult(
                    tool_name="run_command", success=False, output="",
                    error=f"BLOCKED: {result.get('reason', 'Security violation')}"
                )
            output = result.get("stdout", "")
            if result.get("stderr"):
                output += f"\nstderr: {result['stderr']}"
            return ToolResult(
                tool_name="run_command",
                success=result.get("success", False),
                output=f"Exit code: {result.get('return_code', -1)}\n{output}",
                error=result.get("error"),
            )
        except Exception as e:
            return ToolResult(tool_name="run_command", success=False, output="", error=str(e))

    async def _tool_read_file(self, params: dict) -> ToolResult:
        """Tool wrapper for file read."""
        try:
            result = await self._read_file({"path": params.get("path", "")})
            if result.get("error"):
                return ToolResult(tool_name="read_file", success=False, output="", error=result["error"])
            content = result.get("content", "")
            return ToolResult(
                tool_name="read_file", success=True,
                output=f"File: {result.get('path')} ({result.get('lines', 0)} lines)\n{content}"
            )
        except Exception as e:
            return ToolResult(tool_name="read_file", success=False, output="", error=str(e))

    async def _tool_write_file(self, params: dict) -> ToolResult:
        """Tool wrapper for file write."""
        try:
            result = await self._write_file({
                "path": params.get("path", ""),
                "content": params.get("content", "")
            })
            if result.get("written"):
                return ToolResult(
                    tool_name="write_file", success=True,
                    output=f"Written to {result.get('path')} ({result.get('size_bytes', 0)} bytes)"
                )
            return ToolResult(tool_name="write_file", success=False, output="", error=result.get("error", "Write failed"))
        except Exception as e:
            return ToolResult(tool_name="write_file", success=False, output="", error=str(e))

    async def _tool_list_directory(self, params: dict) -> ToolResult:
        """Tool wrapper for directory listing."""
        try:
            result = await self._list_directory({
                "path": params.get("path", "."),
                "recursive": params.get("recursive", False)
            })
            if result.get("error"):
                return ToolResult(tool_name="list_directory", success=False, output="", error=result["error"])
            items = result.get("items", [])
            listing = "\n".join(
                f"{'[DIR]' if not item.get('is_file') else '[FILE]'} {item.get('name', item.get('path', ''))}"
                + (f" ({item.get('size', 0)} bytes)" if item.get('is_file') else "")
                for item in items[:50]  # Limit to 50 entries
            )
            if len(items) > 50:
                listing += f"\n... and {len(items) - 50} more items"
            return ToolResult(
                tool_name="list_directory", success=True,
                output=f"Directory: {result.get('path')} ({result.get('count', 0)} items)\n{listing}"
            )
        except Exception as e:
            return ToolResult(tool_name="list_directory", success=False, output="", error=str(e))

    # Comandos bloqueados por segurança
    BLOCKED_COMMANDS = {
        "rm", "del", "format", "mkfs", "dd",  # Destrutivos
        "shutdown", "reboot", "poweroff",      # Sistema
        "curl", "wget", "nc", "netcat",        # Network (usar WebWorker)
    }

    # Diretórios protegidos
    PROTECTED_DIRS = {
        "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
        "/bin", "/sbin", "/etc", "/usr", "/sys", "/proc"
    }

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Shell",
            default_model="LITE"
        )

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Execute shell or file operation.

        Input format:
        {
            "operation": "command" | "file_read" | "file_write" | "file_delete" | "list_dir",
            "command": "shell command",        (for operation=command)
            "path": "file/dir path",           (for file ops)
            "content": "file content",         (for file_write)
            "recursive": true/false            (for list_dir)
        }
        """
        operation = input_data.get("operation", "command")

        import time
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            if operation == "command":
                result = await self._execute_command(input_data, db)
            elif operation == "file_read":
                result = await self._read_file(input_data)
            elif operation == "file_write":
                result = await self._write_file(input_data)
            elif operation == "file_delete":
                result = await self._delete_file(input_data)
            elif operation == "list_dir":
                result = await self._list_directory(input_data)
            elif operation == "file_move":
                result = await self._move_file(input_data)
            else:
                raise ValueError(f"Unknown operation: {operation}")

            tokens = self._estimate_tokens(str(result))
            return await self._complete_task(db, task, result, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)

    async def _execute_command(self, input_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """Execute shell command with safety validation."""
        command = input_data.get("command", "")

        # Safety check via LLM
        safety_prompt = f"""Analise o seguinte comando shell e classifique seu nível de risco:

Comando: {command}

Retorne JSON:
{{
    "is_safe": true/false,
    "risk_level": "safe|caution|dangerous",
    "reason": "explicação do risco",
    "suggestion": "versão mais segura do comando (se aplicável)"
}}

Comandos destrutivos (rm -rf, format, etc) devem ser marcados como dangerous.
"""

        safety_check = await self._call_llm(
            prompt=safety_prompt,
            model=self.default_model,
            schema={
                "type": "object",
                "properties": {
                    "is_safe": {"type": "boolean"},
                    "risk_level": {"type": "string"},
                    "reason": {"type": "string"},
                    "suggestion": {"type": "string"}
                },
                "required": ["is_safe", "risk_level", "reason"]
            }
        )

        # Block se dangerous
        if safety_check.get("risk_level") == "dangerous":
            return {
                "executed": False,
                "blocked": True,
                "reason": safety_check.get("reason"),
                "suggestion": safety_check.get("suggestion")
            }

        # Check blocked commands
        cmd_parts = command.lower().split()
        if cmd_parts and cmd_parts[0] in self.BLOCKED_COMMANDS:
            return {
                "executed": False,
                "blocked": True,
                "reason": f"Comando bloqueado por segurança: {cmd_parts[0]}"
            }

        try:
            # Execute com timeout
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )

            return {
                "executed": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "success": result.returncode == 0,
                "safety_check": safety_check
            }

        except subprocess.TimeoutExpired:
            return {
                "executed": False,
                "error": "Command timeout (30s limit)"
            }

    async def _read_file(self, input_data: Dict) -> Dict[str, Any]:
        """Read file contents."""
        path = Path(input_data.get("path", ""))

        if not path.exists():
            return {"error": f"File not found: {path}"}

        if not path.is_file():
            return {"error": f"Not a file: {path}"}

        try:
            # Limit file size to 10MB
            if path.stat().st_size > 10 * 1024 * 1024:
                return {"error": "File too large (>10MB)"}

            content = path.read_text(encoding='utf-8', errors='replace')

            return {
                "content": content,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "lines": len(content.splitlines())
            }

        except Exception as e:
            return {"error": f"Failed to read file: {str(e)}"}

    async def _write_file(self, input_data: Dict) -> Dict[str, Any]:
        """Write content to file."""
        path = Path(input_data.get("path", ""))
        content = input_data.get("content", "")

        # Resolve content from dependency_results if not provided directly
        if not content:
            dep_results = input_data.get("dependency_results", {})
            for dep_idx in sorted(dep_results.keys(), key=lambda x: int(x), reverse=True):
                dep = dep_results[dep_idx]
                if isinstance(dep, dict):
                    # Dynamic worker output: {"result": "...code..."}
                    if dep.get("result"):
                        content = dep["result"]
                        break
                    # Code worker output: {"code": "..."}
                    if dep.get("code"):
                        content = dep["code"]
                        break
                    # Shell worker output with stdout
                    if dep.get("stdout"):
                        content = dep["stdout"]
                        break
                elif isinstance(dep, str) and dep.strip():
                    content = dep
                    break

        # Check protected directories
        for protected in self.PROTECTED_DIRS:
            if str(path).startswith(protected):
                return {
                    "written": False,
                    "error": f"Cannot write to protected directory: {protected}"
                }

        try:
            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            path.write_text(content, encoding='utf-8')

            return {
                "written": True,
                "path": str(path),
                "size_bytes": path.stat().st_size
            }

        except Exception as e:
            return {
                "written": False,
                "error": f"Failed to write file: {str(e)}"
            }

    async def _delete_file(self, input_data: Dict) -> Dict[str, Any]:
        """Delete file or directory."""
        path = Path(input_data.get("path", ""))

        # Check protected directories
        for protected in self.PROTECTED_DIRS:
            if str(path).startswith(protected):
                return {
                    "deleted": False,
                    "error": f"Cannot delete from protected directory: {protected}"
                }

        if not path.exists():
            return {"error": f"Path not found: {path}"}

        try:
            was_directory = path.is_dir()
            if path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)

            return {
                "deleted": True,
                "path": str(path),
                "was_directory": was_directory
            }

        except Exception as e:
            return {
                "deleted": False,
                "error": f"Failed to delete: {str(e)}"
            }

    async def _list_directory(self, input_data: Dict) -> Dict[str, Any]:
        """List directory contents."""
        path = Path(input_data.get("path", "."))
        recursive = input_data.get("recursive", False)

        if not path.exists():
            return {"error": f"Directory not found: {path}"}

        if not path.is_dir():
            return {"error": f"Not a directory: {path}"}

        try:
            if recursive:
                items = [
                    {
                        "path": str(p.relative_to(path)),
                        "is_file": p.is_file(),
                        "size": p.stat().st_size if p.is_file() else None
                    }
                    for p in path.rglob("*")
                ]
            else:
                items = [
                    {
                        "name": p.name,
                        "is_file": p.is_file(),
                        "size": p.stat().st_size if p.is_file() else None
                    }
                    for p in path.iterdir()
                ]

            return {
                "path": str(path),
                "items": items,
                "count": len(items),
                "recursive": recursive
            }

        except Exception as e:
            return {"error": f"Failed to list directory: {str(e)}"}

    async def _move_file(self, input_data: Dict) -> Dict[str, Any]:
        """Move/rename file or directory."""
        src = Path(input_data.get("source", ""))
        dst = Path(input_data.get("destination", ""))

        # Check protected directories
        for protected in self.PROTECTED_DIRS:
            if str(src).startswith(protected) or str(dst).startswith(protected):
                return {
                    "moved": False,
                    "error": f"Cannot move to/from protected directory: {protected}"
                }

        if not src.exists():
            return {"error": f"Source not found: {src}"}

        try:
            shutil.move(str(src), str(dst))

            return {
                "moved": True,
                "source": str(src),
                "destination": str(dst)
            }

        except Exception as e:
            return {
                "moved": False,
                "error": f"Failed to move: {str(e)}"
            }
