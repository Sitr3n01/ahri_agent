export interface EngineEvent {
  type: EngineEventType;
  data: Record<string, any>;
  timestamp: number;
  execution_id: string;
  iteration: number;
}

export type EngineEventType =
  | 'engine_start'
  | 'engine_stop'
  | 'iteration_start'
  | 'iteration_end'
  | 'llm_request'
  | 'llm_response'
  | 'tool_use_start'
  | 'tool_use_end'
  | 'tool_permission_ask'
  | 'compact_start'
  | 'compact_end'
  | 'agent_spawn'
  | 'agent_complete'
  | 'text_chunk'
  | 'final_response'
  | 'error'
  | 'cancelled'
  | 'progress';

export interface EngineExecution {
  execution_id: string;
  goal: string;
  model: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  iterations: number;
  total_tokens: number;
  tool_calls_count: number;
  final_response?: string;
  error?: string;
  created_at: string;
  completed_at?: string;
  duration_ms?: number;
  events: EngineEvent[];
}

export interface EngineToolUse {
  tool_name: string;
  arguments: Record<string, any>;
  output?: string;
  error?: string;
  duration_ms: number;
  iteration: number;
}

export interface EngineConfig {
  enabled: boolean;
  default_model: string;
  max_iterations: number;
  permission_mode: 'auto' | 'ask' | 'trust';
  stream_enabled: boolean;
  compact_threshold: number;
  enable_subagents: boolean;
}
