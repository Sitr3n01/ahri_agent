import { create } from 'zustand';
import type { ChatMessage, SessionSummary } from '@ahri/shared';
import type { AvailableModel } from '@ahri/shared/types/llm.js';
import { api } from '@/api/client';
import { chatWs } from '@/api/websocket';

export interface Attachment {
  type: 'image' | 'video' | 'pdf';
  data: string; // base64
  name: string;
  preview?: string; // data URL for images
}

interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  activeSessionId: number | null;
  sessions: SessionSummary[];
  model: string;
  availableModels: AvailableModel[];
  memoryNotifications: string[];

  // Pending new chat: true when user clicked "New Chat" but hasn't sent a message yet.
  // Session is created lazily on first message (Claude/ChatGPT pattern).
  isPendingNewChat: boolean;

  // Reasoning Settings
  reasoningLevel: string;
  enableThinking: boolean;

  // Chat Settings (hydrated from localStorage)
  streamingEnabled: boolean;
  showTimestamps: boolean;
  autoSaveTags: boolean;
  internetSearchEnabled: boolean;
  globalEnableThinking: boolean;

  // Actions
  setModel: (model: string) => void;
  loadChatSettings: () => void;
  fetchAvailableModels: () => Promise<void>;
  fetchSessions: (persona?: string) => Promise<void>;
  loadSession: (id: number) => Promise<void>;
  createSession: (title?: string) => Promise<void>;
  startNewChat: () => void;
  deleteSession: (id: number) => Promise<void>;
  renameSession: (id: number, title: string) => Promise<void>;
  sendMessage: (message: string, attachments?: Attachment[], mode?: 'default' | 'web_search' | 'lore_search') => Promise<void>;
  sendMessageStreaming: (message: string, attachments?: Attachment[], mode?: 'default' | 'web_search' | 'lore_search') => Promise<void>;
  stopStreaming: () => void;
  addMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  setReasoningLevel: (level: string) => void;
  setEnableThinking: (enabled: boolean) => void;
}

