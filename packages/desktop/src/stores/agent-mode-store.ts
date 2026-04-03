/**
 * Agent Mode Store - Zustand state management for orchestrated task execution.
 *
 * V2: Adds model selection, directory context, RPM tracking.
 * Thread-safe: store actions use immutable patterns (no .push()).
 */

import { create } from 'zustand';
import type { AgentExecution, AgentSession, AgentWorkerTask, TPMStatus, AgentModelId, GeminiReasoningLevel } from '@ahri/shared';
import { api } from '../api/client';

export type AgentPermissionMode = 'supervised' | 'plan_first' | 'auto';

interface AgentModeState {
  // State
  executions: AgentExecution[];
  activeExecution: AgentExecution | null;
  workerTasks: Map<number, AgentWorkerTask[]>;
  isLoading: boolean;
  error: string | null;
  tpmStatus: TPMStatus;

  // Agent Mode v2 — model & directory selection
  selectedModel: AgentModelId;
  selectedDirectory: string | null;
  recentDirectories: string[];

  // Agent Mode v3 — reasoning & internet search
  reasoningLevel: GeminiReasoningLevel;
  enableThinking: boolean;
  internetSearchEnabled: boolean;

  // Agent Mode v4 — permission mode
  permissionMode: AgentPermissionMode;

  // Agent Mode v5 — sessions
  sessions: AgentSession[];
  activeSession: AgentSession | null;

  // Actions
  executeTask: (goal: string, orchestrator?: string, attachments?: string[]) => Promise<void>;
  pollStatus: (executionId: number) => Promise<void>;
  loadWorkerTasks: (executionId: number) => Promise<void>;
  clearHistory: () => void;
  setActiveExecution: (execution: AgentExecution | null) => void;
  setTPMStatus: (status: TPMStatus) => void;

  // Model & directory actions
  setSelectedModel: (model: AgentModelId) => void;
  setSelectedDirectory: (dir: string | null) => void;
  loadRecentDirectories: () => Promise<void>;

  // Reasoning & internet actions
  setReasoningLevel: (level: GeminiReasoningLevel) => void;
  setEnableThinking: (enabled: boolean) => void;
  setInternetSearchEnabled: (enabled: boolean) => void;

  // Permission mode actions
  setPermissionMode: (mode: AgentPermissionMode) => void;
  approveExecution: (executionId: number) => Promise<void>;
  cancelExecution: (executionId: number) => Promise<void>;
  rejectExecution: (executionId: number) => Promise<void>;
  approveWorkerTask: (taskId: number) => Promise<void>;
  skipWorkerTask: (taskId: number) => Promise<void>;

  // WebSocket updates (partial merges to preserve existing state)
  updateExecution: (update: Partial<AgentExecution> & { execution_id?: number }) => void;
  addWorkerTask: (task: AgentWorkerTask) => void;
  updateWorkerTask: (task: AgentWorkerTask) => void;

  // History management
  deleteExecution: (executionId: number) => void;

  // Session actions
  loadSessions: () => Promise<void>;
  setActiveSession: (session: AgentSession | null) => void;
  deleteSession: (sessionId: number) => Promise<void>;
}

// Persist model selection in localStorage
function getPersistedModel(): AgentModelId {
  try {
    const stored = localStorage.getItem('ahri-agent-model');
    if (stored === 'qwen-3.5-local' || stored === 'gemini-flash-lite') return stored;
  } catch { /* ignore */ }
  return 'gemini-flash-lite';
}

function getPersistedDirectory(): string | null {
  try {
    return localStorage.getItem('ahri-agent-directory') || null;
  } catch { return null; }
}

function getPersistedReasoning(): GeminiReasoningLevel {
  try {
    const stored = localStorage.getItem('ahri-agent-reasoning');
    if (stored === 'off' || stored === 'low' || stored === 'medium' || stored === 'high') return stored;
  } catch { /* ignore */ }
  return 'medium';
}

function getPersistedThinking(): boolean {
  try {
    return localStorage.getItem('ahri-agent-thinking') === 'true';
  } catch { return false; }
}

function getPersistedInternetSearch(): boolean {
  try {
    return localStorage.getItem('ahri-agent-internet') === 'true';
  } catch { return false; }
}

