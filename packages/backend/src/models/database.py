"""
SQLAlchemy models e engine SQLite.
Substitui os arquivos JSON (user_profile.json, memory.json, history/*.json, etc).
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON, ForeignKey, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# =============================================================================
# User Profile (substitui data/global/user_profile.json)
# =============================================================================
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, default=1)
    
    # --- Instruções Manuais (Editáveis no Front) ---
    name = Column(String(100), default="Usuário")
    occupation = Column(String(200), default="")
    custom_instructions = Column(Text, default="")
    
    # --- Contexto Narrativo Sintético (Gerado pela IA) ---
    work_context = Column(Text, default="")
    personal_context = Column(Text, default="")
    top_of_mind = Column(Text, default="")
    brief_history = Column(Text, default="")

    # --- Legacy Keys (Mantidos provisoriamente caso necessário para migração) ---
    archetype = Column(String(200), default="")
    learning_style = Column(String(200), default="")
    attributes = Column(JSON, default=dict)
    preferences = Column(JSON, default=dict)
    knowledge_tracker = Column(JSON, default=dict)
    active_quests = Column(JSON, default=dict)
    session_log = Column(JSON, default=list)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Social Graph (substitui data/global/social_graph.json)
# =============================================================================
class SocialGraphEntry(Base):
    __tablename__ = "social_graph_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)    # spotify, instagram, twitter
    data = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Persona Memory (substitui data/personas/{name}/memory.json)
# =============================================================================
class PersonaMemory(Base):
    __tablename__ = "persona_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_name = Column(String(50), nullable=False, unique=True, index=True)
    active_quests = Column(JSON, default=dict)
    session_log = Column(JSON, default=list)
    session_log_detailed = Column(JSON, default=list)
    last_session_buffer = Column(JSON, default=list)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Chat Sessions (substitui data/personas/{name}/history/*.json)
# =============================================================================
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_name = Column(String(50), nullable=False, index=True)
    title = Column(String(200), default="")
    original_filename = Column(String(200), default="")  # Para referência durante migração
    compacted_summary = Column(Text, default="")          # Summary of compacted older messages
    compacted_up_to = Column(Integer, default=0)           # order_index up to which messages were compacted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_order", "session_id", "order_index"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)        # user, assistant, model, system
    content = Column(Text, default="")
    images = Column(JSON, default=list)               # Base64 encoded images
    timestamp = Column(String(20), default="")        # HH:MM:SS format from original
    order_index = Column(Integer, default=0)
    meta = Column(JSON, default=dict)                 # auto_generated, model_used, etc.
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


# =============================================================================
# RAG Ingestion Tracker (substitui data/personas/{name}/rag_tracker.json)
# =============================================================================
class RagIngestionTracker(Base):
    __tablename__ = "rag_ingestion_tracker"

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_name = Column(String(50), nullable=False, index=True)
    file_key = Column(String(300), nullable=False)   # e.g., "static_lore/lore.md"
    last_modified = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# Search Quota (substitui websearch_quota tracking in-memory)
# =============================================================================
class SearchQuota(Base):
    __tablename__ = "search_quota"

    id = Column(Integer, primary_key=True, default=1)
    date = Column(String(10), nullable=False)         # YYYY-MM-DD
    count = Column(Integer, default=0)
    max_daily = Column(Integer, default=90)


# =============================================================================
# Episodic Memory (NOVA - Memória episódica estruturada)
# =============================================================================
class EpisodicMemory(Base):
    __tablename__ = "episodic_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    persona_name = Column(String(50), nullable=False, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    topics = Column(JSON, default=list)              # ["japanese", "coding", "personal"]
    emotional_tone = Column(String(50), default="")  # "focused", "playful", "melancholic"
    summary = Column(Text, default="")
    importance = Column(Integer, default=5)           # 1-10 scale
    outcomes = Column(JSON, default=list)             # ["learned hiragana T-row", "fixed bug"]


# =============================================================================
# Agent Tasks (NOVA - Tarefas do agente)
# =============================================================================
class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    capability = Column(String(50), nullable=False)  # file_read, shell_execute, etc.
    parameters = Column(JSON, default=dict)
    permission_level = Column(String(20), default="SAFE")  # SAFE, CONFIRM, BLOCKED
    status = Column(String(20), default="pending")   # pending, approved, running, completed, failed
    result = Column(Text, default="")
    error = Column(Text, default="")
    execution_id = Column(Integer, ForeignKey("agent_executions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# =============================================================================
# Agent Mode - Sessions (groups related executions)
# =============================================================================
class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    executions = relationship("AgentExecution", back_populates="session", cascade="all, delete-orphan")


# =============================================================================
# Agent Mode - Orchestrated Executions
# =============================================================================
class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_session_id = Column(Integer, ForeignKey("agent_sessions.id", ondelete="SET NULL"), nullable=True)
    goal = Column(Text, nullable=False)                  # User's task description
    orchestrator_model = Column(String(100), nullable=False)  # "gemini-2.5-flash", "gemini-3.1-flash-lite"
    status = Column(String(20), default="planning")      # planning, deliberating, running, completed, failed
    plan = Column(JSON, default=dict)                    # Orchestrator's step breakdown
    result = Column(Text, default="")                    # Final synthesized output
    error = Column(Text, default="")
    images = Column(JSON, default=list)                  # Base64 encoded images for context
    permission_mode = Column(String(20), default="auto")  # auto, plan_first, supervised
    replan_count = Column(Integer, default=0, server_default="0")  # Number of replans triggered
    original_plan = Column(JSON, nullable=True)           # Plan before revision (if replanned)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    session = relationship("AgentSession", back_populates="executions")
    worker_tasks = relationship("AgentWorkerTask", back_populates="execution", cascade="all, delete-orphan")


class AgentWorkerTask(Base):
    __tablename__ = "agent_worker_tasks"
    __table_args__ = (
        Index("ix_worker_tasks_execution_id", "execution_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(Integer, ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False)
    worker_type = Column(String(50), nullable=False)     # RAG, Code, Web, Memory, Vision, Shell, Browser, Router
    model = Column(String(100), nullable=False)          # "gemini-3.1-flash-lite", etc.
    input_data = Column(JSON, default=dict)              # Worker prompt + parameters
    output_data = Column(JSON, default=dict)             # Worker's structured result
    tokens_used = Column(Integer, default=0)             # For TPM tracking
    duration_ms = Column(Integer, default=0)
    status = Column(String(20), default="pending")       # pending, running, completed, failed
    error = Column(Text, default="")
    retry_count = Column(Integer, default=0, server_default="0")  # Self-correction retry count
    reflexion_notes = Column(JSON, default=list)          # Reflexion notes from self-correction
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    execution = relationship("AgentExecution", back_populates="worker_tasks")


class TPMQuota(Base):
    __tablename__ = "tpm_quotas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_hash = Column(String(64), nullable=False)    # SHA256 hash of API key
    provider = Column(String(50), nullable=False)        # google_gemini, deepinfra, ollama
    model = Column(String(100), nullable=False)          # gemini-3.1-flash-lite, gemini-2.5-flash, etc.
    tokens_used = Column(Integer, default=0)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)


# =============================================================================
# Dual-Layer Memory Architecture (v3.2.0)
# =============================================================================

class UserPreferences(Base):
    """Layer 1: Explicit user-controlled preferences. AI never writes here."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, default=1)

    # Identity
    display_name = Column(String(100), default="Usuário")
    pronouns = Column(String(50), default="")
    occupation = Column(String(200), default="")
    location = Column(String(200), default="")

    # Behavioral directives (free-form text the user writes)
    custom_instructions = Column(Text, default="")

    # Hard limits
    topics_to_avoid = Column(Text, default="")
    persona_style = Column(Text, default="")

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SemanticMemoryTier(Base):
    """Layer 2: AI-managed hierarchical semantic memory with decay."""
    __tablename__ = "semantic_memory_tiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tier = Column(String(30), nullable=False, index=True)
    # Values: immediate_context | top_of_mind | recent_history |
    #         work_context | personal_context | long_term_background

    content = Column(Text, nullable=False)

    source_session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_reinforced = Column(DateTime, default=datetime.utcnow, nullable=False)

    decay_date = Column(DateTime, nullable=True)
    # Set when this item should be re-evaluated for tier demotion

    is_flagged = Column(Boolean, default=False)
    # True when content conflicts with an older fact

    conflict_note = Column(Text, default="")
    importance = Column(Integer, default=5)  # 1-10 scale
    tags = Column(JSON, default=list)


