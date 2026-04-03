"""
Agent Mode Router - Orchestrated multi-agent task execution endpoints.

Provides REST and WebSocket APIs for submitting tasks, checking status,
and streaming real-time updates from workers.

V2: Background execution (non-blocking), dual rate limiting (TPM+RPM).
"""
import asyncio
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import get_db, AgentExecution, AgentWorkerTask, AgentSession
from ..models.schemas import (
    AgentModeExecuteRequest,
    AgentExecutionSchema,
    AgentSessionSchema,
    AgentWorkerTaskSchema,
    AgentExecutionStatus
)
from ..dependencies import get_llm_service, get_vector_service
from ..services.orchestrator_service import OrchestratorService
from ..services.tpm_manager import TPMManager, AgentKeyRotator
from ..services.event_log import get_log, EventType
from ..config import get_settings

logger = logging.getLogger("ahri.agent_mode")
router = APIRouter(prefix="/agent-mode", tags=["agent-mode"])

# Global TPM+RPM manager (shared across requests, thread-safe)
_settings = get_settings()
tpm_manager = TPMManager(
    limit_tpm=_settings.agent_mode_tpm_limit,
    limit_rpm=_settings.agent_mode_rpm_limit
)

# Global key rotator for round-robin across multiple API keys
key_rotator = AgentKeyRotator(
    keys=_settings.agent_api_keys,
    rpm_per_key=_settings.agent_mode_rpm_limit
)

# Track background tasks to prevent garbage collection
_background_tasks: dict[int, asyncio.Task] = {}
_background_tasks_lock = asyncio.Lock()


def _vision_prepass_sync(images: list[str]) -> str:
    """
    Analyze images with Gemini Flash and return text descriptions.
    Synchronous — meant to run in executor from async context.

    This lets text-only models (flash-lite workers) understand image content.
    Uses vision key rotation for rate limit distribution.
    """
    import base64
    import io
    from PIL import Image
    from src.core.llm_clients import GeminiClient

    settings = get_settings()
    vision_keys = settings.vision_keys
    if not vision_keys:
        return ""

    descriptions = []
    for idx, img_b64 in enumerate(images):
        try:
            # Strip data URL prefix if present (frontend sends "data:image/png;base64,ABC...")
            if img_b64.startswith("data:"):
                img_b64 = img_b64.split(",", 1)[1]

            client = GeminiClient(
                api_key=settings.vision_keys[0] if settings.vision_keys else settings.gemini_primary_key,
                model_name=settings.google_model_vision
            )

            img_bytes = base64.b64decode(img_b64)
            img = Image.open(io.BytesIO(img_bytes))

            response = client.generate_content_sync(contents=[
                "Descreva esta imagem em detalhes para que outro modelo de IA (sem visão) "
                "possa entender completamente o conteúdo. Inclua: objetos, texto visível, "
                "cores, layout, pessoas, e qualquer informação relevante. Seja preciso e conciso.",
                img,
            ])
            descriptions.append(f"[Imagem {idx+1}]: {response.text}")
        except Exception as e:
            logger.error(f"[Vision Pre-pass] Failed to analyze image {idx+1}: {e}")
            descriptions.append(f"[Imagem {idx+1}]: (falha na análise: {e})")

    return "\n".join(descriptions)


async def _run_orchestration(
    execution_id: int,
    goal: str,
    orchestrator_model: str,
    reasoning_level: str = "medium",
    enable_thinking: bool = False,
    internet_search_enabled: bool = False,
    images: list[str] | None = None,
    permission_mode: str = "auto",
    agent_session_id: int | None = None,
):
    """Run orchestration in background. Uses its own DB session."""
    from ..models.database import async_session_factory

    llm_service = get_llm_service()
    vector_service = get_vector_service()
    orchestrator = OrchestratorService(
        llm_service, vector_service, tpm_manager, key_rotator=key_rotator
    )

    # Vision pre-pass: analyze images with Gemini Flash, inject descriptions into goal
    enriched_goal = goal
    if images:
        logger.info(f"[AgentMode] Vision pre-pass for {len(images)} image(s)")
        loop = asyncio.get_running_loop()
        image_context = await loop.run_in_executor(None, _vision_prepass_sync, images)
        if image_context:
            enriched_goal = f"{goal}\n\n[CONTEXTO VISUAL - Análise das imagens enviadas]\n{image_context}"
            logger.info(f"[AgentMode] Vision context injected ({len(image_context)} chars)")

    async with async_session_factory() as db:
        try:
            await orchestrator.execute_task(
                db=db,
                goal=enriched_goal,
                orchestrator_model=orchestrator_model,
                execution_id=execution_id,
                reasoning_level=reasoning_level,
                enable_thinking=enable_thinking,
                internet_search_enabled=internet_search_enabled,
                permission_mode=permission_mode,
                agent_session_id=agent_session_id,
            )
        except Exception as e:
            logger.error(f"[AgentMode] Background execution {execution_id} failed: {e}")
            # Mark as failed in DB
            try:
                await db.rollback()
                from sqlalchemy import select
                stmt = select(AgentExecution).where(AgentExecution.id == execution_id)
                result = await db.execute(stmt)
                execution = result.scalar_one_or_none()
                if execution:
                    execution.status = AgentExecutionStatus.FAILED
                    execution.error = str(e)
                    execution.completed_at = datetime.utcnow()
                    await db.commit()
            except Exception as db_err:
                logger.error(f"[AgentMode] Failed to update execution status in DB: {db_err}")
        finally:
            async with _background_tasks_lock:
                _background_tasks.pop(execution_id, None)


