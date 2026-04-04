# Ahri V3 - Project Context & Documentation
**Version:** 3.0.1 (Audited & Fixed)
**Last Updated:** 2026-02-11
**Status:** Production Ready

---

## What Is This Project?

Ahri is an AI companion system with **17 anime-inspired personas**, **3-layer memory** (session, profile, RAG), **Spotify integration**, **multi-LLM support**, and **Japanese teaching capabilities**.

This is **V3**: A complete rewrite from V2 (Python/Streamlit monolith) to a modern monorepo architecture with FastAPI backend, Electron desktop app, and PWA mobile app.

**V2 Location:** `C:\Users\zegil\Documents\GitHub\Ahri V2\Ahri\`
**V3 Location:** `C:\Users\zegil\Documents\GitHub\Ahri V3\`
**Technical Docs:** [DOCUMENTATION.md](./DOCUMENTATION.md)
**Bug Report:** [BUG_REPORT.md](./BUG_REPORT.md)

---

## Architecture

```
ahri-v3/                          # Monorepo (Turborepo + npm workspaces)
├── packages/
│   ├── backend/                  # Python FastAPI (port 8742)
│   │   ├── src/
│   │   │   ├── main.py           # FastAPI app, CORS, lifespan
│   │   │   ├── config.py         # Pydantic BaseSettings (.env)
│   │   │   ├── dependencies.py   # FastAPI Depends() injection
│   │   │   ├── routers/          # 8 routers: auth, chat, personas, memory, sessions, search, spotify, engine_v2
│   │   │   ├── services/         # 7 services (agent mode removido; V4 engine em src/engine/)
│   │   │   ├── core/             # prompt_builder, llm_clients, save_tag_parser, memory_analyzer
│   │   │   ├── models/           # schemas.py (Pydantic), database.py (SQLAlchemy)
│   │   │   └── scripts/          # migrate_data.py (JSON→SQLite)
│   │   └── tests/                # pytest async tests
│   ├── desktop/                  # Electron 33 + React 19 + TypeScript + Vite 6 + Tailwind + Zustand 5
│   │   ├── electron/             # main.ts (IPC, backend lifecycle, tray), preload.ts
│   │   └── src/                  # React app: stores, features, components, styles
│   ├── web/                      # PWA Mobile (React 19 + Vite 6 + Tailwind + Zustand 5)
│   │   ├── src/                  # Stores, features (login, chat, personas, sessions, settings)
│   │   └── public/               # PWA manifest, icons, service worker
│   └── shared/                   # @ahri/shared - TypeScript types, themes (17 personas), API client
└── data/                         # SQLite + ChromaDB + persona files (persona.md, rag_docs/, knowledge/)
```

---

## Migration Status - ✅ COMPLETE

### ✅ Fase 0 - Boilerplate (COMPLETED)
- Monorepo structure with Turborepo + npm workspaces
- All 4 packages initialized (backend, desktop, web, shared)
- Config files: tsconfig, vite, tailwind, postcss, electron-builder, turbo.json

### ✅ Fase 1 - Backend API (COMPLETED)
**Services (7):**
- `llm_service.py` - Multi-LLM wrapper (Gemini/Gemma/DeepSeek/Ollama)
- `memory_service.py` - 3-layer memory (session/profile/RAG)
- `persona_service.py` - Persona loader from persona.md
- `vector_service.py` - ChromaDB wrapper
- `session_service.py` - Chat session CRUD
- `search_service.py` - Google Custom Search API
- `spotify_service.py` - Spotify OAuth + current track

**Core Modules (4):**
- `prompt_builder.py` - System prompt builder
- `llm_clients.py` - Per-request GeminiClient instances (thread-safe fix)
- `save_tag_parser.py` - Parse [[SAVE:]] tags
- `memory_analyzer.py` - Classify memory importance (CRITICAL/IMPORTANT/USEFUL/IGNORE)

**Routers (9):**
- `/auth` - JWT login/refresh
- `/chat` - Messages + WebSocket streaming
- `/personas` - List, get, activate personas
- `/sessions` - CRUD operations
- `/memory` - /memoria, /aprender, /esquecer
- `/search` - Web search, lore search
- `/spotify` - Current track, listening context
- `/engine/v2` - V4 Engine (ativado via `engine_v2_enabled=True`)

**Database (9 tables):**
- UserProfile, ChatSession, ChatMessage, PersonaMemory, SocialGraphEntry, EpisodicMemory
- RagIngestionTracker, SearchQuota, UserPreferences

**Features:**
- JWT auth (access 15min + refresh 7d)
- WebSocket streaming for chat
- File upload (images, video, PDF via Gemini File API)
- Migration script (JSON→SQLite, idempotent)
- Test suite (~25 async tests)
- **Thread-safe LLM clients** (per-request GeminiClient instances)

### ✅ Fase 2 - Desktop App (COMPLETED)

**Stores (5 Zustand):**
- `auth-store.ts` - JWT authentication
- `persona-store.ts` - Persona selection
- `chat-store.ts` - Chat messages, streaming
- `engine-store.ts` - V4 Engine executions
- `ui-store.ts` / `theme-store.ts` / `i18n-store.ts` - UI state

**Features:**
1. ✅ Shared API client (`@ahri/shared/AhriApiClient`)
2. ✅ LoginView with glassmorphism
3. ✅ ChatView with WebSocket streaming
4. ✅ ChatInput (auto-resize textarea, drag & drop, paste images)
5. ✅ MessageBubble (markdown, code blocks, image rendering)
6. ✅ Sidebar (persona selector, session list, logout, settings toggle)
7. ✅ File upload UI (drag & drop, paste, compression)
8. ✅ Vision/Multimodal (Gemini File API for video/PDF)
9. ✅ Terminal commands (/memoria, /aprender, /esquecer)
10. ✅ Auto-Persona Daemon (Spotify polling in Electron)
11. ✅ Persona backgrounds + avatars (17 unique themes)
12. ✅ Search mode toggle (web_search, lore_search, default)
13. ✅ Session rename (inline editing)

**Electron Features:**
- Backend lifecycle management (spawn/kill Python uvicorn)
- IPC handlers for agent capabilities (openFile, readFile, listDir, etc.)
- Window controls (minimize, maximize, close)
- System tray integration
- Auto-Persona Daemon (Spotify → Persona matching every 60s)

**Design System:**
- Glassmorphism CSS (`.glass`, `.glass-dark`, `.glass-strong`)
- 17 persona themes (dynamic CSS variables)
- Tailwind CSS utilities
- Responsive layout
- Animations (fade, slide, pulse)

### 🔄 Fase 3 - V4 Engine (EM DESENVOLVIMENTO)

O Agent Mode original foi **removido** e substituído pelo V4 Engine — uma arquitetura mais limpa baseada em QueryEngine, tools, hooks e plugins.

**Localização:** `packages/backend/src/engine/`

**Componentes implementados:**
- `query_engine.py` - Engine principal (loop de raciocínio + tools)
- `model_registry.py` - Gerenciamento de modelos (Gemini/Ollama/DeepInfra)
- `tools/` - Tool registry + builtins (file, shell, web, vision, memory, search, code)
- `hooks/` - Hook manager (pre/post tool execution)
- `compact/` - Context compaction automática
- `permissions/` - Permission manager (auto/supervised)
- `plugins/` - Plugin loader
- `agents/` - Agent spawner

**Router:** `/engine/v2/execute` (ativado via `engine_v2_enabled=True` no .env)

**Frontend:** `engine-store.ts` (Zustand) — conecta ao novo engine via WebSocket

### ✅ Fase 4 - Mobile PWA (COMPLETED)

**Package `@ahri/web`:**

**Configuration:**
- ✅ Vite config with PWA plugin (vite-plugin-pwa)
- ✅ Service worker (Workbox runtime caching)
- ✅ PWA manifest (icons, theme, display mode)
- ✅ Tailwind + PostCSS config
- ✅ TypeScript config (shared package support)

**Stores (3 Zustand with persist):**
- ✅ `auth-store.ts` - Login/logout, localStorage sync
- ✅ `persona-store.ts` - Persona selection
- ✅ `chat-store.ts` - Chat state, messages

**Views (5):**
- ✅ `LoginView.tsx` - Glassmorphism login
- ✅ `ChatView.tsx` - Touch-optimized chat (auto-resize, image upload)
- ✅ `PersonasView.tsx` - Grid persona selector
- ✅ `SessionsView.tsx` - Session list (rename/delete)
- ✅ `SettingsView.tsx` - Model selector, offline status, PWA install

**Components:**
- ✅ `BottomNav.tsx` - 4-tab navigation (Chat, Personas, Sessions, Settings)
- ✅ `MessageBubble.tsx` - Markdown rendering
- ✅ `ChatHeader.tsx` - Persona info, model display

**Features:**
- ✅ PWA service worker (offline-first)
- ✅ Cache strategies (NetworkFirst for API, CacheFirst for images)
- ✅ Touch-optimized UX (44px minimum touch targets)
- ✅ Safe area support (iOS notch)
- ✅ Bottom navigation (mobile pattern)
- ✅ Glassmorphism design system
- ✅ Responsive mobile layout
- ✅ Pull-to-refresh disabled
- ✅ Image preview before send
- ✅ Session management (create/load/delete/rename)

**Styles:**
- ✅ `globals.css` - Glassmorphism, scrollbars, animations, touch optimizations
- ✅ Tailwind utilities
- ✅ Persona theme CSS variables
- ✅ Dark mode optimizations

---

## Bugs Fixed

### Critical Fixes (V3.0 Release)
1. ✅ **TPMManager Race Condition** - Added `threading.Lock` to prevent concurrent access
2. ✅ **WebSocket Infinite Polling** - Added 10-minute timeout to agent mode WebSocket
3. ✅ **TypeScript rootDir Errors** - Removed rootDir from tsconfig.json in desktop/web

### Critical Fixes (V3.0.1 Audit - 2026-02-11)
4. ✅ **Worker `__init__` Signatures** - Fixed 6 workers (Shell, Memory, Web, Vision, Browser, Router) with wrong `super().__init__()` parameter order and missing `default_model`
5. ✅ **Worker Model Format** - Fixed 7 workers using raw model paths (`gemini/gemma-3-4b-it`) instead of mode strings (`"GOOGLE"`, `"PRO"`) in `_call_llm()` calls
6. ✅ **Worker Method Names** - Fixed 6 workers calling `_create_task()` (nonexistent) instead of `_create_task_record()`
7. ✅ **Orchestrator `async for` Bug** - `generate_response()` is a sync generator, not async. Changed `async for` → `for` in `_plan_task_prompt_based()` and `_synthesize_results()`
8. ✅ **Orchestrator Invalid Model Param** - Removed `model=model` kwarg from `generate_response()` (doesn't accept it). Now calls `set_mode(model)` before generating
9. ✅ **Topological Sort Bug** - Fixed reversed in-degree calculation in `_topological_sort()` that caused wrong execution order of parallel worker tasks

### Frontend Fixes (V3.0.1 Audit - 2026-02-11)
10. ✅ **Desktop Chat Store** - Fixed mutable `.push()` on Zustand state (replaced with immutable spread pattern)
11. ✅ **Web Chat Store** - Fixed type imports and API method alignment with `@ahri/shared`
12. ✅ **Web App.tsx** - Fixed persona type usage

### Code Quality Improvements
- Added error handling validation
- Improved type safety across packages
- Cleaned up temporary files (AGENT_MODE_STATUS.md, PHASE3_*.md, compass artifacts)
- Added comprehensive documentation

**See [BUG_REPORT.md](./BUG_REPORT.md) for full analysis.**

---

## Key Technical Decisions

- **Database:** SQLite via SQLAlchemy async (aiosqlite) - replaces 6+ JSON files
- **Vector DB:** ChromaDB with `all-MiniLM-L6-v2` embeddings
- **LLM Backends:** 4 modes - PRO (gemini-2.5-pro-preview), GOOGLE (Gemma 3 27B), DEEPSEEK (DeepSeek R1 via OpenRouter), LOCAL (Ollama)
- **State Management:** Zustand 5 with persist middleware (no Redux)
- **Styling:** Tailwind CSS + glassmorphism utilities (`.glass`, `.glass-dark`, `.glass-strong`)
- **Auth:** JWT single-user (access 15min + refresh 7d), password in .env
- **Streaming:** WebSocket for chat + agent mode, HTTP fallback
- **Agent Permissions:** 3-tier (SAFE auto-execute, CONFIRM needs approval, BLOCKED rejected)
- **Thread Safety:**
  - Per-request GeminiClient instances (fixes V2 global genai.configure() bug)
  - threading.Lock in TPMManager for concurrent request safety
  - WebSocket timeout protection (10 minutes max)

---

## Tech Stack

| Component | Technology | Version | Notes |
|-----------|-----------|---------|-------|
| **Backend** | FastAPI | 0.115+ | Async Python web framework |
| **Desktop** | Electron | 33.x | Desktop app wrapper |
| **Mobile** | React PWA | 19.x | Progressive Web App |
| **Build** | Turborepo | Latest | Monorepo build system |
| **Database** | SQLite | 3.x | Via SQLAlchemy async |
| **Vector DB** | ChromaDB | Latest | Semantic search |
| **LLM** | Gemini/Gemma | 2.5/3.x | Google AI Studio |
| **Bundler** | Vite | 6.x | Fast ES modules bundler |
| **State** | Zustand | 5.x | React state management |
| **Styling** | Tailwind | 3.4+ | Utility-first CSS |
| **Types** | TypeScript | 5.7+ | Type safety |

---

## Project Structure

```
packages/backend/src/
├── routers/          # 9 API routes
├── services/         # 10 services
│   └── workers/      # 8 agent workers
├── core/             # 4 core modules
├── models/           # SQLAlchemy ORM + Pydantic schemas
└── scripts/          # Migration scripts

