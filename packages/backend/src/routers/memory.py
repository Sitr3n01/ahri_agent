"""
Memory: perfil do usuário, aprender, esquecer, CRUD de memórias RAG,
auto-profile, social graph, memória episódica.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

from src.dependencies import AuthDep, DbDep
from src.models.schemas import (
    UserProfileSchema, MemorySaveRequest, MemoryLearnRequest,
    MemoryForgetRequest, MemoryUpdateRequest, MemoryItem,
    AutoProfileResponse, AutoProfilePatchRequest,
    RagFileInfo, RagStatsResponse, RagSearchRequest,
    SocialGraphPlatformResponse, SocialGraphImportRequest,
    EpisodeResponse, EpisodeBulkDeleteRequest, ForgetResponse,
    PersonaMemoryResponse, PersonaMemoryPatchRequest,
    # Dual-layer memory (v3.2.0)
    UserPreferencesSchema, UpdatePreferencesRequest,
    SemanticMemoryItemSchema, SemanticTiersResponse,
    AddSemanticFactRequest, DecayPassResponse, MigrateLegacyResponse,
)
from src.services.semantic_memory_service import SemanticMemoryService
from src.services.memory_service import MemoryService
from src.services.persona_service import get_active_persona
from src.services.vector_service import get_vector_service
from src.services.llm_service import LLMService

from src.services.workers.narrative_memory_worker import NarrativeMemoryWorker

logger = logging.getLogger("ahri.router.memory")

router = APIRouter()


# =============================================================================
# User Profile (existing)
# =============================================================================

@router.get("/profile", response_model=UserProfileSchema)
async def get_profile(auth: AuthDep, db: DbDep):
    """Retorna o perfil do usuário."""
    svc = MemoryService(db)
    profile = await svc.get_profile()

    return UserProfileSchema(
        name=profile.get("name", ""),
        occupation=profile.get("occupation", ""),
        custom_instructions=profile.get("custom_instructions", ""),
        work_context=profile.get("work_context", ""),
        personal_context=profile.get("personal_context", ""),
        top_of_mind=profile.get("top_of_mind", ""),
        brief_history=profile.get("brief_history", ""),
        # Legacy
        archetype=profile.get("archetype", ""),
        learning_style=profile.get("learning_style", ""),
        attributes=profile.get("attributes", {}),
        preferences=profile.get("preferences", {}),
        knowledge_tracker=profile.get("knowledge_tracker", {}),
        active_quests=profile.get("active_quests", {}),
        session_log=profile.get("session_log", []),
    )


@router.post("/profile")
async def save_profile_endpoint(profile: UserProfileSchema, auth: AuthDep, db: DbDep):
    """Salva/atualiza o perfil do usuário."""
    svc = MemoryService(db)

    data = {
        "name": profile.name,
        "occupation": profile.occupation,
        "custom_instructions": profile.custom_instructions,
        "work_context": profile.work_context,
        "personal_context": profile.personal_context,
        "top_of_mind": profile.top_of_mind,
        "brief_history": profile.brief_history,
        # Legacy
        "archetype": profile.archetype,
        "learning_style": profile.learning_style,
        "attributes": profile.attributes,
        "preferences": profile.preferences,
        "knowledge_tracker": profile.knowledge_tracker,
        "active_quests": profile.active_quests,
        "session_log": profile.session_log,
    }

    await svc.save_profile(data)
    return {"status": "saved", "profile": profile}


async def _run_synthesis_bg(db_url: str):
    from src.models.database import async_session_factory
    async with async_session_factory() as db:
        try:
            llm = LLMService(mode="PRO")  # Requires robust parsing
            worker = NarrativeMemoryWorker(llm)
            # using execution_id=0 for manual/background invokes outside agent mode
            await worker.execute(db, execution_id=0, input_data={"limit_sessions": 10})
        except Exception as e:
            logger.error(f"Background synthesis failed: {e}")

@router.post("/profile/synthesize")
async def synthesize_profile_bg(auth: AuthDep, bg_tasks: BackgroundTasks):
    from src.models.database import _engine
    if not _engine:
        raise HTTPException(status_code=500, detail="DB Engine not found")
        
    db_url = str(_engine.url)
    bg_tasks.add_task(_run_synthesis_bg, db_url)
    return {"status": "queued", "message": "Síntese de memória iniciada em background."}


# =============================================================================
# Memory Save/Learn/Forget
# =============================================================================

@router.post("/save")
async def save_memory(request: MemorySaveRequest, auth: AuthDep, db: DbDep):
    """Salva uma memória manualmente via [[SAVE:]] tag ou UI."""
    persona = get_active_persona()

    try:
        vector_svc = get_vector_service(persona)
        vector_svc.add_dynamic_memory(request.title, request.content)
        return {"status": "saved", "title": request.title, "persona": persona}
    except Exception as e:
        logger.error(f"Memory save error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save memory: {e}")


@router.post("/learn")
async def learn_topic(request: MemoryLearnRequest, auth: AuthDep, db: DbDep):
    """Comando /aprender - adiciona conhecimento ao RAG."""
    persona = get_active_persona()

    try:
        vector_svc = get_vector_service(persona)
        vector_svc.add_dynamic_memory(request.topic, request.content)

        svc = MemoryService(db)
        await svc.add_fact(f"Aprendeu: {request.topic}")

        return {"status": "learned", "topic": request.topic, "persona": persona}
    except Exception as e:
        logger.error(f"Learn error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to learn: {e}")


@router.post("/forget", response_model=ForgetResponse)
async def forget_topic(request: MemoryForgetRequest, auth: AuthDep, db: DbDep):
    """Comando /esquecer - DELEÇÃO COMPLETA em 5 camadas (fix do bug V2).
    1. ChromaDB chunks
    2. Arquivos .md do disco (knowledge/)
    3. rag_tracker.json
    4. UserProfile.knowledge_tracker
    5. UserProfile.attributes
    """
    persona = get_active_persona()

    try:
        vector_svc = get_vector_service(persona)
        deleted_chunks = 0
        deleted_files = []

        # Step 1: Delete matching ChromaDB chunks
        results = vector_svc.collection.get(
            where={"type": "dynamic_knowledge"},
            include=["documents", "metadatas"],
        )

        matching_filenames = set()
        if results and results["ids"]:
            ids_to_delete = []
            for i, doc_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}
                doc_text = results["documents"][i] if results["documents"] else ""
                filename = metadata.get("filename", "")

                if request.topic.lower() in filename.lower() or request.topic.lower() in doc_text.lower():
                    ids_to_delete.append(doc_id)
                    if filename:
                        matching_filenames.add(filename)

            if ids_to_delete:
                vector_svc.collection.delete(ids=ids_to_delete)
                deleted_chunks = len(ids_to_delete)

        # Step 2 & 3: Delete matching files from disk + tracker
        import json
        for filename in matching_filenames:
            file_path = vector_svc.knowledge_dir / filename
            if file_path.exists():
                try:
                    file_path.unlink()
                    deleted_files.append(filename)
                    logger.info(f"[FORGET] Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"[FORGET] Error deleting file {file_path}: {e}")

            # Clean tracker
            tracker_file = vector_svc.persona_dir / "rag_tracker.json"
            if tracker_file.exists():
                try:
                    tracker = json.loads(tracker_file.read_text())
                    tracker_key = f"dynamic_knowledge/{filename}"
                    if tracker_key in tracker:
                        del tracker[tracker_key]
                        tracker_file.write_text(json.dumps(tracker))
                except Exception as e:
                    logger.error(f"[FORGET] Error updating tracker: {e}")

        # Steps 4 & 5: Clean profile (knowledge_tracker + attributes)
        svc = MemoryService(db)
        removed_entries = await svc.forget_from_profile(request.topic)

        return ForgetResponse(
            status="forgotten",
            topic=request.topic,
            deleted_chunks=deleted_chunks,
            deleted_files=deleted_files,
            removed_profile_entries=removed_entries,
        )
    except Exception as e:
        logger.error(f"Forget error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to forget: {e}")


# =============================================================================
# RAG Memory CRUD (existing)
# =============================================================================

@router.get("/list")
async def list_memories(
    auth: AuthDep,
    source_type: Optional[str] = Query(None, description="Filter: static_lore, dynamic_knowledge, chat_history"),
    persona: Optional[str] = Query(None, description="Persona name (defaults to active)"),
):
    """Lista memórias RAG da persona ativa."""
    persona_name = persona or get_active_persona()
    vector_svc = get_vector_service(persona_name)
    memories = vector_svc.list_memories(source_type=source_type)
    return {
        "memories": [MemoryItem(**m) for m in memories],
        "total": len(memories),
        "persona": persona_name,
    }


# =============================================================================
# Auto-Profile Management
# =============================================================================

@router.get("/auto-profile", response_model=AutoProfileResponse)
async def get_auto_profile(auth: AuthDep, db: DbDep):
    """Retorna o perfil automático gerado pela IA."""
    svc = MemoryService(db)
    data = await svc.get_auto_profile()
    return AutoProfileResponse(**data)


@router.patch("/auto-profile")
async def patch_auto_profile(request: AutoProfilePatchRequest, auth: AuthDep, db: DbDep):
    """Remove entradas específicas do perfil automático."""
    svc = MemoryService(db)
    removed = await svc.patch_auto_profile(request.model_dump())
    return {"status": "patched", "removed": removed}


@router.post("/auto-profile/clear/{category}")
async def clear_auto_profile_category(category: str, auth: AuthDep, db: DbDep):
    """Limpa uma categoria inteira do perfil automático."""
    valid = ["attributes", "knowledge_tracker", "active_quests", "session_log"]
    if category not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {valid}")

    svc = MemoryService(db)
    success = await svc.clear_auto_profile_category(category)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "cleared", "category": category}


# =============================================================================
# RAG File Management
# =============================================================================

@router.get("/rag/files", response_model=list[RagFileInfo])
async def list_rag_files(
    auth: AuthDep,
    persona: Optional[str] = Query(None, description="Persona name (defaults to active)"),
):
    """Lista arquivos de rag_docs/ e knowledge/ da persona."""
    persona_name = persona or get_active_persona()
    vector_svc = get_vector_service(persona_name)
    files = vector_svc.list_files_on_disk()
    return [RagFileInfo(**f) for f in files]


@router.get("/rag/files/{filename}/path")
async def get_rag_file_path(
    filename: str,
    auth: AuthDep,
    source_type: str = Query("dynamic_knowledge", description="static_lore or dynamic_knowledge"),
    persona: Optional[str] = Query(None),
):
    """Retorna o caminho absoluto do arquivo no disco (usado pelo Electron)."""
    persona_name = persona or get_active_persona()
    vector_svc = get_vector_service(persona_name)
    file_path = vector_svc.get_file_absolute_path(filename, source_type)
    
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
        
    return {"path": str(file_path)}


@router.delete("/rag/files/{filename}")
async def delete_rag_file(
    filename: str,
    auth: AuthDep,
    source_type: str = Query("dynamic_knowledge", description="static_lore or dynamic_knowledge"),
    persona: Optional[str] = Query(None),
):
    """Deleta arquivo do disco + todos os chunks do ChromaDB + tracker."""
    persona_name = persona or get_active_persona()
    vector_svc = get_vector_service(persona_name)
    deleted_chunks = vector_svc.delete_file_and_chunks(filename, source_type)
    return {"status": "deleted", "filename": filename, "deleted_chunks": deleted_chunks}


@router.post("/rag/reindex")
async def reindex_rag(
    auth: AuthDep,
    persona: Optional[str] = Query(None),
):
    """Força re-ingestão completa da base de conhecimento."""
    persona_name = persona or get_active_persona()
    vector_svc = get_vector_service(persona_name)
    chunks_indexed = vector_svc.force_reindex()
    return {"status": "reindexed", "chunks_indexed": chunks_indexed, "persona": persona_name}


@router.get("/rag/stats", response_model=RagStatsResponse)
async def get_rag_stats(
    auth: AuthDep,
    persona: Optional[str] = Query(None),
):
    """Retorna estatísticas da coleção ChromaDB."""
    persona_name = persona or get_active_persona()
    vector_svc = get_vector_service(persona_name)
    stats = vector_svc.get_collection_stats()
    return RagStatsResponse(
        total_chunks=stats.get("total", 0),
        by_type=stats.get("by_type", {}),
        persona=persona_name,
    )


@router.post("/rag/search")
async def search_rag_memories(request: RagSearchRequest, auth: AuthDep):
    """Busca semântica nas memórias RAG com metadata."""
    persona = get_active_persona()
    vector_svc = get_vector_service(persona)
    memories = vector_svc.search_with_metadata(
        query=request.query,
        source_type=request.source_type,
        limit=request.limit,
    )
    return {"memories": memories, "total": len(memories), "persona": persona}


# =============================================================================
# Social Graph Management
# =============================================================================

@router.get("/social-graph", response_model=list[SocialGraphPlatformResponse])
async def get_social_graph(auth: AuthDep, db: DbDep):
    """Retorna todas as entradas do social graph."""
    svc = MemoryService(db)
    graph = await svc.get_social_graph()
    return [
        SocialGraphPlatformResponse(platform=platform, data=data)
        for platform, data in graph.items()
    ]


@router.get("/social-graph/{platform}", response_model=SocialGraphPlatformResponse)
async def get_social_graph_platform(platform: str, auth: AuthDep, db: DbDep):
    """Retorna dados de uma plataforma específica."""
    svc = MemoryService(db)
    graph = await svc.get_social_graph()
    if platform not in graph:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not found")
    return SocialGraphPlatformResponse(platform=platform, data=graph[platform])


@router.put("/social-graph/{platform}")
async def upsert_social_graph_platform(platform: str, data: dict, auth: AuthDep, db: DbDep):
    """Cria ou atualiza dados de uma plataforma no social graph."""
    svc = MemoryService(db)
    await svc.update_social_graph(platform, data)
    return {"status": "saved", "platform": platform}


@router.delete("/social-graph/{platform}")
async def delete_social_graph_platform(platform: str, auth: AuthDep, db: DbDep):
    """Deleta uma plataforma do social graph."""
    svc = MemoryService(db)
    success = await svc.delete_social_graph_platform(platform)
    if not success:
        raise HTTPException(status_code=404, detail=f"Platform '{platform}' not found")
    return {"status": "deleted", "platform": platform}


@router.post("/social-graph/import")
async def import_social_graph(request: SocialGraphImportRequest, auth: AuthDep, db: DbDep):
    """Importa múltiplas plataformas de uma vez."""
    svc = MemoryService(db)
    imported = 0
    for platform, data in request.platforms.items():
        await svc.update_social_graph(platform, data)
        imported += 1
    return {"status": "imported", "imported": imported}


# =============================================================================
# Episodic Memory Management
# =============================================================================

@router.get("/episodes", response_model=list[EpisodeResponse])
async def list_episodes(
    auth: AuthDep,
    db: DbDep,
    persona: Optional[str] = Query(None),
    min_importance: Optional[int] = Query(None, ge=1, le=10),
    min_date: Optional[str] = Query(None),
    max_date: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lista memórias episódicas com filtros."""
    persona_name = persona or get_active_persona()
    svc = MemoryService(db)
    episodes = await svc.get_episodes(
        persona_name=persona_name,
        min_importance=min_importance,
        min_date=min_date,
        max_date=max_date,
        limit=limit,
        offset=offset,
    )
    return [EpisodeResponse(**ep) for ep in episodes]


