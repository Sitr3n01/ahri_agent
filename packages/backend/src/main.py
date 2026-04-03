"""
Ahri V3 - FastAPI Application Entry Point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import get_settings
from src.models.database import init_db, close_db
from src.routers import auth, chat, personas, memory, sessions, agent, search, spotify, agent_mode, settings

logger = logging.getLogger("ahri.main")

from src.engine.model_registry import create_model_registry
from src.engine.tools.registry import ToolRegistry
from src.engine.tools.builtin import register_builtin_tools
from src.engine.query_engine import QueryEngine
from src.engine.hooks.manager import HookManager
from src.engine.compact.manager import CompactManager
from src.engine.permissions.base import PermissionManager
from src.engine.plugins.loader import PluginLoader
from src.engine.agents.spawner import AGENT_TOOLS
from src.routers.engine_v2 import router as engine_v2_router

_engine: QueryEngine | None = None

def get_engine() -> QueryEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized")
    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown da aplicação."""
    settings = get_settings()

    # Garante que diretórios existem
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.vector_db_path.mkdir(parents=True, exist_ok=True)
    settings.personas_dir.mkdir(parents=True, exist_ok=True)

    # Inicializa banco de dados
    logger.info(f"Initializing database: {settings.sqlite_url}")
    await init_db(settings.sqlite_url)

    # Initialize V4 Engine (if enabled)
    if getattr(settings, 'engine_v2_enabled', False):
        global _engine
        # 1. Model Registry
        model_registry = create_model_registry(settings)

        # 2. Tool Registry
        tool_registry = ToolRegistry()
        builtin_count = register_builtin_tools(tool_registry)

        # Register agent spawning tool
        for tool in AGENT_TOOLS:
            tool_registry.register(tool)

        # 3. Hook Manager
        hook_manager = HookManager(default_timeout=getattr(settings, 'engine_hook_timeout', 30))

        # 4. Permission Manager
        permission_manager = PermissionManager(mode=getattr(settings, 'engine_permission_mode', 'auto'))

        # 5. Compact Manager
        compact_manager = CompactManager(
            model_registry=model_registry,
            threshold=getattr(settings, 'engine_compact_threshold', 0.80),
            keep_recent=getattr(settings, 'engine_compact_keep_recent', 4),
        )

        # 6. Plugin Loader
        plugin_dirs = getattr(settings, 'engine_plugin_directories', [])
        if plugin_dirs:
            plugin_loader = PluginLoader(tool_registry, hook_manager)
            plugins_loaded = plugin_loader.load_all(plugin_dirs)
            logger.info(f"Loaded {plugins_loaded} plugin tools")

        # 7. Create Query Engine
        _engine = QueryEngine(
            model_registry=model_registry,
            tool_registry=tool_registry,
            settings=settings,
            permission_manager=permission_manager,
            hook_manager=hook_manager,
            compact_manager=compact_manager,
        )

        logger.info(f"V4 Engine initialized: {tool_registry.enabled_count} tools, "
                     f"{len(model_registry.available_models)} models")

    logger.info("Ahri V3 Backend started.")
    yield

    # Cleanup
    await close_db()
    logger.info("Ahri V3 Backend stopped.")


app = FastAPI(
    title="Ahri V3 API",
    description="AI Companion System with Multi-Persona Support and Agent Capabilities",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - permite Electron (localhost) e mobile (Cloudflare tunnel)
_cors_origins = [
    "http://localhost:5173",   # Vite dev (desktop)
    "http://localhost:5174",   # Vite dev (web)
    "http://localhost:3000",   # Alternate dev port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:3000",
    "app://.",                 # Electron custom protocol
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(personas.router, prefix="/personas", tags=["Personas"])
app.include_router(memory.router, prefix="/memory", tags=["Memory"])
app.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
app.include_router(agent.router, prefix="/agent", tags=["Agent"])
app.include_router(agent_mode.router)  # Agent mode has its own prefix
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(spotify.router, prefix="/spotify", tags=["Spotify"])
app.include_router(settings.router, prefix="/settings", tags=["Settings"])
app.include_router(engine_v2_router)

# Serve static files from data directory
app.mount("/data", StaticFiles(directory=str(get_settings().data_dir)), name="data")


@app.get("/health")
async def health_check():
    """Health check para o Electron saber que o backend está pronto."""
    return {"status": "ok", "version": "0.1.0"}
