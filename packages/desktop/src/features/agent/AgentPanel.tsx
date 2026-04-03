import { useAgentStore } from '@/stores/agent-store';
import { useAgentModeStore } from '@/stores/agent-mode-store';
import { usePersonaStore } from '@/stores/persona-store';
import { usePersonaTheme } from '@/hooks/usePersonaTheme';
import { ReasoningTimeline } from '@/components/ReasoningTimeline';
import type { AgentWorkerTask } from '@ahri/shared';

const WORKER_ICONS: Record<string, string> = {
  RAG: '📚', Code: '💻', Shell: '⚡', Memory: '🧠',
  Web: '🌐', Vision: '👁', Browser: '🌍', Router: '🔀',
  Search: '🔍', Dynamic: '🔧',
};

const STATUS_COLORS: Record<string, string> = {
  running: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
  awaiting_approval: '#eab308',
};

function WorkerCard({ task }: { task: AgentWorkerTask }) {
  const isRunning = task.status === 'running';
  const statusColor = STATUS_COLORS[task.status] || '#6b7280';
  const icon = WORKER_ICONS[task.worker_type] || '⚙';

  return (
    <div className="rounded-lg p-2.5 space-y-1.5" style={{
      background: 'var(--surface-hover)',
      border: `1px solid ${isRunning ? 'color-mix(in srgb, #3b82f6 30%, var(--glass-border))' : 'var(--glass-border)'}`,
    }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm">{icon}</span>
          <span className="text-[11px] font-semibold" style={{ color: 'var(--text-primary)' }}>
            {task.worker_type} Worker
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {isRunning && (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={statusColor} strokeWidth="2.5" className="animate-spin">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
          )}
          <span className="text-[9px] px-1.5 py-0.5 rounded-md font-medium" style={{
            color: statusColor,
            background: `color-mix(in srgb, ${statusColor} 12%, transparent)`,
          }}>
            {task.status === 'completed' ? '✓' : task.status === 'failed' ? '✗' : task.status === 'running' ? '...' : task.status}
          </span>
        </div>
      </div>

      {/* Task description from input_data */}
      {task.input_data?.description ? (
        <p className="text-[10px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          {String(task.input_data.description as string)}
        </p>
      ) : null}

      {/* Error display */}
      {task.status === 'failed' && task.error && (
        <p className="text-[10px] leading-relaxed" style={{ color: 'var(--error)' }}>
          {task.error}
        </p>
      )}

      {/* Stats footer */}
      <div className="flex items-center gap-3">
        {task.tokens_used > 0 && (
          <span className="text-[9px]" style={{ color: 'var(--text-tertiary)' }}>
            {task.tokens_used.toLocaleString()} tokens
          </span>
        )}
        {task.duration_ms > 0 && (
          <span className="text-[9px]" style={{ color: 'var(--text-tertiary)' }}>
            {(task.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
        {task.model && (
          <span className="text-[9px]" style={{ color: 'var(--text-tertiary)' }}>
            {task.model}
          </span>
        )}
      </div>
    </div>
  );
}

export function AgentPanel() {
  const setPanelOpen = useAgentStore((s) => s.setPanelOpen);
  const activeExecution = useAgentModeStore((s) => s.activeExecution);
  const workerTasks = useAgentModeStore((s) => s.workerTasks);
  const theme = usePersonaTheme();

  // Get tasks for the active execution
  const tasks: AgentWorkerTask[] = activeExecution
    ? (workerTasks.get(activeExecution.id) || activeExecution.worker_tasks || [])
    : [];

  const runningCount = tasks.filter(t => t.status === 'running').length;
  const completedCount = tasks.filter(t => t.status === 'completed').length;
  const totalTokens = tasks.reduce((sum, t) => sum + (t.tokens_used || 0), 0);
  const totalDuration = tasks.reduce((sum, t) => sum + (t.duration_ms || 0), 0);

  const hasPlan = activeExecution?.plan?.reasoning && activeExecution?.plan?.steps?.length > 0;

  return (
    <aside className="w-80 h-full flex flex-col border-l relative z-10" style={{
      borderColor: 'var(--glass-border)',
      background: 'var(--sidebar-bg)',
      backdropFilter: 'blur(24px) saturate(150%)',
      boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.15)',
    }}>
      {/* Header */}
      <div className="p-4 flex items-center justify-between" style={{ borderBottom: '1px solid var(--glass-border)' }}>
        <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          Painel de Agentes
        </h2>
        <button
          onClick={() => setPanelOpen(false)}
          className="p-1.5 rounded-lg transition-colors"
          style={{ color: 'var(--text-tertiary)' }}
          title="Close panel"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {!activeExecution ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center px-4">
              <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>Nenhum worker ativo</p>
              <p className="text-[10px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
                Execute uma tarefa para ver o painel de agentes.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Reasoning Timeline — Execution Plan (moved from chat) */}
            {hasPlan && (
              <ReasoningTimeline
                reasoning={activeExecution.plan!.reasoning || ''}
                deliberation={activeExecution.plan?.deliberation}
                refinedUnderstanding={activeExecution.plan?.refined_understanding}
                steps={activeExecution.plan!.steps || []}
                workerTasks={tasks}
                theme={theme}
              />
            )}

            {/* Workers Section */}
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 px-1">
                <span className="text-xs">⚡</span>
                <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                  Workers {runningCount > 0 ? `(${runningCount} ativo${runningCount > 1 ? 's' : ''})` : ''}
                </span>
              </div>

              {tasks.length === 0 ? (
                <p className="text-[10px] px-1 py-2" style={{ color: 'var(--text-tertiary)' }}>
                  Nenhum worker executou ainda...
                </p>
              ) : (
                <div className="space-y-1.5">
                  {tasks.map((task) => (
                    <WorkerCard key={task.id} task={task} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Footer — totals */}
      {activeExecution && tasks.length > 0 && (
        <div className="px-3 py-2.5 flex items-center justify-between" style={{ borderTop: '1px solid var(--glass-border)' }}>
          <div className="flex items-center gap-3">
            <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
              {completedCount}/{tasks.length} workers
            </span>
            {totalTokens > 0 && (
              <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                {totalTokens.toLocaleString()} tokens
              </span>
            )}
            {totalDuration > 0 && (
              <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                {(totalDuration / 1000).toFixed(1)}s
              </span>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