@router.delete("/episodes/{episode_id}")
async def delete_episode(episode_id: int, auth: AuthDep, db: DbDep):
    """Deleta uma memória episódica."""
    svc = MemoryService(db)
    success = await svc.delete_episode(episode_id)
    if not success:
        raise HTTPException(status_code=404, detail="Episode not found")
    return {"status": "deleted", "id": episode_id}


@router.post("/episodes/bulk-delete")
async def bulk_delete_episodes(request: EpisodeBulkDeleteRequest, auth: AuthDep, db: DbDep):
    """Deleta múltiplas memórias episódicas."""
    svc = MemoryService(db)
    deleted = await svc.bulk_delete_episodes(request.ids)
    return {"status": "deleted", "deleted": deleted}


# =============================================================================
# Persona Memory Management (per-persona quests, session logs, buffer)
# =============================================================================

@router.get("/persona-memory", response_model=PersonaMemoryResponse)
async def get_persona_memory(
    auth: AuthDep,
    db: DbDep,
    persona: Optional[str] = Query(None, description="Persona name (defaults to active)"),
):
    """Retorna memória específica de uma persona (quests, session_log, buffer)."""
    persona_name = persona or get_active_persona()
    svc = MemoryService(db)
    data = await svc.get_persona_memory(persona_name)
    return PersonaMemoryResponse(persona_name=persona_name, **data)


