"""
Pydantic schemas para request/response da API.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Auth
# =============================================================================
class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ResetPasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=4, max_length=100)


class ForceResetRequest(BaseModel):
    new_password: str = Field(..., min_length=4, max_length=100)


# =============================================================================
# Personas
# =============================================================================
class PersonaTheme(BaseModel):
    # Empty string = no custom override; frontend mergePersonaTheme falls back to per-persona static theme.
    primary: str = ""
    secondary: str = ""
    shadow: str = ""
    glow: str = ""
    avatar: str = ""
    background: str = ""
    background_mobile: str = ""


class PersonaSummary(BaseModel):
    name: str
    display_name: str
    archetype: str = ""
    universe: str = ""
    theme: PersonaTheme = Field(default_factory=PersonaTheme)


class PersonaDetail(PersonaSummary):
    identity_text: str = ""
    spotify_genres: list[str] = []
    has_lore: bool = False
    knowledge_count: int = 0
    session_count: int = 0


class PersonaListResponse(BaseModel):
    personas: list[PersonaSummary]
    active: str


class CreatePersonaRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    archetype: str = ""
    universe: str = ""
    voice_language: str = "pt-br"
    primary_color: str = "#d8b4d8"
    secondary_color: str = "#e9cce9"
    identity_text: str = ""
    spotify_genres: list[str] = []


class UpdatePersonaRequest(BaseModel):
    display_name: Optional[str] = None
    archetype: Optional[str] = None
    universe: Optional[str] = None
    voice_language: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    identity_text: Optional[str] = None
    avatar_base64: Optional[str] = None
    background_base64: Optional[str] = None


# =============================================================================
# Chat
# =============================================================================
class ChatMessageSchema(BaseModel):
    role: str
    content: str
    images: list[str] = []
    timestamp: str = ""
    meta: dict = {}


class FileAttachment(BaseModel):
    data: str  # base64
    name: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None      # ID da conversa (v3.1.0)
    images: list[str] = []
    video: Optional[FileAttachment] = None
    pdfs: list[FileAttachment] = []
    mode: str = "default"                # default, web_search, lore_search
    model: str = "LITE"                   # PRO, FLASH, LITE, DEEPSEEK, LOCAL
    reasoning_level: str = "medium"      # off/low/medium/high
    enable_thinking: bool = False        # Ollama toggle
    auto_save_tags: bool = True          # Process [[SAVE:]] tags in response


class ChatResponse(BaseModel):
    message: ChatMessageSchema
    agent_tasks: list["AgentTaskSchema"] = []
    memory_notifications: list[str] = []
    search_context: Optional[str] = None


# =============================================================================
# Sessions
# =============================================================================
class SessionSummary(BaseModel):
    id: int
    title: str
    persona_name: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionSummary):
    messages: list[ChatMessageSchema]


class SessionCreateRequest(BaseModel):
    title: str = ""


class SessionRenameRequest(BaseModel):
    title: str


# =============================================================================
# Memory
# =============================================================================
class UserProfileSchema(BaseModel):
    # Manual
    name: str = ""
    occupation: str = ""
    custom_instructions: str = ""
    
    # Auto Narrative Context
    work_context: str = ""
    personal_context: str = ""
    top_of_mind: str = ""
    brief_history: str = ""

    # Legacy (To be deprecated)
    archetype: str = ""
    learning_style: str = ""
    attributes: dict = {}
    preferences: dict = {}
    knowledge_tracker: dict = {}
    active_quests: dict = {}
    session_log: list = []


class MemorySaveRequest(BaseModel):
    title: str
    content: str


class MemoryLearnRequest(BaseModel):
    topic: str
    content: str


class MemoryForgetRequest(BaseModel):
    topic: str


class MemoryUpdateRequest(BaseModel):
    content: str


class MemoryItem(BaseModel):
    id: str
    content: str
    type: str = "unknown"
    filename: str = ""
    source: str = ""


# --- Auto-Profile Management ---
class AutoProfileResponse(BaseModel):
    # Narrative Context
    work_context: str = ""
    personal_context: str = ""
    top_of_mind: str = ""
    brief_history: str = ""

    # Legacy
    attributes: dict = {}
    knowledge_tracker: dict = {}
    active_quests: dict = {}
    session_log: list = []


class ManualProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    occupation: Optional[str] = None
    custom_instructions: Optional[str] = None


class AutoProfilePatchRequest(BaseModel):
    remove_attribute_keys: list[str] = []
    update_attributes: dict = {}
    remove_vocabulary_indices: list[int] = []
    remove_concept_indices: list[int] = []
    remove_quest_keys: list[str] = []
    remove_session_log_indices: list[int] = []


# --- RAG File Management ---
class RagFileInfo(BaseModel):
    filename: str
    source_type: str  # "static_lore" | "dynamic_knowledge"
    size_bytes: int
    chunk_count: int
    last_modified: float


class RagStatsResponse(BaseModel):
    total_chunks: int
    by_type: dict[str, int]
    persona: str


class RagSearchRequest(BaseModel):
    query: str
    source_type: Optional[str] = None
    limit: int = 20


# --- Social Graph ---
class SocialGraphPlatformResponse(BaseModel):
    platform: str
    data: dict
    updated_at: str | None = None


class SocialGraphImportRequest(BaseModel):
    platforms: dict[str, dict]


# --- Episodic Memory ---
class EpisodeResponse(BaseModel):
    id: int
    persona_name: str
    date: str
    topics: list[str] = []
    emotional_tone: str = ""
    summary: str = ""
    importance: int = 5
    outcomes: list[str] = []


# --- Enhanced Forget ---
class ForgetResponse(BaseModel):
    status: str
    topic: str
    deleted_chunks: int = 0
    deleted_files: list[str] = []
    removed_profile_entries: list[str] = []


class EpisodeBulkDeleteRequest(BaseModel):
    ids: list[int] = []


# =============================================================================
# Dual-Layer Memory Architecture (v3.2.0)
# =============================================================================

class UserPreferencesSchema(BaseModel):
    """Layer 1: Explicit user-controlled preferences."""
    display_name: str = ""
    pronouns: str = ""
    occupation: str = ""
    location: str = ""
    custom_instructions: str = ""
    topics_to_avoid: str = ""
    persona_style: str = ""


class UpdatePreferencesRequest(BaseModel):
    display_name: Optional[str] = None
    pronouns: Optional[str] = None
    occupation: Optional[str] = None
    location: Optional[str] = None
    custom_instructions: Optional[str] = None
    topics_to_avoid: Optional[str] = None
    persona_style: Optional[str] = None


class SemanticMemoryItemSchema(BaseModel):
    """Layer 2: A single memory fact in a hierarchical tier."""
    id: int
    tier: str
    content: str
    source_session_id: Optional[int] = None
    created_at: datetime
    last_reinforced: datetime
    decay_date: Optional[datetime] = None
    is_flagged: bool = False
    conflict_note: str = ""
    importance: int = 5
    tags: list[str] = []


class SemanticTiersResponse(BaseModel):
    """All six memory tiers grouped."""
    immediate_context: list[SemanticMemoryItemSchema] = []
    top_of_mind: list[SemanticMemoryItemSchema] = []
    recent_history: list[SemanticMemoryItemSchema] = []
    work_context: list[SemanticMemoryItemSchema] = []
    personal_context: list[SemanticMemoryItemSchema] = []
    long_term_background: list[SemanticMemoryItemSchema] = []


class AddSemanticFactRequest(BaseModel):
    tier: str
    content: str
    importance: int = 5
    tags: list[str] = []
    source_session_id: Optional[int] = None


class DecayPassResponse(BaseModel):
    decayed: int


class MigrateLegacyResponse(BaseModel):
    status: str
    migrated_facts: int


# Persona Memory Management
class PersonaMemoryResponse(BaseModel):
    persona_name: str
    active_quests: dict = {}
    session_log: list = []
    session_log_detailed: list = []
    last_session_buffer: list = []


class PersonaMemoryPatchRequest(BaseModel):
    remove_quest_keys: list[str] = []
    remove_session_log_indices: list[int] = []
    remove_session_log_detailed_indices: list[int] = []
    clear_buffer: bool = False


# =============================================================================
# Settings
# =============================================================================
class SettingsSchema(BaseModel):
    gemini_api_key_paid: str = ""
    gemini_api_key_free: str = ""
    openrouter_api_key: str = ""
    openrouter_model_name: str = ""
    google_model_pro: str = "gemini-2.0-pro-exp-02-05"           # Modelo de alta performance
    google_model_flash: str = "gemini-2.5-flash"
    google_model_lite: str = "gemini-3.1-flash-lite-preview"
    google_model_vision: str | None = None
    google_model_search: str | None = None
    google_model_memory: str | None = None
    ollama_chat_model: str = "gpt-oss:20b"
    
    cse_api_key: str = ""
    cse_cx: str = ""
    
    spotipy_client_id: str = ""
    spotipy_client_secret: str = ""
    spotipy_redirect_uri: str = ""
    
    agent_mode_enabled: bool = True
    agent_mode_orchestrator: str = ""
    ollama_base_url: str = ""

    google_api_key_vision_a: str = ""
    google_api_key_vision_b: str = ""
    google_api_key_manager: str = ""
    
    google_api_key_search: str = ""
    google_api_key_search_b: str = ""
    
    google_ai_studio_api_key: str = ""

    deepinfra_api_key: str = ""
    gh_token: str = ""
    gist_id: str = ""

    # Agent Mode v2
    agent_mode_rpm_limit: int = 15
    agent_mode_tpm_limit: int = 250000
    agent_mode_max_parallel: int = 10
    agent_mode_local_model: str = "qwen3:8b"
    agent_mode_api_model: str = "gemini-3.1-flash-lite-preview"

    # Compaction
    compaction_threshold: int = 30
    compaction_recent_window: int = 15

    # Agent Mode API Keys (round-robin)
    agent_api_key_1: str = ""
    agent_api_key_2: str = ""
    agent_api_key_3: str = ""
    agent_api_key_4: str = ""
    agent_api_key_5: str = ""



class UpdateSettingsRequest(BaseModel):
    settings: dict  # Partial update


# =============================================================================
# Models
# =============================================================================
class AvailableModelSchema(BaseModel):
    id: str
    display_name: str
    provider: str  # google_apikey, openrouter, ollama
    color: str = "#8B5CF6"
    description: str = ""
    input_token_limit: int = 0
    output_token_limit: int = 0


class GoogleModelInfo(BaseModel):
    name: str
    display_name: str
    supported_generation_methods: list[str] = []


class GoogleModelCheckResponse(BaseModel):
    models: list[GoogleModelInfo]


# =============================================================================
# Agent
# =============================================================================
class AgentCapability(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    DIR_LIST = "dir_list"
    SHELL_EXECUTE = "shell_execute"
    CODE_EXECUTE = "code_execute"
    BROWSER_OPEN = "browser_open"
    SCREENSHOT = "screenshot"
    CLIPBOARD_READ = "clipboard_read"
    CLIPBOARD_WRITE = "clipboard_write"
    SYSTEM_INFO = "system_info"
    APP_LAUNCH = "app_launch"


class PermissionLevel(str, Enum):
    SAFE = "SAFE"
    CONFIRM = "CONFIRM"
    BLOCKED = "BLOCKED"


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTaskSchema(BaseModel):
    id: int = 0
    capability: AgentCapability
    parameters: dict = {}
    permission_level: PermissionLevel = PermissionLevel.SAFE
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    result: str = ""
    error: str = ""
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AgentExecuteRequest(BaseModel):
    capability: AgentCapability
    parameters: dict = {}


class AgentApproveRequest(BaseModel):
    task_id: int


# =============================================================================
# Agent Mode - Orchestration
# =============================================================================
class AgentExecutionStatus(str, Enum):
    PLANNING = "planning"
    DELIBERATING = "deliberating"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentWorkerType(str, Enum):
    RAG = "RAG"
    CODE = "Code"
    WEB = "Web"
    MEMORY = "Memory"
    VISION = "Vision"
    SHELL = "Shell"
    BROWSER = "Browser"
    ROUTER = "Router"
    SEARCH = "Search"
    DYNAMIC = "Dynamic"


class AgentWorkerTaskSchema(BaseModel):
    id: int = 0
    execution_id: int
    worker_type: AgentWorkerType
    model: str
    input_data: dict = {}
    output_data: dict = {}
    tokens_used: int = 0
    duration_ms: int = 0
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    error: str = ""
    retry_count: int = 0
    reflexion_notes: list = []
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AgentExecutionSchema(BaseModel):
    id: int = 0
    agent_session_id: Optional[int] = None
    goal: str
    orchestrator_model: str
    status: AgentExecutionStatus = AgentExecutionStatus.PLANNING
    plan: dict = {}
    result: str = ""
    error: str = ""
    replan_count: int = 0
    original_plan: Optional[dict] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_tasks: list[AgentWorkerTaskSchema] = []


class AgentSessionSchema(BaseModel):
    id: int = 0
    title: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    executions: list[AgentExecutionSchema] = []


class AgentModeExecuteRequest(BaseModel):
    goal: str
    orchestrator_model: str = "gemini-3.1-flash-lite-preview"
    working_directory: Optional[str] = None  # Project directory context
    reasoning_level: str = "medium"          # off/low/medium/high (Gemini thinking budget)
    enable_thinking: bool = False            # Qwen/Ollama thinking toggle
    internet_search_enabled: bool = False    # Enable web search worker
    images: list[str] = []                   # Base64 images for vision pre-pass
    permission_mode: str = "plan_first"      # supervised/plan_first/auto
    agent_session_id: Optional[int] = None   # Session to link this execution to


# =============================================================================
# Search
# =============================================================================
class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class SearchResult(BaseModel):
    title: str
    link: str
    snippet: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    remaining_quota: int


# =============================================================================
# Spotify
# =============================================================================
class SpotifyContext(BaseModel):
    is_playing: bool = False
    track_name: str = ""
    artist_name: str = ""
    album_name: str = ""
    genres: list[str] = []
    suggested_persona: str = ""


# =============================================================================
# Sync
# =============================================================================
class SyncState(BaseModel):
    active_persona: str
    active_session_id: Optional[int] = None
    user_profile: UserProfileSchema
    recent_messages: list[ChatMessageSchema] = []
    spotify_context: Optional[SpotifyContext] = None


# Resolve forward references
ChatResponse.model_rebuild()
