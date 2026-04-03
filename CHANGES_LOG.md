# Ahri V3 — Changes Log

## Session: 2026-03-20 — Settings + Agent Mode Enhancements

### Summary

| Change | Type | Scope |
|--------|------|-------|
| Directory dialog bug fix | Bug Fix | Electron IPC |
| VS Code button bug fix | Bug Fix | Electron IPC |
| 5 Agent API keys + round-robin | Feature | Backend + Frontend |
| Gemini reasoning levels (low/med/high) | Feature | Backend + Frontend |
| Qwen thinking toggle (on/off) | Feature | Backend + Frontend |
| Internet search worker | Feature | Backend + Frontend |
| Search toggle in agent input bar | Feature | Frontend |

---

### 1. Bug Fix: Directory Selector Not Opening

**Problem:** The `agent:select-directory` IPC handler used `const { dialog } = await import('electron')` (dynamic import) which could fail silently in certain Electron/Vite configurations.

**Fix:** Added `dialog` to the static import from `electron` on line 1 of `main.ts`. Removed the dynamic import. Added try/catch with error logging.

**Files:**
- `packages/desktop/electron/main.ts` — Static import of `dialog`, error handling

---

### 2. Bug Fix: VS Code Editor Button

**Problem:** `spawn('code', [...])` had no error handling. If VS Code wasn't in PATH, it failed silently. No fallback mechanism.

**Fix:** Added try/catch, `child.unref()` for detached processes, `child.on('error')` listener with `code.cmd` fallback, and proper error return values.

**Files:**
- `packages/desktop/electron/main.ts` — Error handling + `code.cmd` fallback
- `packages/desktop/src/features/agent-mode/AgentModeView.tsx` — `.catch()` on IPC calls

---

### 3. Feature: 5 Agent API Keys with Round-Robin

**Purpose:** Gemini Flash Lite free tier allows 15 RPM per API key. With 5 keys rotating in round-robin, we achieve 75 RPM total throughput.

**How it works:**
- `AgentKeyRotator` class in `tpm_manager.py` maintains per-key sliding window RPM counters
- `get_next_key()` returns the next available key (round-robin order)
- If all keys are at limit, returns the key with the shortest wait time
- Thread-safe with `threading.Lock`
- Keys are configured in Settings > API Keys > "Agent Mode Keys (Round-Robin)"

**Configuration:**
1. Open Settings > API Keys tab
2. Scroll to "Agent Mode Keys (Round-Robin)" section
3. Add up to 5 Gemini API keys
4. Each key independently allows 15 RPM
5. Keys are saved to `.env` as `AGENT_API_KEY_1` through `AGENT_API_KEY_5`

**Files:**
- `packages/backend/src/config.py` — 5 new fields + `agent_api_keys` property
- `packages/backend/src/services/tpm_manager.py` — `AgentKeyRotator` class
- `packages/backend/src/models/schemas.py` — Fields in `SettingsSchema`
- `packages/backend/src/routers/settings.py` — Map new fields in response
- `packages/backend/src/routers/agent_mode.py` — Create rotator, pass to orchestrator
- `packages/backend/src/services/orchestrator_service.py` — Use rotator in `_execute_single_worker`
- `packages/backend/src/services/workers/base_worker.py` — `_create_client(api_key=...)` param
- `packages/desktop/src/features/settings/SettingsView.tsx` — UI for 5 key inputs

---

### 4. Feature: Gemini Reasoning Levels

**Purpose:** Gemini models support `thinkingConfig.thinkingBudget` to control reasoning depth. Users can choose how much "thinking" the model does before answering.

**Levels:**
| Level | Token Budget | Use Case |
|-------|-------------|----------|
| Off | 0 | Fast responses, no reasoning |
| Low | 1,024 | Quick tasks, simple questions |
| Medium | 8,192 | Default, balanced |
| High | 24,576 | Complex analysis, deep reasoning |

**How it works:**
- Frontend: Reasoning level selector appears in the model selector popup when Gemini is selected
- Backend: `thinkingConfig` is added to the Gemini REST API payload
- The budget flows: UI → Store → API Client → Router → Orchestrator → Workers → GeminiClient

**Files:**
- `packages/backend/src/core/llm_clients.py` — `thinking_budget` param in `generate_content_rest()`
- `packages/backend/src/services/workers/base_worker.py` — `thinking_budget` param in `_call_llm()`
- `packages/backend/src/services/orchestrator_service.py` — Reasoning level mapping
- `packages/backend/src/models/schemas.py` — `reasoning_level` in `AgentModeExecuteRequest`
- `packages/shared/src/types/agent-mode.ts` — `GeminiReasoningLevel` type
- `packages/desktop/src/stores/agent-mode-store.ts` — `reasoningLevel` state
- `packages/desktop/src/components/AgentModelSelector.tsx` — 4-button radio selector