@router.patch("/persona-memory")
async def patch_persona_memory(
    request: PersonaMemoryPatchRequest,
    auth: AuthDep,
    db: DbDep,
    persona: Optional[str] = Query(None),
):
    """Remove entradas específicas da memória de persona."""
    persona_name = persona or get_active_persona()
    svc = MemoryService(db)
    removed = await svc.patch_persona_memory(persona_name, request.model_dump())
    return {"status": "patched", "persona": persona_name, "removed": removed}


@router.delete("/persona-memory/buffer")
async def clear_persona_buffer(
    auth: AuthDep,
    db: DbDep,
    persona: Optional[str] = Query(None),
):
    """Limpa o last_session_buffer de uma persona."""
    persona_name = persona or get_active_persona()
    svc = MemoryService(db)
    removed = await svc.patch_persona_memory(persona_name, {"clear_buffer": True})
    return {"status": "cleared", "persona": persona_name}


# =============================================================================
# RAG Memory CRUD (individual chunks - existing)
# =============================================================================

@router.get("/{memory_id}")
async def get_memory(memory_id: str, auth: AuthDep):
    """Retorna detalhes de uma memória específica."""
    persona = get_active_persona()
    vector_svc = get_vector_service(persona)
    memory = vector_svc.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.put("/{memory_id}")