function getPersistedPermissionMode(): AgentPermissionMode {
  try {
    const stored = localStorage.getItem('ahri-agent-permission');
    if (stored === 'supervised' || stored === 'plan_first' || stored === 'auto') return stored;
  } catch { /* ignore */ }
  return 'plan_first';
}

export const useAgentModeStore = create<AgentModeState>((set, get) => ({
  // Initial state
  executions: [],
  activeExecution: null,
  workerTasks: new Map(),
  isLoading: false,
  error: null,
  tpmStatus: {
    tokensUsed: 0, tokensRemaining: 250000, limitTPM: 250000, utilizationPercent: 0,
    requestsUsed: 0, requestsRemaining: 15, limitRPM: 15, rpmUtilizationPercent: 0,
  },

  // Agent Mode v2 defaults
  selectedModel: getPersistedModel(),
  selectedDirectory: getPersistedDirectory(),
  recentDirectories: [],

  // Agent Mode v3 defaults
  reasoningLevel: getPersistedReasoning(),
  enableThinking: getPersistedThinking(),
  internetSearchEnabled: getPersistedInternetSearch(),

  // Agent Mode v4 defaults
  permissionMode: getPersistedPermissionMode(),

  // Agent Mode v5 defaults
  sessions: [],
  activeSession: null,

  // Model & directory actions
  setSelectedModel: (model: AgentModelId) => {
    localStorage.setItem('ahri-agent-model', model);
    set({ selectedModel: model });
  },

  setSelectedDirectory: (dir: string | null) => {
    if (dir) localStorage.setItem('ahri-agent-directory', dir);
    else localStorage.removeItem('ahri-agent-directory');
    set({ selectedDirectory: dir });

    // Also add to recent dirs via IPC
    if (dir && window.ahri?.agent?.addRecentDir) {
      window.ahri.agent.addRecentDir(dir).then(dirs => {
        set({ recentDirectories: dirs });
      }).catch(() => { /* ignore */ });
    }
  },

  loadRecentDirectories: async () => {
    try {
      if (window.ahri?.agent?.getRecentDirs) {
        const dirs = await window.ahri.agent.getRecentDirs();
        set({ recentDirectories: dirs });
      }
    } catch { /* ignore */ }
  },

  // Reasoning & internet actions
  setReasoningLevel: (level: GeminiReasoningLevel) => {
    localStorage.setItem('ahri-agent-reasoning', level);
    set({ reasoningLevel: level });
  },

  setEnableThinking: (enabled: boolean) => {
    localStorage.setItem('ahri-agent-thinking', String(enabled));
    set({ enableThinking: enabled });
  },

  setInternetSearchEnabled: (enabled: boolean) => {
    localStorage.setItem('ahri-agent-internet', String(enabled));
    set({ internetSearchEnabled: enabled });
  },

  setPermissionMode: (mode: AgentPermissionMode) => {
    localStorage.setItem('ahri-agent-permission', mode);
    set({ permissionMode: mode });
  },

  approveExecution: async (executionId: number) => {
    try {
      const execution = await api.approveExecution(executionId);
      set({ activeExecution: execution });
      // Resume polling
      pollExecutionUntilComplete(executionId);
    } catch (e: any) {
      console.error('[AgentMode] Approve failed:', e);
      set({ error: e?.message || 'Failed to approve execution' });
    }
  },

  cancelExecution: async (executionId: number) => {
    try {
      const execution = await api.cancelAgentMode(executionId);
      set({ activeExecution: execution });
    } catch (e: any) {
      console.error('[AgentMode] Cancel failed:', e);
      set({ error: e?.message || 'Failed to cancel execution' });
    }
  },

  rejectExecution: async (executionId: number) => {
    try {
      const execution = await api.rejectExecution(executionId);
      set({ activeExecution: execution });
    } catch (e: any) {
      console.error('[AgentMode] Reject failed:', e);
      set({ error: e?.message || 'Failed to reject execution' });
    }
  },

  approveWorkerTask: async (taskId: number) => {
    try {
      await api.approveWorkerTask(taskId);
    } catch (e: any) {
      console.error('[AgentMode] Approve worker task failed:', e);
      set({ error: e?.message || 'Failed to approve worker task' });
    }
  },

  skipWorkerTask: async (taskId: number) => {
    try {
      await api.skipWorkerTask(taskId);
    } catch (e: any) {
      console.error('[AgentMode] Skip worker task failed:', e);
      set({ error: e?.message || 'Failed to skip worker task' });
    }
  },

  // Execute new task
  executeTask: async (goal: string, orchestrator?: string, attachments: string[] = []) => {
    set({ isLoading: true, error: null });

    try {
      const { selectedModel, selectedDirectory, reasoningLevel, enableThinking, internetSearchEnabled, permissionMode } = get();

      // Map frontend model IDs to backend mode strings
      const modelMap: Record<string, string> = {
        'qwen-3.5-local': 'LOCAL',
        'gemini-flash-lite': 'LITE',
      };

      const rawModel = orchestrator || selectedModel;
      const orchestratorModel = modelMap[rawModel] || rawModel;

      // Wrap goal with directory context if needed
      const contextualGoal = selectedDirectory
        ? `No diretório [${selectedDirectory}]: ${goal}`
        : goal;

      // Timeout: 30s to prevent infinite hang
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('Timeout: backend não respondeu em 30s. Verifique se o backend está rodando.')), 30000)
      );

      const execution = await Promise.race([
        api.executeAgentMode(contextualGoal, orchestratorModel, {
          reasoning_level: reasoningLevel,
          enable_thinking: enableThinking,
          internet_search_enabled: internetSearchEnabled,
          images: attachments,
          permission_mode: permissionMode,
          agent_session_id: get().activeSession?.id,
        }),
        timeoutPromise,
      ]);

      set({
        activeExecution: execution,
        executions: [execution, ...get().executions],
        isLoading: false,
        error: null,
      });

      // If execution came with a session ID, update active session and refresh sidebar
      if (execution.agent_session_id && !get().activeSession) {
        try {
          const session = await api.getAgentSession(execution.agent_session_id);
          set({ activeSession: session });
          get().loadSessions(); // Refresh sidebar session list
        } catch { /* ignore */ }
      } else if (execution.agent_session_id && get().activeSession) {
        // Session already active — just refresh the list to show new execution under it
        get().loadSessions();
      }

      // Start polling for status updates
      pollExecutionUntilComplete(execution.id);

    } catch (error: any) {
      const message = error?.message || 'Falha ao executar tarefa';
      console.error('[AgentMode] Execution failed:', message);
      set({ isLoading: false, error: message });
    }
  },

  // Poll execution status
  pollStatus: async (executionId: number) => {
    try {
      const execution = await api.getAgentModeStatus(executionId);

      if (get().activeExecution?.id === executionId) {
        set({ activeExecution: execution });
      }

      set({
        executions: get().executions.map(e =>
          e.id === executionId ? execution : e
        ),
      });

      if (execution.worker_tasks && execution.worker_tasks.length > 0) {
        const workerTasks = new Map(get().workerTasks);
        workerTasks.set(executionId, execution.worker_tasks);
        set({ workerTasks });
      }
    } catch (error) {
      console.error('[AgentMode] Status poll failed:', error);
    }
  },

  // Load worker tasks separately
  loadWorkerTasks: async (executionId: number) => {
    try {
      const tasks = await api.getAgentModeWorkers(executionId);
      const workerTasks = new Map(get().workerTasks);
      workerTasks.set(executionId, tasks);
      set({ workerTasks });
    } catch (error) {
      console.error('[AgentMode] Worker tasks load failed:', error);
    }
  },

  setTPMStatus: (status: TPMStatus) => set({ tpmStatus: status }),

  clearHistory: () => set({
    executions: [],
    activeExecution: null,
    workerTasks: new Map(),
  }),

  setActiveExecution: (execution: AgentExecution | null) => {
    set({ activeExecution: execution });
    if (execution && !get().workerTasks.has(execution.id)) {
      get().loadWorkerTasks(execution.id);
    }
  },

  // WebSocket updates (immutable patterns)
  updateExecution: (update: Partial<AgentExecution> & { execution_id?: number }) => {
    // Merge partial update into existing execution (preserves worker_tasks, result, etc.)
    const id = update.id || update.execution_id;
    const active = get().activeExecution;
    if (active && id === active.id) {
      const merged = { ...active, ...update, worker_tasks: active.worker_tasks };
      // Preserve worker_tasks from the active execution (managed by addWorkerTask/updateWorkerTask)
      // But allow full replacement if update includes non-empty worker_tasks
      if (update.worker_tasks && update.worker_tasks.length > 0) {
        merged.worker_tasks = update.worker_tasks;
      }
      set({ activeExecution: merged as AgentExecution });
    }
    set({
      executions: get().executions.map(e =>
        e.id === id ? { ...e, ...update } as AgentExecution : e
      ),
    });
  },

  addWorkerTask: (task: AgentWorkerTask) => {
    const workerTasks = new Map(get().workerTasks);
    const existingTasks = workerTasks.get(task.execution_id) || [];
    if (!existingTasks.find(t => t.id === task.id)) {
      const updated = [...existingTasks, task];
      workerTasks.set(task.execution_id, updated);
      // Also sync to activeExecution so UI renders worker cards
      const active = get().activeExecution;
      if (active?.id === task.execution_id) {
        set({ workerTasks, activeExecution: { ...active, worker_tasks: updated } });
      } else {
        set({ workerTasks });
      }
    }
  },

  updateWorkerTask: (task: AgentWorkerTask) => {
    const workerTasks = new Map(get().workerTasks);
    const existingTasks = workerTasks.get(task.execution_id) || [];
    const updated = existingTasks.map(t => t.id === task.id ? task : t);
    workerTasks.set(task.execution_id, updated);
    // Also sync to activeExecution so UI renders updated worker cards
    const active = get().activeExecution;
    if (active?.id === task.execution_id) {
      set({ workerTasks, activeExecution: { ...active, worker_tasks: updated } });
    } else {
      set({ workerTasks });
    }
  },

  deleteExecution: (executionId: number) => {
    const workerTasks = new Map(get().workerTasks);
    workerTasks.delete(executionId);
    set({
      executions: get().executions.filter(e => e.id !== executionId),
      activeExecution: get().activeExecution?.id === executionId ? null : get().activeExecution,
      workerTasks,
    });
  },

  // Session actions
  loadSessions: async () => {
    try {
      const sessions = await api.getAgentSessions();
      set({ sessions });
    } catch (e) {
      console.error('[AgentMode] Failed to load sessions:', e);
    }
  },

  setActiveSession: (session: AgentSession | null) => {
    // Only reset activeExecution when switching to a DIFFERENT session (or null)
    if (session?.id !== get().activeSession?.id) {
      set({ activeSession: session, activeExecution: null });
    } else {
      set({ activeSession: session });
    }
  },

  deleteSession: async (sessionId: number) => {
    try {
      await api.deleteAgentSession(sessionId);
      set({
        sessions: get().sessions.filter(s => s.id !== sessionId),
        activeSession: get().activeSession?.id === sessionId ? null : get().activeSession,
      });
    } catch (e) {
      console.error('[AgentMode] Failed to delete session:', e);
    }
  },
}));

// Track active polling intervals to prevent leaks
const _activePolls = new Map<number, ReturnType<typeof setInterval>>();

// Helper: Poll execution until completed/failed
function pollExecutionUntilComplete(executionId: number) {
  // Clear any existing poll for this execution
  const existing = _activePolls.get(executionId);
  if (existing) {
    clearInterval(existing);
    _activePolls.delete(executionId);
  }

  const pollInterval = 2000;
  let pollCount = 0;
  const maxPolls = 300; // Max 10 minutes (300 * 2s)

  const interval = setInterval(async () => {
    const store = useAgentModeStore.getState();
    const execution = store.executions.find(e => e.id === executionId);

    if (
      !execution ||
      execution.status === 'completed' ||
      execution.status === 'failed' ||
      pollCount >= maxPolls
    ) {
      clearInterval(interval);
      _activePolls.delete(executionId);
      if (pollCount >= maxPolls) {
        console.warn('[AgentMode] Polling timeout reached for execution', executionId);
      }
      return;
    }

    await store.pollStatus(executionId);
    pollCount++;
  }, pollInterval);

  _activePolls.set(executionId, interval);
}