---

### 5. Feature: Qwen Thinking Toggle

**Purpose:** Ollama/Qwen models support a `think` option that enables chain-of-thought reasoning.

**How it works:**
- When enabled, adds `"think": true` to the Ollama API options
- Toggle appears in the model selector popup when Qwen is selected
- State persists in localStorage

**Files:**
- `packages/backend/src/core/llm_clients.py` — `think` param in `generate_sync()`
- `packages/backend/src/services/workers/base_worker.py` — `enable_thinking` param in `_call_llm()`
- `packages/backend/src/models/schemas.py` — `enable_thinking` in `AgentModeExecuteRequest`
- `packages/shared/src/types/agent-mode.ts` — `enable_thinking` in request type
- `packages/desktop/src/stores/agent-mode-store.ts` — `enableThinking` state
- `packages/desktop/src/components/AgentModelSelector.tsx` — Toggle switch UI

---

### 6. Feature: Internet Search Worker

**Purpose:** Agent mode can now perform web searches when the user enables internet access. Uses the existing `SearchService` (Google Custom Search Engine API).

**How it works:**
- New `SearchWorker` (`search_worker.py`) wraps the existing `SearchService`
- Worker accepts `{query, max_results, synthesize}` input
- Performs search via Google CSE, then optionally summarizes results with LLM
- Conditionally registered: only available when `internet_search_enabled=True` in request
- Orchestrator planning prompts dynamically include Search in available workers list

**UI:**
- Globe icon (🌐) toggle button in agent input bar, between Editor and Status indicator
- When active: highlighted with persona primary color
- State persists in localStorage

**Files:**
- `packages/backend/src/services/workers/search_worker.py` — **NEW FILE**
- `packages/backend/src/models/schemas.py` — `SEARCH` in `AgentWorkerType` enum, `internet_search_enabled` in request
- `packages/backend/src/services/orchestrator_service.py` — Conditional Search worker registration, dynamic planning prompts
- `packages/shared/src/types/agent-mode.ts` — `'Search'` in `AgentWorkerType`, `internet_search_enabled` in request
- `packages/desktop/src/stores/agent-mode-store.ts` — `internetSearchEnabled` state
- `packages/desktop/src/features/agent-mode/AgentModeView.tsx` — Globe toggle button
- `packages/desktop/src/features/settings/SettingsView.tsx` — Search in workers grid
- `packages/shared/src/api-client/index.ts` — `internet_search_enabled` in API call

---

### Architecture Notes

**Orchestrator Params Flow:**
```
User clicks "Execute" in AgentModeView
  → agent-mode-store.executeTask()
    → api.executeAgentMode(goal, model, {reasoning_level, enable_thinking, internet_search_enabled})
      → POST /agent-mode/execute
        → _run_orchestration(...)
          → OrchestratorService.execute_task(..., reasoning_level, enable_thinking, internet_search_enabled)
            → _execute_single_worker()
              → key_rotator.get_next_key()  (round-robin API key)
              → worker.execute(db, execution_id, input_data + _orchestrator_params)
                → BaseWorker._call_llm(..., api_key, thinking_budget, enable_thinking)
                  → GeminiClient.generate_content_rest(prompt, thinking_budget=N)
                  → OllamaClient.generate_sync(messages, think=True/False)
```

**Key Rotator Pattern:**
```
AgentKeyRotator(keys=[key1, key2, key3, key4, key5], rpm_per_key=15)
  → get_next_key()  # Returns (key, wait_seconds)
  → Round-robin: try each key in order
  → Per-key sliding window: deque[float] of timestamps
  → If all keys exhausted: return key with shortest wait
```

---

### Known Limitations

1. **Search quota:** Google CSE free tier has 90 searches/day limit (tracked in `SearchQuota` table)
2. **Thinking budget:** Some Gemini models may not support `thinkingConfig` — the API will ignore it gracefully
3. **Ollama think:** Requires Ollama version that supports the `think` option (recent versions)
4. **Key rotation:** Keys are loaded at startup. If keys change in Settings, restart the backend to refresh the rotator

---

### Testing Checklist

- [ ] Open Agent Mode → click 📁 → verify Windows Explorer dialog opens
- [ ] Select a directory → click VS Code icon → verify VS Code opens
- [ ] Configure 2+ agent API keys in Settings → submit agent task → check backend logs for key rotation
- [ ] Select Gemini model → set reasoning to "High" → submit task → verify `thinkingConfig` in logs
- [ ] Select Qwen model → enable thinking toggle → submit task → verify `think: true` in Ollama payload
- [ ] Enable internet search (globe icon) → submit task requiring web info → verify SearchWorker invoked
- [ ] Verify all settings persist across app restarts (localStorage + .env)