# =============================================================================
# Engine V4 Tables
# =============================================================================
class EngineExecution(Base):
    """V4 Engine execution record."""
    __tablename__ = "engine_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String, unique=True, nullable=False, index=True)
    goal = Column(Text, nullable=False)
    model = Column(String, nullable=False)
    status = Column(String, default="running")  # running, completed, failed, cancelled
    system_prompt = Column(Text, default="")

    # Metrics
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    iterations = Column(Integer, default=0)
    tool_calls_count = Column(Integer, default=0)

    # Sub-agent info
    parent_id = Column(String, nullable=True)
    depth = Column(Integer, default=0)

    # Result
    final_response = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Relationships
    tool_uses = relationship("EngineToolUse", back_populates="execution", cascade="all, delete-orphan")


class EngineToolUse(Base):
    """V4 Engine tool use record."""
    __tablename__ = "engine_tool_uses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String, ForeignKey("engine_executions.execution_id"), nullable=False)
    tool_name = Column(String, nullable=False)
    arguments = Column(JSON, default={})
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, default=0)
    iteration = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    execution = relationship("EngineExecution", back_populates="tool_uses")


class EnginePlugin(Base):
    """Installed plugin record."""
    __tablename__ = "engine_plugins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    version = Column(String, nullable=False)
    description = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    installed_at = Column(DateTime, default=datetime.utcnow)
    config = Column(JSON, default={})