/** Gera um título automático a partir das primeiras palavras da mensagem (Claude pattern). */
function autoTitle(message: string): string {
  const words = message.trim().split(/\s+/).slice(0, 6).join(' ');
  return words.length > 60 ? words.slice(0, 60) + '…' : words;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  streamingContent: '',
  activeSessionId: null,
  sessions: [],
  model: 'LITE',
  availableModels: [],
  memoryNotifications: [],
  reasoningLevel: 'medium',
  enableThinking: false,
  isPendingNewChat: false,

  // Chat settings defaults (overridden by loadChatSettings)
  streamingEnabled: true,
  showTimestamps: true,
  autoSaveTags: true,
  internetSearchEnabled: false,
  globalEnableThinking: false,

  setModel: (model) => set({ model }),
  loadChatSettings: () => {
    try {
      const stored = localStorage.getItem('ahri_settings_chat');
      if (stored) {
        const parsed = JSON.parse(stored);
        set({
          streamingEnabled: parsed.streaming_enabled ?? true,
          showTimestamps: parsed.show_timestamps ?? true,
          autoSaveTags: parsed.auto_save_tags ?? true,
          internetSearchEnabled: parsed.internet_search_enabled ?? false,
          globalEnableThinking: parsed.enable_thinking ?? false,
          reasoningLevel: parsed.reasoning_level ?? 'off',
        });
      }
    } catch { /* ignore parse errors */ }
  },
  setReasoningLevel: (level) => set({ reasoningLevel: level }),
  setEnableThinking: (enabled) => set({ enableThinking: enabled }),

  fetchAvailableModels: async () => {
    try {
      const models = await api.getAvailableModels();
      set({ availableModels: models });
      // Se o modelo atual não está na lista, usa o primeiro disponível
      const currentModel = useChatStore.getState().model;
      if (models.length > 0 && !models.find(m => m.id === currentModel)) {
        set({ model: models[0].id });
      }
    } catch (e) {
      console.error('Failed to fetch available models:', e);
    }
  },

  fetchSessions: async (persona) => {
    try {
      const sessions = await api.listSessions(persona);
      set({ sessions });
    } catch (e) {
      console.error('Failed to fetch sessions:', e);
    }
  },

  loadSession: async (id) => {
    try {
      const detail = await api.getSession(id);
      set({
        activeSessionId: id,
        messages: detail.messages,
        isPendingNewChat: false,
      });
    } catch (e) {
      console.error('Failed to load session:', e);
    }
  },

  createSession: async (title) => {
    try {
      const session = await api.createSession(title);
      set((state) => ({
        sessions: [session, ...state.sessions],
        activeSessionId: session.id,
        messages: [],
        isPendingNewChat: false,
      }));
    } catch (e) {
      console.error('Failed to create session:', e);
    }
  },

  /**
   * Inicia um novo chat localmente (Claude/ChatGPT pattern).
   * NÃO cria sessão no backend ainda — isso acontece ao enviar a primeira mensagem.
   */
  startNewChat: () => {
    set({
      messages: [],
      activeSessionId: null,
      isPendingNewChat: true,
      streamingContent: '',
      isStreaming: false,
      memoryNotifications: [],
    });
  },

  deleteSession: async (id) => {
    try {
      await api.deleteSession(id);
      set((state) => {
        const sessions = state.sessions.filter((s) => s.id !== id);
        const isActive = state.activeSessionId === id;
        return {
          sessions,
          activeSessionId: isActive ? null : state.activeSessionId,
          messages: isActive ? [] : state.messages,
        };
      });
    } catch (e) {
      console.error('Failed to delete session:', e);
    }
  },

  renameSession: async (id, title) => {
    try {
      await api.renameSession(id, title);
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === id ? { ...s, title } : s,
        ),
      }));
    } catch (e) {
      console.error('Failed to rename session:', e);
    }
  },

  // HTTP (non-streaming) fallback
  sendMessage: async (message, attachments = [], mode = 'default') => {
    const { model, reasoningLevel, enableThinking, autoSaveTags, internetSearchEnabled, isPendingNewChat } = get();

    // Se está em modo pendente, cria a sessão agora com o título automático
    if (isPendingNewChat) {
      try {
        const session = await api.createSession(autoTitle(message));
        set((state) => ({
          sessions: [session, ...state.sessions],
          activeSessionId: session.id,
          isPendingNewChat: false,
        }));
      } catch (e) {
        console.error('Failed to auto-create session:', e);
      }
    }

    // Wire: internet_search_enabled → override mode to web_search when default
    const effectiveMode = (mode === 'default' && internetSearchEnabled) ? 'web_search' : mode;

    // Extrai images, video, pdfs
    const images = attachments.filter(a => a.type === 'image').map(a => a.data);
    const video = attachments.find(a => a.type === 'video');
    const pdfs = attachments.filter(a => a.type === 'pdf');

    // Adiciona mensagem do user imediatamente
    const userMsg: ChatMessage = {
      role: 'user',
      content: message,
      images,
      timestamp: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
      meta: {},
    };
    set((state) => ({
      messages: [...state.messages, userMsg],
      isStreaming: true,
    }));

    try {
      const response = await api.sendMessage({
        message,
        session_id: get().activeSessionId ?? undefined,
        images,
        video: video ? { data: video.data, name: video.name } : undefined,
        pdfs: pdfs.map(p => ({ data: p.data, name: p.name })),
        mode: effectiveMode,
        model,
        reasoning_level: reasoningLevel,
        enable_thinking: enableThinking,
        auto_save_tags: autoSaveTags,
      });

      set((state) => ({
        messages: [...state.messages, response.message],
        isStreaming: false,
        memoryNotifications: response.memory_notifications,
      }));
    } catch (e) {
      console.error('Failed to send message:', e);
      const errorMsg: ChatMessage = {
        role: 'assistant',
        content: `[Erro] Falha ao enviar mensagem: ${e}`,
        images: [],
        timestamp: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
        meta: { error: true },
      };
      set((state) => ({
        messages: [...state.messages, errorMsg],
        isStreaming: false,
      }));
    }
  },

  // WebSocket streaming
  sendMessageStreaming: async (message, attachments = [], mode = 'default') => {
    const { model, reasoningLevel, enableThinking, autoSaveTags, internetSearchEnabled, isPendingNewChat } = get();

    // Se está em modo pendente, cria a sessão agora com o título automático
    if (isPendingNewChat) {
      try {
        const session = await api.createSession(autoTitle(message));
        set((state) => ({
          sessions: [session, ...state.sessions],
          activeSessionId: session.id,
          isPendingNewChat: false,
        }));
      } catch (e) {
        console.error('Failed to auto-create session:', e);
      }
    }

    // Wire: internet_search_enabled → override mode to web_search when default
    const effectiveMode = (mode === 'default' && internetSearchEnabled) ? 'web_search' : mode;

    // Extrai images, video, pdfs
    const images = attachments.filter(a => a.type === 'image').map(a => a.data);
    const video = attachments.find(a => a.type === 'video');
    const pdfs = attachments.filter(a => a.type === 'pdf');

    // Adiciona mensagem do user imediatamente
    const userMsg: ChatMessage = {
      role: 'user',
      content: message,
      images,
      timestamp: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
      meta: {},
    };
    set((state) => ({
      messages: [...state.messages, userMsg],
      isStreaming: true,
      streamingContent: '',
    }));

    // Configura handlers
    chatWs.setHandlers({
      onChunk: (content) => {
        set((state) => ({
          streamingContent: state.streamingContent + content,
        }));
      },
      onDone: async (data) => {
        const aiMsg: ChatMessage = {
          role: 'assistant',
          content: data.content,
          images: [],
          timestamp: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
          meta: { model },
        };
        set((state) => ({
          messages: [...state.messages, aiMsg],
          isStreaming: false,
          streamingContent: '',
          memoryNotifications: data.memory_notifications,
        }));

        // Adiciona agent tasks ao agent-store
        if (data.agent_tasks && data.agent_tasks.length > 0) {
          const { useAgentStore } = await import('./agent-store');
          data.agent_tasks.forEach((task: any) => {
            useAgentStore.getState().addTask(task);
          });
        }
      },
      onError: (error) => {
        const errorMsg: ChatMessage = {
          role: 'assistant',
          content: `[Erro] ${error}`,
          images: [],
          timestamp: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
          meta: { error: true },
        };
        set((state) => ({
          messages: [...state.messages, errorMsg],
          isStreaming: false,
          streamingContent: '',
        }));
      },
    });

    // Conecta WS se necessário, senão fallback para HTTP
    if (!chatWs.isConnected) {
      const connected = await chatWs.connect();
      if (!connected) {
        // Revert optimistic update (remove user message) before fallback to avoid duplicate
        set((state) => ({
          messages: state.messages.slice(0, -1),
          isStreaming: false
        }));
        return get().sendMessage(message, attachments, mode);
      }
    }

    chatWs.sendMessage(message, model, get().activeSessionId ?? undefined, images, video, pdfs, effectiveMode, {
      reasoning_level: reasoningLevel,
      enable_thinking: enableThinking,
      auto_save_tags: autoSaveTags,
    });
  },

  stopStreaming: () => {
    const { isStreaming } = get();
    if (!isStreaming) return;

    chatWs.cancel(); // We need to add this method to chatWs
    set({ isStreaming: false, streamingContent: '' });
  },

  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

  clearMessages: () => set({ messages: [], activeSessionId: null }),
}));