async def update_memory(memory_id: str, request: MemoryUpdateRequest, auth: AuthDep):
    """Edita conteúdo de uma memória existente."""
    persona = get_active_persona()
    vector_svc = get_vector_service(persona)
    success = vector_svc.update_memory(memory_id, request.content)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "updated", "id": memory_id}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, auth: AuthDep):
    """Deleta uma memória específica."""
    persona = get_active_persona()
    vector_svc = get_vector_service(persona)
    success = vector_svc.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted", "id": memory_id}


# =============================================================================
# Layer 1 — User Preferences (v3.2.0)
# =============================================================================

@router.get("/preferences", response_model=UserPreferencesSchema)
async def get_preferences(auth: AuthDep, db: DbDep):
    """Retorna as preferências explícitas do usuário (Layer 1)."""
    svc = SemanticMemoryService(db)
    prefs = await svc.get_preferences()
    return UserPreferencesSchema(**prefs)


@router.put("/preferences", response_model=UserPreferencesSchema)
async def update_preferences(request: UpdatePreferencesRequest, auth: AuthDep, db: DbDep):
    """Atualiza as preferências explícitas do usuário (Layer 1)."""
    svc = SemanticMemoryService(db)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    prefs = await svc.update_preferences(data)
    return UserPreferencesSchema(**prefs)