packages/desktop/
├── electron/         # Main process + preload
└── src/
    ├── stores/       # 5 Zustand stores
    ├── features/     # Feature modules (auth, chat, sidebar, agent, agent-mode)
    ├── components/   # Shared components (TPMQuotaMeter, DependencyGraph, ExecutionHistory)
    ├── api/          # API client + WebSocket manager
    └── styles/       # Global CSS, glassmorphism

packages/web/
└── src/
    ├── stores/       # 3 Zustand stores (auth, persona, chat)
    ├── features/     # 5 views (login, chat, personas, sessions, settings)
    ├── components/   # BottomNav, MessageBubble, ChatHeader
    ├── api/          # API client
    └── styles/       # Mobile-first CSS

packages/shared/src/
├── types/            # TypeScript types (api, persona, chat, memory, llm, engine)
├── themes/           # 17 persona themes
└── api-client/       # AhriApiClient class
```

---

## Running the Project

### Development

**Backend:**
```bash
cd packages/backend
python -m uvicorn src.main:app --host 0.0.0.0 --port 8742 --reload
```

**Desktop:**
```bash
cd packages/desktop
npm run dev
```

**Web (PWA):**
```bash
cd packages/web
npm run dev
```

**All at once:**
```bash
npm run dev  # Turborepo runs all in parallel
```

### Environment Setup

**`.env` file in `packages/backend/`:**

```bash
# Auth
JWT_SECRET_KEY=your-super-secret-key-min-32-chars-CHANGE-THIS
PASSWORD=your-password

