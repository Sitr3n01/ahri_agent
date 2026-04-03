/**
 * Tipos para o sistema de chat.
 */

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  images: string[];
  timestamp: string;
  meta: Record<string, unknown>;
}

export interface FileAttachment {
  data: string;  // base64
  name: string;
}

export interface ChatRequest {
  message: string;
  session_id?: number;
  images: string[];
  video?: FileAttachment;
  pdfs?: FileAttachment[];
  mode: 'default' | 'web_search' | 'lore_search';
  model: string;
  reasoning_level?: string;
  enable_thinking?: boolean;
  auto_save_tags?: boolean;
}

export interface ChatResponse {
  message: ChatMessage;
  agent_tasks: AgentTask[];
  memory_notifications: string[];
}

export interface SessionSummary {
  id: number;
  title: string;
  persona_name: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends SessionSummary {
  messages: ChatMessage[];
}

// WebSocket message types
export interface WsChatChunk {
  type: 'chunk';
  content: string;
  done: boolean;
}

export interface WsSyncEvent {
  type: 'message_new' | 'persona_switched' | 'memory_updated' | 'session_changed' | 'agent_task_update';
  data: unknown;
}

// Re-export for convenience
import type { AgentTask } from './agent.js';
export type { AgentTask };
