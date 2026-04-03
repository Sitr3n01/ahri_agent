/**
 * Tipos para o sistema de agente.
 */

export type AgentCapability =
  | 'file_read'
  | 'file_write'
  | 'file_delete'
  | 'dir_list'
  | 'shell_execute'
  | 'code_execute'
  | 'browser_open'
  | 'screenshot'
  | 'clipboard_read'
  | 'clipboard_write'
  | 'system_info'
  | 'app_launch';

export type PermissionLevel = 'SAFE' | 'CONFIRM' | 'BLOCKED';

export type AgentTaskStatus = 'pending' | 'awaiting_approval' | 'approved' | 'running' | 'completed' | 'failed';

export interface AgentTask {
  id: number;
  capability: AgentCapability;
  parameters: Record<string, unknown>;
  permission_level: PermissionLevel;
  status: AgentTaskStatus;
  result: string;
  error: string;
  created_at: string | null;
  completed_at: string | null;
}

/**
 * Mapeamento de capabilities para seus níveis de permissão padrão.
 */
export const CAPABILITY_PERMISSIONS: Record<AgentCapability, PermissionLevel> = {
  file_read: 'SAFE',
  dir_list: 'SAFE',
  system_info: 'SAFE',
  clipboard_read: 'SAFE',
  browser_open: 'SAFE',
  app_launch: 'CONFIRM',
  clipboard_write: 'CONFIRM',
  file_write: 'CONFIRM',
  file_delete: 'CONFIRM',
  shell_execute: 'CONFIRM',
  code_execute: 'CONFIRM',
  screenshot: 'CONFIRM',
};