# LLMs
GEMINI_API_KEY=your-gemini-api-key
DEEPSEEK_API_KEY=your-openrouter-key  # Optional

# Spotify (optional)
SPOTIFY_CLIENT_ID=your-client-id
SPOTIFY_CLIENT_SECRET=your-client-secret

# Search (optional)
GOOGLE_SEARCH_API_KEY=your-search-key
GOOGLE_SEARCH_ENGINE_ID=your-engine-id

# Agent Mode
AGENT_MODE_ORCHESTRATOR_MODEL=gemini-2.5-flash
AGENT_MODE_WORKER_MODEL=gemma-3-4b
AGENT_MODE_ENABLE_PARALLEL=true
AGENT_MODE_TPM_LIMIT=15000
```

### Build for Production

**Desktop:**
```bash
cd packages/desktop
npm run build
npm run package  # Creates installer
```

**Web:**
```bash
cd packages/web
npm run build  # Outputs to dist/
```

---

## Testing

**Backend:**
```bash
cd packages/backend
pytest tests/ -v
```

**Type Checking (All Packages):**
```bash
npm run type-check --workspaces
```

---

## Documentation

- **[DOCUMENTATION.md](./DOCUMENTATION.md)** - Complete technical documentation (134 KB)
  - Architecture overview
  - API endpoints
  - Database schema
  - LLM integration
  - Agent Mode system
  - Deployment guide
  - Troubleshooting

- **[BUG_REPORT.md](./BUG_REPORT.md)** - Bug analysis & fixes
  - Critical bugs (race conditions, timeouts)
  - Medium bugs (memory leaks, validation)
  - Code quality issues
  - Security recommendations
  - Performance optimizations

---

## Critical Implementation Notes

### LLM Service API
- `LLMService.generate_response()` is a **sync generator** (yields `str` chunks), NOT async
- Use `for chunk in ...`, never `async for chunk in ...`
- Does NOT accept a `model` parameter - call `set_mode("PRO"|"GOOGLE"|"DEEPSEEK"|"LOCAL")` before generating
- Valid modes: `"PRO"`, `"GOOGLE"`, `"DEEPSEEK"`, `"LOCAL"`

### V4 Engine
- Localizado em `src/engine/` — ativado via `engine_v2_enabled=True` no `.env`
- `QueryEngine` é o ponto de entrada; inicializado no `lifespan()` do `main.py`
- Tools são registradas via `ToolRegistry`; hooks via `HookManager`
- `PermissionLevel` do engine está em `src/engine/tools/base.py` (independente dos schemas)

### Frontend State (Zustand)
- Never mutate state directly with `.push()` - always use immutable patterns: `[...state.array, newItem]`
- Desktop: `auth`, `persona`, `chat`, `engine`, `ui`, `theme`, `i18n` stores
- Web PWA: `auth`, `persona`, `chat` stores (sem engine stores)
- Shared API client is in `@ahri/shared` package

### Common Pitfalls
- Import styles are mixed: backend uses both `from src.x import y` (absolute) and `from ...x import y` (relative)
- `datetime` fields in Pydantic schemas serialize to ISO strings in JSON responses automatically
- WebSocket endpoint de chat: `/chat/ws`

---

## V2 Reference Files

When adding features, reference these V2 source files:
- `brain.py` (1358 lines) - AIEngine, MemoryHandler, PersonaManager
- `vector_brain.py` (205 lines) - ChromaDB RAG
- `web_ui.py` (694+ lines) - Streamlit UI, themes
- `auto_persona_daemon.py` - Spotify polling
- `services/spotify_client.py` - Spotify OAuth
- `services/llm_local_engine.py` - Ollama local

---

## User Preferences

- **Agent capabilities:** Both PC automation + dev tools
- **Database:** SQLite (via SQLAlchemy async)
- **CSS:** Tailwind with glassmorphism
- **Architecture:** Monorepo (Turborepo + npm workspaces)
- **Personas:** 17 anime-inspired personas with unique themes
- **Japanese Teaching:** N5 level tracked in user profile
- **Language:** User speaks Portuguese (pt-br), code comments can be English or Portuguese

---

## What's Next (Future Enhancements)

### Fase 5 - Polish & Portfolio (Not Started)
- [ ] Desktop installer (electron-builder)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Docker containers
- [ ] Production deployment guide
- [ ] Performance benchmarks
- [ ] Security audit
- [ ] User documentation

### Potential Features
- [ ] Voice chat (speech-to-text, text-to-speech)
- [ ] Image generation (DALL-E, Stable Diffusion)
- [ ] Multi-user support
- [ ] Cloud sync (Firebase, Supabase)
- [ ] Browser extension
- [ ] API rate limiting (per-user)
- [ ] Analytics dashboard
- [ ] Custom persona creator

---

## Known Limitations

1. **Single-User:** JWT auth supports only one user (password in .env)
2. **TPM Quota:** 15k tokens/minute limit (Google AI Studio free tier)
3. **Browser Worker:** Requires Playwright installation (`playwright install chromium`)
4. **Offline Mode:** Web scraping, Spotify, and search require internet
5. **LLM Quotas:** Subject to provider rate limits (Gemini, OpenRouter)

---

## Support & Contributing

**Issues:** Check [BUG_REPORT.md](./BUG_REPORT.md) for known issues

**Documentation:** See [DOCUMENTATION.md](./DOCUMENTATION.md) for technical details

**Testing:** Run `pytest` (backend) and `npm run type-check` (frontend)

---

## Creating New Personas - Complete Guide

The Ahri V3 desktop app now includes a full **Persona Editor** in the Settings view. You can create, edit, and manage personas with a visual interface.

### Quick Start

1. **Open Settings:** Click the ⚙️ button in the sidebar
2. **Select a Persona:** Choose any persona from the list to edit
3. **Or Create New:** Click "+ New Persona" button

### Persona Structure

Each persona consists of:

**Files:**
- `data/personas/{name}/persona.md` - Main definition (YAML frontmatter + bio)
- `data/personas/{name}/rag_docs/` - RAG documents (optional)
- `data/personas/{name}/knowledge/` - Additional knowledge files (optional)
- `data/assets/{name}_1.png` - Avatar image (512x512px recommended)
- `data/assets/background_{name}.png` - Desktop background (1920x1080px)
- `data/assets/background_{name}_mobile.png` - Mobile background (1080x1920px, optional)

**Theme Entry:**
- `packages/shared/src/themes/index.ts` - Color theme definition

### Creating a New Persona (Manual Method)

If you need to create a persona manually (e.g., for backend development):

#### 1. Create Directory Structure

```bash
cd data/personas
mkdir my_persona
cd my_persona
mkdir rag_docs knowledge
```

#### 2. Create persona.md

```markdown
---
display_name: "My Persona"
description: "A brief description of this persona"
japanese_level: "N5"
personality_traits:
  - trait1
  - trait2