@router.patch("/preferences", response_model=UserPreferencesSchema)
async def patch_preferences(request: UpdatePreferencesRequest, auth: AuthDep, db: DbDep):
    """Atualiza parcialmente as preferências do usuário (Layer 1)."""
    svc = SemanticMemoryService(db)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    prefs = await svc.update_preferences(data)
    return UserPreferencesSchema(**prefs)


# =============================================================================
# Layer 2 — Semantic Memory Tiers (v3.2.0)
# =============================================================================

def _item_schema(item: dict) -> SemanticMemoryItemSchema:
    from datetime import datetime
    return SemanticMemoryItemSchema(
        id=item["id"],
        tier=item["tier"],
        content=item["content"],
        source_session_id=item.get("source_session_id"),
        created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else datetime.utcnow(),
        last_reinforced=datetime.fromisoformat(item["last_reinforced"]) if item.get("last_reinforced") else datetime.utcnow(),
        decay_date=datetime.fromisoformat(item["decay_date"]) if item.get("decay_date") else None,
        is_flagged=item.get("is_flagged", False),
        conflict_note=item.get("conflict_note", ""),
        importance=item.get("importance", 5),
        tags=item.get("tags", []),
    )


@router.get("/semantic-tiers", response_model=SemanticTiersResponse)
async def get_semantic_tiers(auth: AuthDep, db: DbDep):
    """Retorna todos os tiers semânticos agrupados (Layer 2)."""
    svc = SemanticMemoryService(db)
    tiers = await svc.get_tiers()
    return SemanticTiersResponse(
        immediate_context=[_item_schema(i) for i in tiers.get("immediate_context", [])],
        top_of_mind=[_item_schema(i) for i in tiers.get("top_of_mind", [])],
        recent_history=[_item_schema(i) for i in tiers.get("recent_history", [])],
        work_context=[_item_schema(i) for i in tiers.get("work_context", [])],
        personal_context=[_item_schema(i) for i in tiers.get("personal_context", [])],
        long_term_background=[_item_schema(i) for i in tiers.get("long_term_background", [])],
    )


