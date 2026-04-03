/**
 * Reasoning Timeline - Step-by-step orchestrator thinking visualization
 *
 * Shows:
 * - Main reasoning (why this approach)
 * - Sequential step progression
 * - Current executing step
 * - Completed steps with timestamps
 * - Worker delegation tree
 */

import { useState } from 'react';
import type { AgentWorkerTask } from '@ahri/shared';
import { useThemeStore } from '@/stores/theme-store';

interface Step {
  worker: string;
  description?: string;
  input?: Record<string, any>;
  depends_on?: number[];
}

interface ReasoningTimelineProps {
  reasoning: string;
  deliberation?: string;
  refinedUnderstanding?: string;
  steps: Step[];
  workerTasks: AgentWorkerTask[];
  theme: any;
}

export function ReasoningTimeline({
  reasoning,
  deliberation,
  refinedUnderstanding,
  steps,
  workerTasks,
  theme
}: ReasoningTimelineProps) {
  const themeMode = useThemeStore((s) => s.theme);
  const isLight = themeMode === 'light';
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());
  const [showDeliberation, setShowDeliberation] = useState(false);

  const toggleStep = (idx: number) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(idx)) {
      newExpanded.delete(idx);
    } else {
      newExpanded.add(idx);
    }
    setExpandedSteps(newExpanded);
  };

  // Determine current step based on worker tasks
  const getCurrentStepIndex = (): number => {
    if (workerTasks.length === 0) return -1;

    const lastTask = workerTasks[workerTasks.length - 1];

    // Find step index by matching worker type
    const stepIndex = steps.findIndex((step, idx) => {
      // Match by worker type and check if this task hasn't been completed yet
      return step.worker === lastTask.worker_type &&
        workerTasks.filter(t => t.worker_type === step.worker).length === idx + 1;
    });

    return stepIndex;
  };

  const currentStepIdx = getCurrentStepIndex();

  const getStepStatus = (stepIdx: number): 'pending' | 'running' | 'completed' | 'failed' => {
    // Find matching worker task for this step
    const stepWorker = steps[stepIdx].worker;
    const matchingTasks = workerTasks.filter(t => t.worker_type === stepWorker);

    if (matchingTasks.length === 0) {
      return stepIdx <= currentStepIdx ? 'running' : 'pending';
    }

    const task = matchingTasks[stepIdx] || matchingTasks[matchingTasks.length - 1];

    if (task.status === 'completed') return 'completed';
    if (task.status === 'failed') return 'failed';
    if (task.status === 'running') return 'running';
    return 'pending';
  };

  const getStepTask = (stepIdx: number): AgentWorkerTask | undefined => {
    const stepWorker = steps[stepIdx].worker;
    const matchingTasks = workerTasks.filter(t => t.worker_type === stepWorker);
    return matchingTasks[stepIdx] || matchingTasks[matchingTasks.length - 1];
  };

  const getStepIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <div className="w-6 h-6 rounded-full bg-green-500/20 text-green-500 border border-green-500/30 flex items-center justify-center">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="3">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
        );
      case 'failed':
        return (
          <div className="w-6 h-6 rounded-full bg-red-500/20 text-red-500 border border-red-500/30 flex items-center justify-center">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="3">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        );
      case 'running':
        return (
          <div className="w-6 h-6 rounded-full bg-blue-500/20 text-blue-500 border border-blue-500/30 flex items-center justify-center">
            <div className="w-3.5 h-3.5 border-2 rounded-full animate-spin" style={{ borderColor: 'transparent', borderTopColor: 'currentColor' }} />
          </div>
        );
      default: // pending
        return (
          <div className="w-6 h-6 rounded-full border flex items-center justify-center" style={{ borderColor: 'var(--glass-border)', background: 'rgba(255,255,255,0.03)' }}>
            <div className="w-1.5 h-1.5 rounded-full opacity-40" style={{ background: 'var(--text-tertiary)' }} />
          </div>
        );
    }
  };

  const getWorkerIcon = (worker: string) => {
    const iconProps = { className: "w-4 h-4", strokeWidth: 2, stroke: "currentColor", fill: "none" };
    switch (worker) {
      case 'RAG':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="m15 15 6 6m-5-7c0 3-2 5-5 5s-5-2-5-5 2-5 5-5 5 2 5 5z" />
          </svg>
        );
      case 'Code':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="m10 7-5 5 5 5m4-10 5 5-5 5" />
          </svg>
        );
      case 'Shell':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        );
      case 'Memory':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M9.5 2A1.5 1.5 0 0 0 8 3.5V6a2 2 0 0 1-2 2H3.5a1.5 1.5 0 0 0 0 3H6a2 2 0 0 1 2 2v2.5a1.5 1.5 0 0 0 3 0V16a2 2 0 0 1 2-2h2.5a1.5 1.5 0 0 0 0-3H16a2 2 0 0 1-2-2V3.5A1.5 1.5 0 0 0 12.5 2h-3Z" />
          </svg>
        );
      case 'Web':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        );
      case 'Vision':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" />
          </svg>
        );
      case 'Browser':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <rect width="18" height="18" x="3" y="3" rx="2" ry="2" /><line x1="3" y1="9" x2="21" y2="9" /><line x1="9" y1="21" x2="9" y2="9" />
          </svg>
        );
      case 'Router':
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="m7 11 2-2-2-2m10 10-2 2 2 2m-5-7 4 4m-4 0 4-4" /><path d="M18 10V4c0-1-1-2-2-2H4c-1 0-2 1-2 2v16c0 1 1 2 2 2h12c1 0 2-1 2-2v-6" />
          </svg>
        );
      default:
        return (
          <svg {...iconProps} viewBox="0 0 24 24">
            <path d="M12 15V3m0 12l-4-4m4 4l4-4M2 17l.621 2.485A2 2 0 0 0 4.561 21h14.878a2 2 0 0 0 1.94-1.515L22 17" />
          </svg>
        );
    }
  };

  const formatTimestamp = (timestamp: string | undefined): string => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const calculateDuration = (task: AgentWorkerTask | undefined): string => {
    if (!task || !task.created_at) return '';
    const start = new Date(task.created_at).getTime();
    const end = task.completed_at ? new Date(task.completed_at).getTime() : Date.now();
    const durationMs = end - start;
    return `${(durationMs / 1000).toFixed(1)}s`;
  };

  return (
    <div className="backdrop-blur-3xl rounded-xl p-4 border shadow-2xl transition-all" 
      style={{ 
        borderColor: isLight ? 'rgba(0,0,0,0.08)' : `color-mix(in srgb, ${theme.primary} 20%, var(--glass-border))`,
        background: isLight ? 'rgba(255,255,255,0.75)' : theme.backgroundGlass
      }}
    >
      {/* Header - Discreet */}
      <div className="flex items-start gap-2.5 mb-4">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: `color-mix(in srgb, ${theme.primary} 15%, transparent)`, color: theme.primary }}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-[13px] font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>Orchestrator Reasoning</h3>
          <p className="text-[12px] leading-relaxed italic opacity-60 mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            "{reasoning}"
          </p>
        </div>
      </div>

      {/* Refined Understanding */}
      {refinedUnderstanding && (
        <div className="mb-4 pl-3 py-1.5" style={{ borderLeft: `2px solid ${theme.primary}` }}>
          <p className="text-[12px] font-medium leading-relaxed" style={{ color: 'var(--text-primary)', opacity: 0.8 }}>
            {refinedUnderstanding}
          </p>
        </div>
      )}

      {/* Detailed Deliberation Toggle */}
      {deliberation && (
        <div className="mb-4">
          <button
            onClick={() => setShowDeliberation(!showDeliberation)}
            className="flex items-center gap-1.5 text-[10px] font-mono transition-colors hover:opacity-100"
            style={{ color: 'var(--text-tertiary)', opacity: 0.6 }}
          >
            <svg
              className={`w-2.5 h-2.5 transition-transform duration-200 ${showDeliberation ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeWidth={3}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            {showDeliberation ? 'Hide detailed thinking' : 'Show detailed thinking'}
          </button>

          <div
            className="overflow-hidden transition-all duration-300 ease-in-out"
            style={{ maxHeight: showDeliberation ? '12rem' : '0', opacity: showDeliberation ? 1 : 0 }}
          >
            <div
              className="mt-2 rounded-lg p-3 overflow-y-auto custom-scrollbar"
              style={{
                background: 'var(--code-bg)',
                maxHeight: '12rem',
              }}
            >
              <p className="text-[11px] font-mono leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-secondary)', opacity: 0.7 }}>
                {deliberation}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="space-y-1">
        <div className="text-xs font-semibold mb-3 uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
          Execution Plan ({steps.length} steps)
        </div>

        {steps.map((step, idx) => {
          const status = getStepStatus(idx);
          const task = getStepTask(idx);
          const isExpanded = expandedSteps.has(idx);
          const hasDependencies = step.depends_on && step.depends_on.length > 0;

          return (
            <div key={idx} className="relative">
              {/* Vertical line connector */}
              {idx < steps.length - 1 && (
                <div
                  className="absolute left-3 top-7 w-0.5 h-[calc(100%+4px)] opacity-30"
                  style={{
                    background: status === 'completed' ? theme.primary : (isLight ? 'rgba(0,0,0,0.1)' : 'var(--glass-border)')
                  }}
                />
              )}

              {/* Step card - Compact */}
              <div
                className={`relative rounded-xl p-3 transition-all ${status === 'running' ? 'ring-1 ring-blue-500/30' : ''
                   }`}
                style={{ background: isLight ? 'rgba(255,255,255,0.5)' : theme.backgroundGlass, border: `1px solid ${isLight ? 'rgba(0,0,0,0.05)' : 'var(--glass-border)'}` }}
              >
                <div className="flex items-start gap-3.5">
                  {/* Status icon - Smaller */}
                  <div className="relative flex-shrink-0 mt-0.5">
                    {getStepIcon(status)}

                    {/* Step number badge */}
                    <div className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded flex items-center justify-center text-[7px] font-bold border" style={{ background: 'var(--sidebar-bg)', color: 'var(--text-tertiary)', borderColor: 'var(--glass-border)' }}>
                      {idx}
                    </div>
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span style={{ color: theme.primary }} className="opacity-70 scale-75 origin-left">{getWorkerIcon(step.worker)}</span>
                        <span className="text-[12px] font-bold tracking-tight truncate" style={{ color: 'var(--text-primary)' }}>
                          {step.worker} Worker
                        </span>

                        {/* Dependencies indicator */}
                        {hasDependencies && (
                          <span className="text-[9px] font-mono opacity-30 truncate" style={{ color: 'var(--text-secondary)' }}>
                            [{step.depends_on!.join(', ')}]
                          </span>
                        )}
                      </div>

                      {/* Expand button */}
                      <button
                        onClick={() => toggleStep(idx)}
                        className="w-5 h-5 rounded hover:bg-white/5 transition-colors flex-shrink-0 flex items-center justify-center opacity-40 hover:opacity-100"
                        style={{ color: 'var(--text-tertiary)' }}
                      >
                        <svg
                          className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
                        </svg>
                      </button>
                    </div>

                    {/* Description */}
                    <p className="text-[11px] leading-relaxed mb-2 opacity-70" style={{ color: 'var(--text-secondary)' }}>
                      {step.description}
                    </p>

                    {/* Metadata */}
                    {task && (
                      <div className="flex items-center gap-3 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                        {task.created_at && (
                          <span className="flex items-center gap-1">
                            <svg className="w-2.5 h-2.5 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {formatTimestamp(task.created_at)}
                          </span>
                        )}

                        {task.completed_at && (
                          <span>
                            {calculateDuration(task)}
                          </span>
                        )}

                        {task.tokens_used > 0 && (
                          <span>
                            {task.tokens_used.toLocaleString()} tokens
                          </span>
                        )}
                      </div>
                    )}

                    {/* Expanded details */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t space-y-2" style={{ borderColor: 'var(--glass-border)' }}>
                        {/* Input parameters */}
                        {step.input && Object.keys(step.input).length > 0 && (
                          <div className="rounded-lg p-3" style={{ background: 'var(--code-bg)' }}>
                            <div className="text-xs font-semibold mb-2" style={{ color: 'var(--info)' }}>Input Parameters</div>
                            <pre className="text-xs whitespace-pre-wrap font-mono" style={{ color: 'var(--text-secondary)' }}>
                              {JSON.stringify(step.input, null, 2)}
                            </pre>
                          </div>
                        )}

                        {/* Output data */}
                        {task?.output_data && status === 'completed' && (
                          <div className="rounded-lg p-3" style={{ background: 'var(--code-bg)' }}>
                            <div className="text-xs font-semibold mb-2 flex items-center gap-1" style={{ color: 'var(--success)' }}>
                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                              Output
                            </div>
                            <pre className="text-xs whitespace-pre-wrap font-mono max-h-40 overflow-y-auto custom-scrollbar" style={{ color: 'var(--text-secondary)' }}>
                              {JSON.stringify(task.output_data, null, 2)}
                            </pre>
                          </div>
                        )}

                        {/* Error */}
                        {task?.error && status === 'failed' && (
                          <div className="rounded-lg p-3 border" style={{ background: 'var(--error-bg, rgba(239,68,68,0.1))', borderColor: 'var(--error-border, rgba(239,68,68,0.2))' }}>
                            <div className="text-xs font-semibold mb-2" style={{ color: 'var(--error)' }}>Error</div>
                            <p className="text-xs font-mono" style={{ color: 'var(--error)' }}>{task.error}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary stats */}
      <div className="mt-6 pt-4 border-t" style={{ borderColor: 'var(--glass-border)' }}>
        <div className="flex items-center justify-between text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <div className="flex items-center gap-4">
            <span>
              Completed: {steps.filter((_, idx) => getStepStatus(idx) === 'completed').length}/{steps.length}
            </span>
            {workerTasks.length > 0 && (
              <span>
                Total tokens: {workerTasks.reduce((sum, t) => sum + (t.tokens_used || 0), 0).toLocaleString()}
              </span>
            )}
          </div>

          {currentStepIdx >= 0 && currentStepIdx < steps.length && (
            <div style={{ color: 'var(--info)' }}>
              Current: Step {currentStepIdx} ({steps[currentStepIdx].worker})
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