# =============================================================================
# Database Engine
# =============================================================================
_engine = None
_session_factory = None


async def init_db(database_url: str):
    """Inicializa o engine e cria todas as tabelas (+ migração incremental)."""
    global _engine, _session_factory

    _engine = create_async_engine(database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        # Create all new tables
        await conn.run_sync(Base.metadata.create_all)

        # Incremental migrations for columns added after initial schema
        await _run_migrations(conn)


async def _run_migrations(conn):
    """Run safe ALTER TABLE migrations for columns added to existing tables."""
    import sqlalchemy

    migrations = [
        # v3.0.2: Add agent_session_id to agent_executions
        ("agent_executions", "agent_session_id", "ALTER TABLE agent_executions ADD COLUMN agent_session_id INTEGER REFERENCES agent_sessions(id)"),
        # v3.1.0: Agent improvements - replanning tracking
        ("agent_executions", "replan_count", "ALTER TABLE agent_executions ADD COLUMN replan_count INTEGER DEFAULT 0"),
        ("agent_executions", "original_plan", "ALTER TABLE agent_executions ADD COLUMN original_plan JSON"),
        # v3.1.0: Agent improvements - self-correction tracking
        ("agent_worker_tasks", "retry_count", "ALTER TABLE agent_worker_tasks ADD COLUMN retry_count INTEGER DEFAULT 0"),
        ("agent_worker_tasks", "reflexion_notes", "ALTER TABLE agent_worker_tasks ADD COLUMN reflexion_notes JSON DEFAULT '[]'"),
        # Narrative Synthetic Memory Migrations
        ("user_profiles", "occupation", "ALTER TABLE user_profiles ADD COLUMN occupation VARCHAR(200) DEFAULT ''"),
        ("user_profiles", "custom_instructions", "ALTER TABLE user_profiles ADD COLUMN custom_instructions TEXT DEFAULT ''"),
        ("user_profiles", "work_context", "ALTER TABLE user_profiles ADD COLUMN work_context TEXT DEFAULT ''"),
        ("user_profiles", "personal_context", "ALTER TABLE user_profiles ADD COLUMN personal_context TEXT DEFAULT ''"),
        ("user_profiles", "top_of_mind", "ALTER TABLE user_profiles ADD COLUMN top_of_mind TEXT DEFAULT ''"),
        ("user_profiles", "brief_history", "ALTER TABLE user_profiles ADD COLUMN brief_history TEXT DEFAULT ''"),
        # v3.2.0: Dual-layer memory architecture migration flag
        ("user_profiles", "migration_v2_done", "ALTER TABLE user_profiles ADD COLUMN migration_v2_done BOOLEAN DEFAULT 0"),
    ]

    for table, column, sql in migrations:
        try:
            # Check if column already exists
            result = await conn.execute(sqlalchemy.text(f"PRAGMA table_info({table})"))
            columns = [row[1] for row in result.fetchall()]
            if column not in columns:
                await conn.execute(sqlalchemy.text(sql))
        except Exception:
            pass  # Column already exists or table doesn't exist yet


from typing import AsyncGenerator
# ... imports

# ...

def async_session_factory():
    """Returns a new async session for use outside FastAPI dependency injection.
    Used by background tasks that need their own DB session lifecycle."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection para FastAPI - retorna uma sessão async."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session


async def close_db():
    """Fecha o engine de forma limpa."""
    global _engine
    if _engine:
        await _engine.dispose()