interests:
  - interest1
  - interest2
---

# My Persona Bio

Write the persona's detailed backstory, personality, and characteristics here.

## Personality

Describe personality traits...

## Background

Describe background story...

## Speech Pattern

Describe how they talk...
```

#### 3. Add Images

Place these files in `data/assets/`:
- `my_persona_1.png` (avatar, 512x512px)
- `background_my_persona.png` (desktop background, 1920x1080px)
- `background_my_persona_mobile.png` (mobile background, 1080x1920px, optional)

If you don't provide a mobile background, the system will use the desktop version as fallback.

#### 4. Update themes/index.ts

Add an entry to the `personaThemes` object in `packages/shared/src/themes/index.ts`:

```typescript
my_persona: {
  primary: '#4169E1',        // Main accent color
  secondary: '#B0C4DE',      // Secondary color
  shadow: 'rgba(65, 105, 225, 0.3)',  // Shadow for glows
  glow: 'rgba(176, 196, 222, 0.5)',   // Glow effect
  avatar: 'my_persona_1.png',
  background: 'background_my_persona.png',
  backgroundMobile: 'background_my_persona_mobile.png',
},
```

**Color Guide:**
- `primary`: Used for accents, borders, message bubbles, avatar borders
- `secondary`: Used for gradients, highlights
- `shadow`: Box shadow color (use rgba with 0.3 opacity)
- `glow`: Glow effect color (use rgba with 0.5 opacity)

**Tip:** Use a color picker tool and convert to hex for primary/secondary, then convert to rgba for shadow/glow.

#### 5. Restart Backend

```bash
cd packages/backend
python -m uvicorn src.main:app --reload
```

The backend will automatically detect the new persona on startup.

### Using the Visual Editor (Recommended)

The Settings UI provides:

✅ **Edit Existing Personas:**
- Change display name and description
- Update theme colors with live preview
- Drag & drop new avatar/background images
- See changes in real-time before saving

✅ **Color Picker:**
- Visual color picker + hex input
- Live preview in message bubbles
- Automatic shadow calculation

✅ **Image Upload:**
- Drag & drop or click to upload
- Supports PNG, JPG, WEBP
- Preview before saving

✅ **Validation:**
- Required fields marked with *
- Hex color validation (#RRGGBB)
- Unsaved changes warning

### Backend Integration (Coming Soon)

The visual editor UI is complete, but backend endpoints need implementation:

**Required Endpoints:**

```python
# POST /personas/create
# Creates new persona folder, persona.md, copies images, updates themes.ts

