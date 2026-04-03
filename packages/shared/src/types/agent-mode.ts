/**
 * Agent Mode Types - Orchestrated multi-agent task execution.
 *
 * These types align with backend Pydantic schemas in:
 * packages/backend/src/models/schemas.py
 */

import type { AgentTaskStatus } from './agent.js';

export type AgentExecutionStatus = 'planning' | 'deliberating' | 'awaiting_approval' | 'running' | 'completed' | 'failed';

export type AgentWorkerType =
  | 'RAG'
  | 'Code'
  | 'Web'
  | 'Memory'
  | 'Vision'
  | 'Shell'
  | 'Browser'
  | 'Router'
  | 'Search'
  | 'Dynamic';

// Re-export AgentTaskStatus for convenience
export type { AgentTaskStatus };

export interface AgentWorkerTask {
  id: number;
  execution_id: number;
  worker_type: AgentWorkerType;
  model: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown>;
  tokens_used: number;
  duration_ms: number;
  status: AgentTaskStatus;
  error: string;
  retry_count: number;
  reflexion_notes: ReflexionNote[];
  created_at: string;
  completed_at: string | null;
}

export interface AgentSession {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  executions: AgentExecution[];
}

export interface AgentExecution {
  id: number;
  agent_session_id?: number;
  goal: string;
  orchestrator_model: string;
  status: AgentExecutionStatus;
  plan: {
    reasoning?: string;
    deliberation?: string;
    refined_understanding?: string;
    steps: Array<{
      worker: AgentWorkerType;
      input: Record<string, unknown>;
      description?: string;
      depends_on?: number[];
    }>;
  };
  result: string;
  error: string;
  replan_count: number;
  original_plan?: AgentExecution['plan'];
  created_at: string;
  completed_at: string | null;
  worker_tasks: AgentWorkerTask[];
}

export interface AgentModeExecuteRequest {
  goal: string;
  orchestrator_model?: string;  // default: "gemini-3.1-flash-lite"
  working_directory?: string;   // Project directory context
  reasoning_level?: GeminiReasoningLevel;  // Gemini thinking budget
  enable_thinking?: boolean;               // Qwen/Ollama thinking toggle
  internet_search_enabled?: boolean;       // Enable Search worker
  images?: string[];                       // Base64 images for vision pre-pass
  permission_mode?: string;                // supervised/plan_first/auto
  agent_session_id?: number;               // Session to link this execution to
}

export interface TPMStatus {
  tokensUsed: number;
  tokensRemaining: number;
  limitTPM: number;
  utilizationPercent: number;
  // RPM (requests per minute)
  requestsUsed: number;
  requestsRemaining: number;
  limitRPM: number;
  rpmUtilizationPercent: number;
}

export type AgentModelId = 'qwen-3.5-local' | 'gemini-flash-lite';

export type GeminiReasoningLevel = 'off' | 'low' | 'medium' | 'high';

// ── Event Log Types (real-time WebSocket streaming) ──

export type AgentEventType =
  | 'plan_created'
  | 'plan_deliberated'
  | 'plan_revised'
  | 'worker_started'
  | 'worker_tool_called'
  | 'worker_tool_result'
  | 'worker_completed'
  | 'worker_failed'
  | 'worker_retry'
  | 'evaluation_result'
  | 'replan_triggered'
  | 'synthesis_started'
  | 'execution_completed'
  | 'execution_failed'
  | 'rate_limit_wait'
  | 'tpm_status';

export interface AgentEvent {
  id: number;
  execution_id: number;
  event_type: AgentEventType;
  timestamp: number;
  data: Record<string, unknown>;
  worker_type?: AgentWorkerType;
  step_index?: number;
}

// ── Reflexion / Self-Correction Types ──

export interface ReflexionNote {
  attempt: number;
  error_type: 'temporary' | 'logical' | 'permanent';
  what_happened: string;
  what_to_change: string;
}
