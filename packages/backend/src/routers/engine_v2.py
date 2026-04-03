"""
V4 Engine API endpoints.
Only active when engine_v2_enabled = True.
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from pydantic import BaseModel

from ..config import get_settings, Settings
from ..dependencies import AuthDep, DbDep
from ..models.database import AsyncSession

logger = logging.getLogger("ahri.engine.router")

router = APIRouter(prefix="/engine/v2", tags=["engine-v2"])


class ExecuteRequest(BaseModel):
    goal: str
    model: str = "fast"
    system_prompt: str = ""
    max_iterations: int = 50


@router.post("/execute")
async def execute_task(
    request: ExecuteRequest,
    auth: AuthDep,
    db: DbDep,
    settings: Settings = Depends(get_settings),
):
    """Start a new engine execution (non-streaming, returns final result)."""
    if not getattr(settings, 'engine_v2_enabled', False):
        raise HTTPException(status_code=404, detail="Engine V2 not enabled")

    # Get engine from app state (initialized in lifespan)
    from ..main import get_engine
    engine = get_engine()

    events = []
    final_response = None
    execution_id = ""
    total_input = 0
    total_output = 0
    iterations = 0
    tool_calls_count = 0
    error_msg = None

    import time
    start_time = time.time()

    async for event in engine.run(
        goal=request.goal,
        system_prompt=request.system_prompt,
        model=request.model,
        max_iterations=request.max_iterations,
    ):
        events.append(event.to_dict())

        if event.type.value == "engine_start":
            execution_id = event.execution_id
        elif event.type.value == "final_response":
            final_response = event.data.get("content", "")
            total_input = event.data.get("total_tokens", 0)
            iterations = event.data.get("iterations", 0)
        elif event.type.value == "llm_response":
            total_input += event.data.get("input_tokens", 0)
            total_output += event.data.get("output_tokens", 0)
            if event.data.get("has_tool_calls"):
                tool_calls_count += event.data.get("tool_count", 0)
        elif event.type.value == "error":
            error_msg = event.data.get("error", "")

    # Persist execution record to DB
    if execution_id:
        from datetime import datetime
        from ..models.database import EngineExecution

        duration_ms = int((time.time() - start_time) * 1000)
        db_record = EngineExecution(
            execution_id=execution_id,
            goal=request.goal,
            model=request.model,
            system_prompt=request.system_prompt,
            status="completed" if final_response else ("failed" if error_msg else "unknown"),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            iterations=iterations,
            tool_calls_count=tool_calls_count,
            final_response=final_response,
            error=error_msg,
            duration_ms=duration_ms,
            completed_at=datetime.utcnow(),
        )
        db.add(db_record)
        await db.commit()

    return {
        "execution_id": execution_id,
        "final_response": final_response,
        "events": events,
        "event_count": len(events),
    }


@router.websocket("/ws")
async def engine_websocket(
    websocket: WebSocket,
    goal: str = "",
    model: str = "fast",
    token: str = "",
    permission: str = "",
    cwd: str = "",
    system_prompt: str = "",
):
    """
    WebSocket endpoint for real-time engine streaming.

    Connect: ws://localhost:8742/engine/v2/ws?goal=...&model=fast&token=<jwt>&permission=...
    Receive: JSON events as they happen
    Send: {"type": "cancel"} to cancel execution
    """
    # Authenticate before accepting connection
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        from ..services.auth_service import verify_token
        verify_token(token)
    except Exception:
        await websocket.close(code=4003, reason="Invalid authentication token")
        return

    await websocket.accept()

    if not goal:
        await websocket.send_json({"type": "error", "data": {"error": "No goal provided"}})
        await websocket.close()
        return

    from ..main import get_engine
    engine = get_engine()

    # Apply permission override to this execution if provided
    original_permission_mode = engine.settings.engine_permission_mode if engine.settings else 'ask'
    if permission in ["supervised", "plan_first", "auto"]:
        if engine.settings:
            # Map frontend names to backend names if needed, or just set it
            mapped_mode = "ask" if permission == "supervised" else ("auto" if permission == "auto" else "ask")
            engine.settings.engine_permission_mode = mapped_mode

    input_queue = asyncio.Queue()
    cancel_event = asyncio.Event()

    # Listen for messages from client
    async def listen_for_messages():
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    msg_type = msg.get("type")
                    if msg_type == "cancel":
                        cancel_event.set()
                    elif msg_type == "permission_response":
                        # Push decision to engine's input queue
                        await input_queue.put(msg.get("data", {}))
                except json.JSONDecodeError:
                    continue
        except WebSocketDisconnect:
            cancel_event.set()
        except Exception as e:
            logger.error(f"Listener loop error: {e}")

    message_task = asyncio.create_task(listen_for_messages())

    # Build context dict
    context = {}
    if cwd: context["cwd"] = cwd

    try:
        async for event in engine.run(
            goal=goal,
            model=model,
            system_prompt=system_prompt,
            context=context,
            input_queue=input_queue
        ):
            if cancel_event.is_set():
                await websocket.send_json({
                    "type": "cancelled",
                    "data": {"reason": "User cancelled"},
                })
                break

            await websocket.send_json(event.to_dict())

    except WebSocketDisconnect:
        logger.info("Engine WebSocket disconnected")
    except Exception as e:
        logger.error(f"Engine WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "data": {"error": str(e)}})
        except Exception:
            pass
    finally:
        message_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/executions")
async def list_executions(
    auth: AuthDep,
    db: DbDep,
    limit: int = 20,
):
    """List recent engine executions."""
    from sqlalchemy import select, desc
    from ..models.database import EngineExecution

    result = await db.execute(
        select(EngineExecution)
        .order_by(desc(EngineExecution.created_at))
        .limit(limit)
    )
    executions = result.scalars().all()
    return [
        {
            "execution_id": e.execution_id,
            "goal": e.goal,
            "model": e.model,
            "status": e.status,
            "iterations": e.iterations,
            "total_tokens": e.total_input_tokens + e.total_output_tokens,
            "duration_ms": e.duration_ms,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in executions
    ]