# POST /personas/{name}/update
# Updates persona.md frontmatter, replaces images if provided, updates themes.ts

# DELETE /personas/{name}
# Removes persona folder, deletes images, removes from themes.ts
```

See `SettingsView.tsx` for implementation guides in the alert messages.

### Best Practices

1. **Image Sizes:**
   - Avatar: 512x512px (square, will be cropped to circle)
   - Desktop BG: 1920x1080px (landscape)
   - Mobile BG: 1080x1920px (portrait, optional)

2. **File Naming:**
   - Use lowercase, no spaces (use underscore or dash)
   - Valid: `my_persona`, `new-character`
   - Invalid: `My Persona`, `new character`

3. **Colors:**
   - Test colors in different lighting (chat background at various opacities)
   - Ensure good contrast for readability
   - Use complementary colors for primary/secondary

4. **persona.md Content:**
   - Write in first person for better immersion
   - Include speech patterns and mannerisms
   - Add interests for context in conversations

5. **RAG Documents:**
   - Add relevant lore, wiki pages, character sheets
   - System will use these for contextual responses
   - Supports TXT, MD, PDF formats

### Troubleshooting

**Persona Not Appearing:**
- Check `data/personas/{name}/persona.md` exists
- Verify YAML frontmatter is valid
- Restart backend

**Images Not Loading:**
- Ensure images are in `data/assets/`
- Check file names match themes.ts exactly
- Verify file permissions

**Colors Not Updating:**
- Clear localStorage in browser DevTools
- Restart desktop app
- Check themes.ts has correct hex values

**Theme Changes Not Reflected:**
- Rebuild shared package: `cd packages/shared && npm run build`
- Restart desktop app

---

**Last Updated:** 2026-02-12
**Version:** 3.0.1
**Status:** Production Ready (Audited) ✅
**Lines of Code:** ~27,000 (Backend: 8,000 | Desktop: 12,000 | Web: 5,000 | Shared: 2,000)