@router.get("/semantic-tiers/{tier_name}", response_model=list[SemanticMemoryItemSchema])
async def get_semantic_tier(tier_name: str, auth: AuthDep, db: DbDep):
    """Retorna os itens de um tier específico."""
    svc = SemanticMemoryService(db)
    items = await svc.get_tier(tier_name)
    return [_item_schema(i) for i in items]


@router.post("/semantic-tiers", response_model=SemanticMemoryItemSchema)
async def add_semantic_fact(request: AddSemanticFactRequest, auth: AuthDep, db: DbDep):
    """Adiciona manualmente um fato a um tier semântico."""
    svc = SemanticMemoryService(db)
    item = await svc.add_or_reinforce_fact(
        tier=request.tier,
        content=request.content,
        source_session_id=request.source_session_id,
        importance=request.importance,
        tags=request.tags,
    )
    return _item_schema(item)


@router.delete("/semantic-tiers/tier/{tier_name}")
async def clear_semantic_tier(tier_name: str, auth: AuthDep, db: DbDep):
    """Limpa todos os itens de um tier."""
    svc = SemanticMemoryService(db)
    count = await svc.delete_tier(tier_name)
    return {"status": "cleared", "tier": tier_name, "deleted": count}


@router.delete("/semantic-tiers/{fact_id}")
async def delete_semantic_fact(fact_id: int, auth: AuthDep, db: DbDep):
    """Deleta um fato semântico por ID."""
    svc = SemanticMemoryService(db)
    deleted = await svc.delete_fact(fact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "deleted", "id": fact_id}


@router.post("/semantic-tiers/decay", response_model=DecayPassResponse)
async def run_decay_pass(auth: AuthDep, db: DbDep):
    """Executa um passe de decay manual — promove itens expirados para tiers inferiores."""
    svc = SemanticMemoryService(db)
    count = await svc.run_decay_pass()
    return DecayPassResponse(decayed=count)


@router.post("/migrate-legacy", response_model=MigrateLegacyResponse)
async def migrate_legacy_memory(auth: AuthDep, db: DbDep):
    """
    Migração one-time: converte campos legados do UserProfile para a nova
    arquitetura de tiers semânticos. Idempotente.
    """
    svc = SemanticMemoryService(db)
    migrated = await svc.migrate_legacy()
    return MigrateLegacyResponse(
        status="done" if migrated > 0 else "already_done",
        migrated_facts=migrated,
    )
