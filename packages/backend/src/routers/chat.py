"""
Chat: envio de mensagens e streaming via WebSocket.
"""
import asyncio
import base64
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from jose import JWTError, jwt
from src.core.llm_clients import GeminiClient

from src.config import get_settings
from src.dependencies import AuthDep, DbDep, SettingsDep
from src.models.schemas import ChatRequest, ChatResponse, ChatMessageSchema, FileAttachment
from src.services.llm_service import get_llm_service
from src.services.memory_service import MemoryService
from src.services.session_service import SessionService
from src.services.persona_service import get_active_persona
from src.services.spotify_service import get_spotify_service
from src.core.prompt_builder import build_system_prompt
from src.core.save_tag_parser import extract_save_tags, clean_all_tags
from src.core.memory_analyzer import analyze_incremental, analyze_incremental_v2, TIER_MAP
from src.services.semantic_memory_service import SemanticMemoryService
from src.services.vector_service import get_vector_service

from src.services.compaction_service import CompactionService
from src.services.search_service import SearchService

logger = logging.getLogger("ahri.router.chat")

router = APIRouter()


def _upload_file_to_gemini(file_data_b64: str, mime_type: str, filename: str = "temp_file", api_key: str = ""):
    """Upload file to Gemini File API via google-genai SDK (usado para video e PDF)."""
    try:
        logger.info(f"Uploading file: {filename} ({mime_type})")
        suffix = "." + mime_type.split("/")[-1]

        # Salva temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(base64.b64decode(file_data_b64))
            tmp_path = tmp.name

        # Upload via novo SDK (per-instance client, thread-safe)
        client = GeminiClient(api_key=api_key, model_name="")
        uploaded_file = client.upload_file(tmp_path, mime_type)
        os.remove(tmp_path)

        # Aguarda processamento
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(1)
            uploaded_file = client.get_file(uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            logger.error(f"File upload failed: {uploaded_file.name}")
            return None

        logger.info(f"File uploaded successfully: {uploaded_file.name}")
        return uploaded_file

    except Exception as e:
        logger.error(f"FILE API ERROR: {e}")
        return None


async def _build_context(
    db: DbDep, 
    persona_name: str, 
    model: str, 
    compacted_context: str = "", 
    mode: str = "default", 
    last_user_msg: str = ""
) -> tuple[str, list[dict], str]:
    """Constrói system prompt e carrega contexto (incluindo busca)."""
    mem_svc = MemoryService(db)
    settings = get_settings()

    # 1. Carrega dados básicos
    profile = await mem_svc.get_profile()
    social_graph = await mem_svc.get_social_graph()
    persona_memory = await mem_svc.get_persona_memory(persona_name)

    # 2. Spotify context (síncrono)
    spotify_text = ""
    try:
        spotify_svc = get_spotify_service()
        spotify_text = spotify_svc.get_listening_context_text()
    except Exception:
        pass

    # 3. Pesquisa Dinâmica (Web ou Lore)
    search_context = ""
    if mode == "web_search" and last_user_msg and settings.internet_search_enabled:
        try:
            search_svc = SearchService(db)
            results = await search_svc.search(last_user_msg)
            if results.get("results"):
                search_context = "--- RESULTADOS DA WEB ---\n"
                for r in results["results"]:
                    search_context += f"- {r['title']}: {r['snippet']} ({r['link']})\n"
                logger.info(f"Web search results injected for: {last_user_msg[:30]}")
        except Exception as e:
            logger.error(f"Web search injection error: {e}")

    elif mode == "lore_search" and last_user_msg:
        try:
            vector_svc = get_vector_service(persona_name)
            results = vector_svc.search(last_user_msg, limit=3)
            if results:
                search_context = f"--- LORE DO MUNDO / MEMORIA ({persona_name}) ---\n"
                for r in results:
                    search_context += f"- {r['content']}\n"
                logger.info(f"Lore search results injected for: {last_user_msg[:30]}")
        except Exception as e:
            logger.error(f"Lore search injection error: {e}")

    # 4. Load dual-layer memory (v3.2.0)
    semantic_svc = SemanticMemoryService(db)
    user_preferences = None
    semantic_tiers = None
    try:
        user_preferences = await semantic_svc.get_preferences()
        semantic_tiers = await semantic_svc.get_tiers()
    except Exception as e:
        logger.warning(f"Could not load semantic memory, falling back to legacy: {e}")

    # 5. Monta Prompt
    is_local = model == "LOCAL"
    system_prompt = build_system_prompt(
        user_profile=profile,
        persona_name=persona_name,
        is_local_mode=is_local,
        spotify_context=spotify_text,
        social_graph=social_graph,
        model_name=model,
        enable_agent=True,
        compacted_context=compacted_context,
        search_context=search_context,
        persona_memory=persona_memory,
        user_preferences=user_preferences,
        semantic_tiers=semantic_tiers,
    )

    return system_prompt, profile, search_context


def _process_save_tags(full_response: str, persona_name: str) -> list[str]:
    """Processa [[SAVE:]] tags e salva no RAG."""
    notifications = []
    tags = extract_save_tags(full_response)

    if tags:
        try:
            vector_svc = get_vector_service(persona_name)
            for tag in tags:
                vector_svc.add_dynamic_memory(tag.title, tag.content)
                notifications.append(f"Memória salva: {tag.title}")
                logger.info(f"Memory saved: {tag.title}")
        except Exception as e:
            logger.error(f"Save tag processing error: {e}")

    return notifications



def _run_memory_analysis_bg(user_msg: str, ai_msg: str, profile: dict, session_id: Optional[int] = None):
    """
    Executa análise incremental de memória em background thread.
    v3.2.0: Uses analyze_incremental_v2 to persist facts to SemanticMemoryTier.
    Falls back to legacy analyze_incremental if v2 returns nothing.
    """
    try:
        from src.models.database import async_session_factory
        import asyncio

        results = analyze_incremental_v2(user_msg, ai_msg)
        if results:
            async def _persist():
                async with async_session_factory() as db:
                    svc = SemanticMemoryService(db)
                    for item in results:
                        action = item.get("action")
                        tier = TIER_MAP.get(action)
                        if tier:
                            await svc.add_or_reinforce_fact(
                                tier=tier,
                                content=item["content"],
                                source_session_id=session_id,
                                importance=item.get("importance", 5),
                                tags=item.get("tags", []),
                            )
                    # Fire-and-forget decay pass
                    await svc.run_decay_pass()

            asyncio.run(_persist())
            logger.info(f"Semantic memory updated: {len(results)} facts from interaction")
        else:
            # Fallback: legacy incremental analysis (read-only logging)
            result = analyze_incremental(user_msg, ai_msg, profile)
            if result and result.get("action") != "IGNORE":
                logger.info(f"Legacy memory update detected: {result.get('action')}")
    except Exception as e:
        logger.error(f"Background memory analysis error: {e}")


@router.post("", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    auth: AuthDep,
    db: DbDep,
    settings: SettingsDep,
):
    """Envia uma mensagem e recebe resposta (não-streaming)."""
    persona_name = get_active_persona()
    session_svc = SessionService(db)

    # 1. Configura o modelo LLM
    llm_svc = get_llm_service()
    llm_svc.set_mode(request.model)

    # 2. Busca/cria sessão ativa
    if request.session_id:
        session_id = request.session_id
        session_data = await session_svc.get_session(session_id)
        if not session_data:
             logger.warning(f"Session {session_id} not found, creating a new one")
             new_session = await session_svc.create_session(persona_name=persona_name)
             session_id = new_session["id"]
             history = []
        else:
            history = session_data["messages"]
    else:
        # Padrão Claude/ChatGPT: se não enviado ID, cria nova sessão
        new_session = await session_svc.create_session(persona_name=persona_name)
        session_id = new_session["id"]
        history = []

    # 3. Context compaction
    compacted_context = ""
    compaction_svc = CompactionService()
    if compaction_svc.should_compact(history):
        existing_summary = await session_svc.get_session_summary(session_id)
        loop = asyncio.get_running_loop()
        summary, history = await loop.run_in_executor(
            None, compaction_svc.compact_history, history, existing_summary
        )
        if summary != existing_summary:
            await session_svc.update_session_summary(
                session_id, summary, len(history)
            )
            # Auto-populate PersonaMemory with compacted context
            try:
                pm_svc = MemoryService(db)
                pm_data = await pm_svc.get_persona_memory(persona_name)
                # Append summary to session_log
                session_log = list(pm_data.get("session_log", []))
                session_log.append(summary[:500])
                # Update buffer with recent message snippets
                buffer = [msg.get("content", "")[:200] for msg in history[-3:]]
                await pm_svc.save_persona_memory(persona_name, {
                    "session_log": session_log,
                    "last_session_buffer": buffer,
                })
            except Exception as e:
                logger.warning(f"Failed to auto-populate persona memory: {e}")
        compacted_context = summary
    else:
        compacted_context = await session_svc.get_session_summary(session_id)

    # 4. Constrói system prompt com contexto completo (incluindo busca)
    system_prompt, profile, search_ctx = await _build_context(
        db=db, 
        persona_name=persona_name, 
        model=request.model, 
        compacted_context=compacted_context,
        mode=request.mode,
        last_user_msg=request.message
    )

    # 5. Salva mensagem do usuário
    await session_svc.add_message(
        session_id=session_id,
        role="user",
        content=request.message,
        images=request.images,
    )

    # 5. Upload de arquivos para Gemini File API (video, PDFs)
    uploaded_files = []
    api_key = settings.gemini_fallback_key or settings.gemini_primary_key

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit for base64 uploads

    if request.video:
        if len(request.video.data) > MAX_FILE_SIZE * 1.37: # Approx base64 size
             logger.error("Video file too large")
             # Continue without video or raise? Let's skip to avoid crash
        else:
            vid_file = _upload_file_to_gemini(
                request.video.data, "video/mp4", request.video.name, api_key
            )
            if vid_file:
                uploaded_files.append(vid_file)

    if request.pdfs:
        for pdf in request.pdfs:
            if len(pdf.data) > MAX_FILE_SIZE * 1.37:
                 logger.error(f"PDF too large: {pdf.name}")
                 continue
            pdf_file = _upload_file_to_gemini(
                pdf.data, "application/pdf", pdf.name, api_key
            )
            if pdf_file:
                uploaded_files.append(pdf_file)

    # 6. Gera resposta (coleta streaming em string completa)
    full_response = ""
    try:
        for chunk in llm_svc.generate_response(
            message=request.message,
            system_prompt=system_prompt,
            history=history,
            images=request.images if request.images else None,
            uploaded_files=uploaded_files if uploaded_files else None,
            reasoning_level=request.reasoning_level,
            enable_thinking=request.enable_thinking,
        ):
            full_response += chunk
    except Exception as e:
        logger.error(f"LLM generation error: {e}")
        full_response = f"[Error] Falha na geração: {e}"

    # 7. Processa tags (offloaded to avoid blocking)
    loop = asyncio.get_running_loop()
    if request.auto_save_tags:
        notifications = await loop.run_in_executor(None, _process_save_tags, full_response, persona_name)
    else:
        notifications = []

    # 8. Limpa tags do texto de display
    clean_response = clean_all_tags(full_response)

    # 9. Salva resposta da IA na sessão
    await session_svc.add_message(
        session_id=session_id,
        role="assistant",
        content=clean_response,
        meta={"model": request.model},
    )

    # 10. Trigger memory analyzer em background
    threading.Thread(
        target=_run_memory_analysis_bg,
        args=(request.message, clean_response, profile, session_id),
        daemon=True,
    ).start()

    return ChatResponse(
        message=ChatMessageSchema(
            role="assistant",
            content=clean_response,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            meta={"model": request.model},
        ),
        memory_notifications=notifications,
        search_context=search_ctx if search_ctx else None
    )


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket, settings: SettingsDep):
    """WebSocket para chat em tempo real com streaming."""
    await websocket.accept()
    authenticated = False

    # Track active stop events per websocket
    active_stop_events: dict[WebSocket, threading.Event] = {}

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "cancel":
                event = active_stop_events.get(websocket)
                if event:
                    event.set()
                    logger.info("Chat stream cancellation requested via WebSocket")
                    await websocket.send_json({"type": "status", "content": "Cancellation requested"})
                continue

            # Autenticação no primeiro message
            if msg_type == "auth":
                token = data.get("token", "")
                try:
                    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
                    if payload.get("type") == "access":
                        authenticated = True
                        await websocket.send_json({"type": "auth", "status": "ok"})
                    else:
                        await websocket.send_json({"type": "auth", "status": "error", "detail": "Invalid token type"})
                except JWTError:
                    await websocket.send_json({"type": "auth", "status": "error", "detail": "Invalid token"})
                continue

            if not authenticated:
                await websocket.send_json({"type": "error", "detail": "Not authenticated. Send auth message first."})
                continue

            if msg_type == "message":
                message = data.get("message", "")
                model = data.get("model", "LITE")
                images = data.get("images", [])
                video = data.get("video")
                pdfs = data.get("pdfs", [])
                mode = data.get("mode", "default")
                reasoning_level = data.get("reasoning_level")
                enable_thinking = data.get("enable_thinking", False)
                auto_save_tags = data.get("auto_save_tags", True)

                if not message:
                    await websocket.send_json({"type": "error", "detail": "Empty message"})
                    continue

                persona_name = get_active_persona()
                llm_svc = get_llm_service()
                llm_svc.set_mode(model)

                # Obtem db session via import direto
                from src.models.database import get_db
                async for db in get_db():
                    # 2. Busca/cria sessão
                    session_id = data.get("session_id")
                    if session_id:
                        session_data = await session_svc.get_session(session_id)
                        if not session_data:
                            new_session = await session_svc.create_session(persona_name=persona_name)
                            session_id = new_session["id"]
                            history = []
                        else:
                            history = session_data["messages"]
                    else:
                        new_session = await session_svc.create_session(persona_name=persona_name)
                        session_id = new_session["id"]
                        history = []

                    # Compaction
                    compacted_context = ""
                    compaction_svc = CompactionService()
                    if compaction_svc.should_compact(history):
                        existing_summary = await session_svc.get_session_summary(session_id)
                        ws_loop = asyncio.get_running_loop()
                        summary, history = await ws_loop.run_in_executor(
                            None, compaction_svc.compact_history, history, existing_summary
                        )
                        if summary != existing_summary:
                            await session_svc.update_session_summary(
                                session_id, summary, len(history)
                            )
                            # Auto-populate PersonaMemory with compacted context
                            try:
                                pm_svc = MemoryService(db)
                                pm_data = await pm_svc.get_persona_memory(persona_name)
                                session_log = list(pm_data.get("session_log", []))
                                session_log.append(summary[:500])
                                buffer = [msg.get("content", "")[:200] for msg in history[-3:]]
                                await pm_svc.save_persona_memory(persona_name, {
                                    "session_log": session_log,
                                    "last_session_buffer": buffer,
                                })
                            except Exception as e:
                                logger.warning(f"Failed to auto-populate persona memory: {e}")
                        compacted_context = summary
                    else:
                        compacted_context = await session_svc.get_session_summary(session_id)

                    # 3. Build context (includes search injection)
                    system_prompt, profile, search_ctx = await _build_context(
                        db=db, 
                        persona_name=persona_name, 
                        model=model, 
                        compacted_context=compacted_context,
                        mode=mode,
                        last_user_msg=message
                    )

                    # Salva mensagem do usuário
                    await session_svc.add_message(
                        session_id=session_id,
                        role="user",
                        content=message,
                        images=images,
                    )

                    # Upload arquivos para Gemini File API
                    uploaded_files = []
                    api_key = settings.gemini_fallback_key or settings.gemini_primary_key

                    if video:
                        vid_file = _upload_file_to_gemini(
                            video["data"], "video/mp4", video.get("name", "video.mp4"), api_key
                        )
                        if vid_file:
                            uploaded_files.append(vid_file)

                    if pdfs:
                        for pdf in pdfs:
                            pdf_file = _upload_file_to_gemini(
                                pdf["data"], "application/pdf", pdf.get("name", "document.pdf"), api_key
                            )
                            if pdf_file:
                                uploaded_files.append(pdf_file)

                    # Stream resposta
                    full_response = ""
                    stop_event = threading.Event()
                    active_stop_events[websocket] = stop_event

                    # LLM streaming é síncrono - roda em thread
                    loop = asyncio.get_event_loop()

                    def _stream_sync():
                        nonlocal full_response
                        try:
                            for chunk in llm_svc.generate_response(
                                message=message,
                                system_prompt=system_prompt,
                                history=history,
                                images=images if images else None,
                                uploaded_files=uploaded_files if uploaded_files else None,
                                reasoning_level=reasoning_level,
                                enable_thinking=enable_thinking,
                                stop_event=stop_event,
                            ):
                                full_response += chunk
                                # Usa thread-safe callback
                                asyncio.run_coroutine_threadsafe(
                                    websocket.send_json({"type": "chunk", "content": chunk, "done": False}),
                                    loop,
                                )
                        except Exception as e:
                            logger.error(f"Error in _stream_sync: {e}")
                            asyncio.run_coroutine_threadsafe(
                                websocket.send_json({"type": "error", "detail": str(e)}),
                                loop,
                            )

                    await loop.run_in_executor(None, _stream_sync)
                    active_stop_events.pop(websocket, None)

                    # Processa tags (offloaded)
                    if auto_save_tags:
                        notifications = await loop.run_in_executor(None, _process_save_tags, full_response, persona_name)
                    else:
                        notifications = []
                    clean_response = clean_all_tags(full_response)

                    # Salva resposta
                    await session_svc.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=clean_response,
                        meta={"model": model},
                    )

                    # Envia done
                    await websocket.send_json({
                        "type": "done",
                        "content": clean_response,
                        "memory_notifications": notifications,
                        "search_context": search_ctx if search_ctx else None
                    })

                    # Background memory analysis
                    threading.Thread(
                        target=_run_memory_analysis_bg,
                        args=(message, clean_response, profile, session_id),
                        daemon=True,
                    ).start()

                    break  # Só precisamos de uma sessão db

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        active_stop_events.pop(websocket, None)
