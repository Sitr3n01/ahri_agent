import { create } from 'zustand';
import type { EngineEvent, EngineExecution } from '@ahri/shared';

interface EngineState {
  // Current execution
  currentExecution: EngineExecution | null;
  events: EngineEvent[];
  isRunning: boolean;

  // History
  executions: EngineExecution[];

  // WebSocket
  ws: WebSocket | null;

  // Actions
  startExecution: (goal: string, options?: { model?: string; permissionMode?: string; directory?: string; }) => void;
  sendResponse: (data: any) => void;
  cancelExecution: () => void;
  handleEvent: (event: EngineEvent) => void;
  clearEvents: () => void;
  loadHistory: () => Promise<void>;
}

export const useEngineStore = create<EngineState>((set, get) => ({
  currentExecution: null,
  events: [],
  isRunning: false,
  executions: [],
  ws: null,

  startExecution: (goal: string, options?: { model?: string; permissionMode?: string; directory?: string; }) => {
    const token = localStorage.getItem('ahri_access_token') || '';
    
    // Connect to the V4 engine websocket with complete context
    const params = new URLSearchParams({
      goal,
      model: options?.model || 'fast',
      token
    });
    
    if (options?.permissionMode) params.append('permission', options.permissionMode);
    if (options?.directory) params.append('cwd', options.directory);

    const ws = new WebSocket(`ws://localhost:8742/engine/v2/ws?${params.toString()}`);

    ws.onmessage = (msg) => {
      try {
        const event: EngineEvent = JSON.parse(msg.data);
        get().handleEvent(event);
      } catch (e) {
        console.error('Failed to parse engine event:', e);
      }
    };

    ws.onclose = () => {
      set({ isRunning: false, ws: null });
    };

    set({
      ws,
      isRunning: true,
      events: [],
      currentExecution: {
        execution_id: '',
        goal,
        model: options?.model || 'fast',
        status: 'running',
        iterations: 0,
        total_tokens: 0,
        tool_calls_count: 0,
        events: [],
        created_at: new Date().toISOString(),
      },
    });
  },

  sendResponse: (data: any) => {
    const { ws } = get();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'permission_response', data }));
    }
  },

  cancelExecution: () => {
    const { ws } = get();
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'cancel' }));
      setTimeout(() => ws.close(), 100);
    }
    set({ isRunning: false, ws: null });
  },

  handleEvent: (event: EngineEvent) => {
    set((state) => {
      const events = [...state.events, event];
      const execution = state.currentExecution
        ? { ...state.currentExecution, events }
        : null;

      // Update execution state based on event type
      if (execution) {
        switch (event.type) {
          case 'engine_start':
            execution.execution_id = event.execution_id;
            execution.status = 'running';
            break;
          case 'engine_stop':
            execution.status = event.data.reason === 'completed' ? 'completed' : 'failed';
            execution.total_tokens = event.data.total_tokens;
            break;
          case 'iteration_end':
            execution.iterations = event.iteration;
            execution.total_tokens = event.data.total_tokens;
            break;
          case 'tool_use_end':
            execution.tool_calls_count += 1;
            break;
          case 'final_response':
            execution.final_response = event.data.content;
            break;
          case 'error':
            execution.error = event.data.error;
            break;
        }
      }

      return { events, currentExecution: execution };
    });
  },

  clearEvents: () => set({ events: [], currentExecution: null }),

  loadHistory: async () => {
    try {
      const response = await fetch('http://localhost:8742/engine/v2/executions');
      const data = await response.json();
      set({ executions: data });
    } catch (e) {
      console.error('Failed to load engine history:', e);
    }
  },
}));
