"""
Adapter to wrap V3 Workers as V4 Tools.

This allows gradual migration: existing workers continue to work
through the adapter while new tools are written natively.

Usage:
    from src.services.workers.code_worker import CodeWorker
    tool = WorkerToolAdapter.from_worker(code_worker, "code_analyze")
    registry.register(tool)
"""
import json
import logging
from typing import Any, Optional

from ..tools.base import (
    ToolDefinition, ToolUseContext, ToolCategory,
    ExecutionMode, PermissionLevel,
)

logger = logging.getLogger("ahri.engine.migration")


class WorkerToolAdapter:
    """
    Wraps a V3 BaseWorker as a V4 ToolDefinition.

    Maps the worker's execute() method to a tool handler function,
    bridging the V3 worker architecture (class-based, LLMService dependency)
    with the V4 tool architecture (function-based, ToolUseContext injection).
    """

    @staticmethod
    def from_worker(
        worker,           # BaseWorker instance
        tool_name: str,
        description: str = "",
        category: ToolCategory = ToolCategory.CUSTOM,
        execution_mode: ExecutionMode = ExecutionMode.SERIAL,
        permission_level: PermissionLevel = PermissionLevel.SAFE,
        parameters: Optional[dict] = None,
    ) -> ToolDefinition:
        """
        Create a ToolDefinition that wraps a V3 worker.

        The handler calls worker.execute_with_correction() which internally
        handles ReAct loops and self-correction if enabled.
        """

        async def handler(ctx: ToolUseContext, args: dict[str, Any]) -> str:
            """Adapted handler that bridges V4 context to V3 worker."""
            try:
                # V3 workers need a db session and execution_id
                db = ctx.db
                execution_id = int(ctx.execution_id) if ctx.execution_id.isdigit() else 0

                # Call the worker's execute method
                task = await worker.execute_with_correction(
                    db=db,
                    execution_id=execution_id,
                    input_data=args,
                )

                return json.dumps({
                    "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
                    "output": task.output_data or {},
                    "tokens_used": task.tokens_used or 0,
                    "error": task.error,
                })
            except Exception as e:
                logger.error(f"Worker adapter error for {tool_name}: {e}")
                return json.dumps({"error": str(e)})

        return ToolDefinition(
            name=tool_name,
            description=description or f"Adapted from V3 {getattr(worker, 'worker_type', 'Worker')}",
            category=category,
            execution_mode=execution_mode,
            permission_level=permission_level,
            parameters=parameters or {"type": "object", "properties": {}},
            handler=handler,
            is_builtin=False,
        )

    @staticmethod
    def adapt_all_workers(
        workers: dict,    # {"RAG": RAGWorker, "Code": CodeWorker, ...}
    ) -> list[ToolDefinition]:
        """
        Adapt all V3 workers to V4 tools.

        Worker type mapping:
        - RAG → rag_search (concurrent)
        - Code → code_worker (serial)
        - Shell → shell_worker (serial)
        - Memory → memory_worker (concurrent)
        - Web → web_worker (concurrent)
        - Vision → vision_worker (serial)
        - Browser → browser_worker (serial)
        - Router → router_worker (concurrent)
        """
        WORKER_CONFIGS = {
            "RAG": ("v3_rag", "Search and synthesize from RAG documents", ToolCategory.MEMORY, ExecutionMode.CONCURRENT),
            "Code": ("v3_code", "Analyze, generate, or review code (V3)", ToolCategory.CODE, ExecutionMode.SERIAL),
            "Shell": ("v3_shell", "File operations and command execution (V3)", ToolCategory.SHELL, ExecutionMode.SERIAL),
            "Memory": ("v3_memory", "Search episodic/profile memories (V3)", ToolCategory.MEMORY, ExecutionMode.CONCURRENT),
            "Web": ("v3_web", "Fetch URLs and scrape web pages (V3)", ToolCategory.WEB, ExecutionMode.CONCURRENT),
            "Vision": ("v3_vision", "Analyze images (V3)", ToolCategory.VISION, ExecutionMode.SERIAL),
            "Browser": ("v3_browser", "Browser automation (V3)", ToolCategory.BROWSER, ExecutionMode.SERIAL),
            "Router": ("v3_router", "Classify and route tasks (V3)", ToolCategory.SYSTEM, ExecutionMode.CONCURRENT),
        }

        tools = []
        for worker_type, worker in workers.items():
            if worker_type in WORKER_CONFIGS:
                name, desc, cat, mode = WORKER_CONFIGS[worker_type]
                tool = WorkerToolAdapter.from_worker(
                    worker, name, desc, cat, mode,
                )
                tools.append(tool)

        return tools