@router.post("/execute", response_model=AgentExecutionSchema)
async def execute_task(
    request: AgentModeExecuteRequest,
    db: AsyncSession = Depends(get_db),
    llm_service = Depends(get_llm_service),
    vector_service = Depends(get_vector_service)
):
    """
    Submit a new agent mode task for execution.

    Returns IMMEDIATELY with execution record (status=planning).
    Orchestration runs in background via asyncio.create_task().
    Poll /agent-mode/{execution_id}/status or use WebSocket for updates.
    """
    try:
        # Step 0: Resolve or auto-create session
        session_id = request.agent_session_id
        if not session_id:
            # Auto-create a new session with goal as title
            session = AgentSession(title=request.goal[:150])
            db.add(session)
            await db.commit()
            await db.refresh(session)
            session_id = session.id

        # Step 1: Create execution record immediately
        execution = AgentExecution(
            goal=request.goal,
            orchestrator_model=request.orchestrator_model,
            status=AgentExecutionStatus.PLANNING,
            agent_session_id=session_id,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

        # Touch session updated_at so it sorts correctly in sidebar
        if request.agent_session_id:
            stmt = select(AgentSession).where(AgentSession.id == session_id)
            result = await db.execute(stmt)
            session_record = result.scalar_one_or_none()
            if session_record:
                from datetime import datetime
                session_record.updated_at = datetime.utcnow()
                await db.commit()

        logger.info(f"[AgentMode] Created execution #{execution.id}, launching background task")

        # Step 2: Launch orchestration in background (non-blocking)
        task = asyncio.create_task(
            _run_orchestration(
                execution.id,
                request.goal,
                request.orchestrator_model,
                reasoning_level=getattr(request, 'reasoning_level', 'medium'),
                enable_thinking=getattr(request, 'enable_thinking', False),
                internet_search_enabled=getattr(request, 'internet_search_enabled', False),
                images=request.images if request.images else None,
                permission_mode=request.permission_mode,
                agent_session_id=session_id,
            )
        )
        async with _background_tasks_lock:
            _background_tasks[execution.id] = task

        # Step 3: Return immediately
        return AgentExecutionSchema(
            id=execution.id,
            agent_session_id=execution.agent_session_id,
            goal=execution.goal,
            orchestrator_model=execution.orchestrator_model,
            status=execution.status,
            plan=execution.plan or {},
            result=execution.result or "",
            error=execution.error or "",
            created_at=execution.created_at,
            completed_at=execution.completed_at,
            worker_tasks=[]
        )

    except Exception as e:
        logger.error(f"[AgentMode] Failed to create execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{execution_id}/approve", response_model=AgentExecutionSchema)
async def approve_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
    llm_service = Depends(get_llm_service),
    vector_service = Depends(get_vector_service),
):
    """
    Approve a paused execution (awaiting_approval) and resume worker execution.
    """
    from sqlalchemy import select as sa_select

    stmt = sa_select(AgentExecution).where(AgentExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Execution is not awaiting approval (status: {execution.status})")

    # Mark as running
    execution.status = AgentExecutionStatus.RUNNING
    await db.commit()

    logger.info(f"[AgentMode] Execution #{execution_id} approved, resuming workers")

    # Launch background task to execute workers + synthesize
    async def _resume_orchestration(exec_id: int, goal: str, plan: dict, orchestrator_model: str):
        from ..models.database import async_session_factory
        llm_svc = get_llm_service()
        vec_svc = get_vector_service()
        orch = OrchestratorService(llm_svc, vec_svc, tpm_manager, key_rotator=key_rotator)

        async with async_session_factory() as resume_db:
            try:
                # Execute workers from the saved plan
                # Check permission_mode for supervised execution
                from sqlalchemy import select as sa_perm
                perm_stmt = sa_perm(AgentExecution).where(AgentExecution.id == exec_id)
                perm_res = await resume_db.execute(perm_stmt)
                perm_exec = perm_res.scalar_one_or_none()
                use_supervised = perm_exec and perm_exec.permission_mode == "supervised"

                if use_supervised:
                    results = await orch._execute_workers_supervised(
                        resume_db, exec_id, plan.get("steps", [])
                    )
                else:
                    results = await orch._execute_workers_with_dependencies(
                        resume_db, exec_id, plan.get("steps", [])
                    )
                # Synthesize
                final_result = await orch._synthesize_results(goal, plan, results, "LITE")

                # Update execution
                from sqlalchemy import select as sa_sel
                from datetime import datetime
                stmt2 = sa_sel(AgentExecution).where(AgentExecution.id == exec_id)
                res2 = await resume_db.execute(stmt2)
                exec_obj = res2.scalar_one_or_none()
                if exec_obj:
                    exec_obj.result = final_result
                    exec_obj.status = AgentExecutionStatus.COMPLETED
                    exec_obj.completed_at = datetime.utcnow()
                    await resume_db.commit()
                    logger.info(f"[AgentMode] Resumed execution #{exec_id} completed")
            except Exception as e:
                logger.error(f"[AgentMode] Resumed execution #{exec_id} failed: {e}")
                try:
                    await resume_db.rollback()
                    from sqlalchemy import select as sa_sel2
                    stmt3 = sa_sel2(AgentExecution).where(AgentExecution.id == exec_id)
                    res3 = await resume_db.execute(stmt3)
                    exec_obj = res3.scalar_one_or_none()
                    if exec_obj:
                        exec_obj.status = AgentExecutionStatus.FAILED
                        exec_obj.error = str(e)
                        exec_obj.completed_at = datetime.utcnow()
                        await resume_db.commit()
                except Exception as db_err:
                    logger.error(f"[AgentMode] Failed to update resumed execution status: {db_err}")
            finally:
                async with _background_tasks_lock:
                    _background_tasks.pop(exec_id, None)

    task = asyncio.create_task(
        _resume_orchestration(execution.id, execution.goal, execution.plan or {}, execution.orchestrator_model)
    )
    async with _background_tasks_lock:
        _background_tasks[execution.id] = task

    return AgentExecutionSchema(
        id=execution.id,
        goal=execution.goal,
        orchestrator_model=execution.orchestrator_model,
        status=execution.status,
        plan=execution.plan or {},
        result=execution.result or "",
        error=execution.error or "",
        created_at=execution.created_at,
        completed_at=execution.completed_at,
        worker_tasks=[],
    )


@router.post("/{execution_id}/reject", response_model=AgentExecutionSchema)
async def reject_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a paused execution (awaiting_approval), marking it as failed.
    """
    from sqlalchemy import select as sa_select
    from datetime import datetime

    stmt = sa_select(AgentExecution).where(AgentExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Execution is not awaiting approval (status: {execution.status})")

    execution.status = AgentExecutionStatus.FAILED
    execution.error = "Plano rejeitado pelo usuário"
    execution.completed_at = datetime.utcnow()
    await db.commit()

    logger.info(f"[AgentMode] Execution #{execution_id} rejected by user")

    return AgentExecutionSchema(
        id=execution.id,
        goal=execution.goal,
        orchestrator_model=execution.orchestrator_model,
        status=execution.status,
        plan=execution.plan or {},
        result=execution.result or "",
        error=execution.error or "",
        created_at=execution.created_at,
        completed_at=execution.completed_at,
        worker_tasks=[],
    )


@router.post("/{execution_id}/cancel", response_model=AgentExecutionSchema)
async def cancel_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel a running or planning execution.
    """
    from datetime import datetime
    from sqlalchemy import select as sa_select

    # 1. Cancel the asyncio task if it exists
    async with _background_tasks_lock:
        task = _background_tasks.pop(execution_id, None)
    if task:
        task.cancel()
        logger.info(f"[AgentMode] Cancelled background task for execution #{execution_id}")

    # 2. Update DB status
    stmt = sa_select(AgentExecution).where(AgentExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status not in [AgentExecutionStatus.COMPLETED, AgentExecutionStatus.FAILED]:
        execution.status = AgentExecutionStatus.FAILED
        execution.error = "Cancelado pelo usuário"
        execution.completed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(execution)
        logger.info(f"[AgentMode] Execution #{execution_id} marked as FAILED (Cancelled)")

    # 3. Load worker tasks for the response
    worker_stmt = sa_select(AgentWorkerTask).where(AgentWorkerTask.execution_id == execution_id)
    worker_result = await db.execute(worker_stmt)
    worker_tasks = worker_result.scalars().all()

    return AgentExecutionSchema(
        id=execution.id,
        goal=execution.goal,
        orchestrator_model=execution.orchestrator_model,
        status=execution.status,
        plan=execution.plan or {},
        result=execution.result or "",
        error=execution.error or "",
        created_at=execution.created_at,
        completed_at=execution.completed_at,
        worker_tasks=[
            AgentWorkerTaskSchema(
                id=t.id,
                execution_id=t.execution_id,
                worker_type=t.worker_type,
                model=t.model,
                input_data=t.input_data,
                output_data=t.output_data,
                tokens_used=t.tokens_used,
                duration_ms=t.duration_ms,
                status=t.status,
                error=t.error,
                created_at=t.created_at,
                completed_at=t.completed_at
            ) for t in worker_tasks
        ],
    )


@router.post("/worker/{task_id}/approve", response_model=AgentWorkerTaskSchema)
async def approve_worker_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a single worker task in supervised mode.
    Changes status from awaiting_approval to approved.
    """
    from sqlalchemy import select as sa_select

    stmt = sa_select(AgentWorkerTask).where(AgentWorkerTask.id == task_id)
    result = await db.execute(stmt)
    worker_task = result.scalar_one_or_none()

    if not worker_task:
        raise HTTPException(status_code=404, detail="Worker task not found")
    if worker_task.status != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Task is not awaiting approval (status: {worker_task.status})")

    worker_task.status = "approved"
    await db.commit()
    await db.refresh(worker_task)

    logger.info(f"[AgentMode] Worker task #{task_id} approved by user")

    return AgentWorkerTaskSchema(
        id=worker_task.id,
        execution_id=worker_task.execution_id,
        worker_type=worker_task.worker_type,
        model=worker_task.model,
        input_data=worker_task.input_data or {},
        output_data=worker_task.output_data or {},
        tokens_used=worker_task.tokens_used or 0,
        duration_ms=worker_task.duration_ms or 0,
        status=worker_task.status,
        error=worker_task.error or "",
        created_at=worker_task.created_at,
        completed_at=worker_task.completed_at,
    )


@router.post("/worker/{task_id}/skip", response_model=AgentWorkerTaskSchema)
async def skip_worker_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Skip a single worker task in supervised mode.
    Changes status to failed with 'skipped' error.
    """
    from sqlalchemy import select as sa_select
    from datetime import datetime

    stmt = sa_select(AgentWorkerTask).where(AgentWorkerTask.id == task_id)
    result = await db.execute(stmt)
    worker_task = result.scalar_one_or_none()

    if not worker_task:
        raise HTTPException(status_code=404, detail="Worker task not found")
    if worker_task.status != "awaiting_approval":
        raise HTTPException(status_code=400, detail=f"Task is not awaiting approval (status: {worker_task.status})")

    worker_task.status = "failed"
    worker_task.error = "Ignorado pelo usu\u00e1rio"
    worker_task.completed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(worker_task)

    logger.info(f"[AgentMode] Worker task #{task_id} skipped by user")

    return AgentWorkerTaskSchema(
        id=worker_task.id,
        execution_id=worker_task.execution_id,
        worker_type=worker_task.worker_type,
        model=worker_task.model,
        input_data=worker_task.input_data or {},
        output_data=worker_task.output_data or {},
        tokens_used=worker_task.tokens_used or 0,
        duration_ms=worker_task.duration_ms or 0,
        status=worker_task.status,
        error=worker_task.error or "",
        created_at=worker_task.created_at,
        completed_at=worker_task.completed_at,
    )


@router.get("/{execution_id}/status", response_model=AgentExecutionSchema)
async def get_execution_status(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get current status of an execution, including worker tasks.

    Use this endpoint to poll for completion or retrieve final results.
    """
    from sqlalchemy import select as sa_select

    stmt = sa_select(AgentExecution).where(AgentExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Load worker tasks
    worker_stmt = sa_select(AgentWorkerTask).where(
        AgentWorkerTask.execution_id == execution_id
    ).order_by(AgentWorkerTask.created_at)
    worker_result = await db.execute(worker_stmt)
    worker_tasks = worker_result.scalars().all()

    # Convert worker tasks to schemas
    worker_schemas = [
        AgentWorkerTaskSchema(
            id=task.id,
            execution_id=task.execution_id,
            worker_type=task.worker_type,
            model=task.model,
            input_data=task.input_data or {},
            output_data=task.output_data or {},
            tokens_used=task.tokens_used or 0,
            duration_ms=task.duration_ms or 0,
            status=task.status,
            error=task.error or "",
            created_at=task.created_at,
            completed_at=task.completed_at
        )
        for task in worker_tasks
    ]

    return AgentExecutionSchema(
        id=execution.id,
        goal=execution.goal,
        orchestrator_model=execution.orchestrator_model,
        status=execution.status,
        plan=execution.plan or {},
        result=execution.result or "",
        error=execution.error or "",
        created_at=execution.created_at,
        completed_at=execution.completed_at,
        worker_tasks=worker_schemas
    )


@router.get("/{execution_id}/workers", response_model=List[AgentWorkerTaskSchema])
async def get_worker_tasks(
    execution_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all worker tasks for an execution.

    Useful for displaying worker progress in UI.
    """
    from sqlalchemy import select as sa_select

    worker_stmt = sa_select(AgentWorkerTask).where(
        AgentWorkerTask.execution_id == execution_id
    ).order_by(AgentWorkerTask.created_at)
    worker_result = await db.execute(worker_stmt)
    worker_tasks = worker_result.scalars().all()

    return [
        AgentWorkerTaskSchema(
            id=task.id,
            execution_id=task.execution_id,
            worker_type=task.worker_type,
            model=task.model,
            input_data=task.input_data or {},
            output_data=task.output_data or {},
            tokens_used=task.tokens_used or 0,
            duration_ms=task.duration_ms or 0,
            status=task.status,
            error=task.error or "",
            created_at=task.created_at,
            completed_at=task.completed_at
        )
        for task in worker_tasks
    ]


@router.websocket("/ws/{execution_id}")
async def websocket_execution_stream(
    websocket: WebSocket,
    execution_id: int
):
    """
    WebSocket endpoint for real-time execution updates.

    Hybrid approach:
    - EventLog subscription for instant event streaming (0ms latency)
    - DB polling every 2s for execution status + TPM status (fallback)

    Message format:
    {
        "type": "agent_event" | "status_update" | "execution_completed" | "tpm_status",
        "data": {...}
    }
    """
    from ..dependencies import get_llm_service, get_vector_service
    import asyncio
    from ..models.database import get_db
    from sqlalchemy import select

    await websocket.accept()
    llm_service = get_llm_service()
    vector_service = get_vector_service()
    orchestrator = OrchestratorService(llm_service, vector_service, tpm_manager)

    # Timeout configuration
    MAX_POLL_DURATION = 600  # 10 minutes maximum
    start_time = asyncio.get_event_loop().time()

    # Queue for events pushed from EventLog subscriber
    event_queue: asyncio.Queue = asyncio.Queue()

    def _on_event(event):
        """Callback from EventLog — push event to async queue."""
        try:
            event_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop events if queue is full

    # Subscribe to EventLog (if it exists yet — execution may still be starting)
    event_log = get_log(execution_id)
    if event_log:
        event_log.subscribe(_on_event)

    try:
        await websocket.send_json({
            "type": "connected",
            "execution_id": execution_id,
            "timestamp": start_time
        })

        last_execution_status = None

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > MAX_POLL_DURATION:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Execution timeout after {MAX_POLL_DURATION}s"
                })
                return

            # ── Phase A: Drain all queued events from EventLog ──
            # Re-subscribe if log appeared after we connected
            if not event_log:
                event_log = get_log(execution_id)
                if event_log:
                    event_log.subscribe(_on_event)

            while not event_queue.empty():
                try:
                    event = event_queue.get_nowait()
                    await websocket.send_json({
                        "type": "agent_event",
                        "data": event.to_dict()
                    })
                except asyncio.QueueEmpty:
                    break

            # ── Phase B: DB poll for execution status + TPM (every cycle) ──
            async for db_session in get_db():
                try:
                    execution = await orchestrator.get_execution_status(db_session, execution_id)

                    if not execution:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Execution not found"
                        })
                        return

                    # Status update if changed
                    if execution.status != last_execution_status:
                        await websocket.send_json({
                            "type": "status_update",
                            "data": {
                                "execution_id": execution.id,
                                "status": execution.status,
                                "plan": execution.plan,
                                "reasoning": execution.plan.get("reasoning") if execution.plan else None
                            }
                        })
                        last_execution_status = execution.status

                    # TPM status
                    tpm_status = tpm_manager.get_status()
                    await websocket.send_json({
                        "type": "tpm_status",
                        "data": {
                            "tokens_used_window": tpm_status["tokens_used_window"],
                            "tokens_remaining": tpm_status["tokens_remaining"],
                            "limit_tpm": tpm_status["limit_tpm"],
                            "utilization_percent": tpm_status["utilization_percent"],
                            "requests_used": tpm_status["requests_used"],
                            "requests_remaining": tpm_status["requests_remaining"],
                            "limit_rpm": tpm_status["limit_rpm"],
                            "rpm_utilization_percent": tpm_status["rpm_utilization_percent"],
                        }
                    })

                    # Terminal state — send final message and close
                    if execution.status in [AgentExecutionStatus.COMPLETED, AgentExecutionStatus.FAILED]:
                        await websocket.send_json({
                            "type": "execution_completed",
                            "data": {
                                "execution_id": execution.id,
                                "status": execution.status,
                                "result": execution.result,
                                "error": execution.error,
                                "completed_at": str(execution.completed_at),
                                "worker_count": len(execution.worker_tasks or [])
                            }
                        })
                        logger.info(f"[AgentMode WS] Execution {execution_id} {execution.status}, closing WebSocket")
                        return

                    break
                except Exception as e:
                    logger.error(f"[AgentMode WS] Poll error: {e}")
                    break

            # Wait 1s between polls (events arrive instantly via queue regardless)
            await asyncio.sleep(1.0)

    except WebSocketDisconnect:
        logger.info(f"[AgentMode] WebSocket disconnected for execution {execution_id}")
    except Exception as e:
        logger.error(f"[AgentMode WS] Error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        # Unsubscribe from EventLog
        if event_log:
            event_log.unsubscribe(_on_event)


# =============================================================================
# Session CRUD Endpoints
# =============================================================================

@router.get("/sessions/list", response_model=list[AgentSessionSchema])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
):
    """List all agent sessions, newest first."""
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    stmt = (
        sa_select(AgentSession)
        .options(selectinload(AgentSession.executions))
        .order_by(AgentSession.updated_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return [
        AgentSessionSchema(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            executions=[
                AgentExecutionSchema(
                    id=e.id,
                    agent_session_id=e.agent_session_id,
                    goal=e.goal,
                    orchestrator_model=e.orchestrator_model,
                    status=e.status,
                    plan=e.plan or {},
                    result=e.result or "",
                    error=e.error or "",
                    created_at=e.created_at,
                    completed_at=e.completed_at,
                    worker_tasks=[],
                )
                for e in sorted(s.executions, key=lambda x: x.created_at or datetime.min)
            ],
        )
        for s in sessions
    ]


@router.post("/sessions/create", response_model=AgentSessionSchema)
async def create_session(
    db: AsyncSession = Depends(get_db),
):
    """Create a new empty agent session."""
    session = AgentSession(title="")
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return AgentSessionSchema(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        executions=[],
    )


@router.get("/sessions/{session_id}", response_model=AgentSessionSchema)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a session with its executions."""
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    stmt = (
        sa_select(AgentSession)
        .where(AgentSession.id == session_id)
        .options(selectinload(AgentSession.executions))
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return AgentSessionSchema(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        executions=[
            AgentExecutionSchema(
                id=e.id,
                agent_session_id=e.agent_session_id,
                goal=e.goal,
                orchestrator_model=e.orchestrator_model,
                status=e.status,
                plan=e.plan or {},
                result=e.result or "",
                error=e.error or "",
                created_at=e.created_at,
                completed_at=e.completed_at,
                worker_tasks=[],
            )
            for e in sorted(session.executions, key=lambda x: x.created_at or datetime.min)
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a session and all its executions."""
    from sqlalchemy import select as sa_select

    stmt = sa_select(AgentSession).where(AgentSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session)
    await db.commit()

    return {"deleted": True, "session_id": session_id}
