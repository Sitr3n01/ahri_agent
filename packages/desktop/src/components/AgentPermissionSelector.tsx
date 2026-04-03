/**
 * AgentPermissionSelector - 3-level permission control for agent mode.
 *
 * Modes:
 * - supervised: User approves each step (Phase 1 = same as plan_first with label)
 * - plan_first: Shows plan, user approves before execution
 * - auto: Full autonomy (requires auto_approve_tasks from Settings)
 *
 * Design matches AgentModelSelector / AgentReasoningSelector pattern.
 */

import { useState, useEffect, useRef } from 'react';
import { useAgentModeStore } from '@/stores/agent-mode-store';
import type { AgentPermissionMode } from '@/stores/agent-mode-store';

const PERMISSION_MODES: {
  id: AgentPermissionMode;
  label: string;
  shortLabel: string;
  description: string;
  color: string;
  icon: (color: string) => React.ReactNode;
}[] = [
  {
    id: 'supervised',
    label: 'Supervisionado',
    shortLabel: 'Superv.',
    description: 'Aprove cada etapa antes da execução',
    color: '#10B981', // Emerald Green
    icon: (color) => <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />,
  },
  {
    id: 'plan_first',
    label: 'Planejamento',
    shortLabel: 'Planejar',
    description: 'Revise o plano completo antes de executar',
    color: '#3B82F6', // Blue
    icon: (color) => <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />,
  },
  {
    id: 'auto',
    label: 'Autônomo',
    shortLabel: 'Auto',
    description: 'Executa tudo automaticamente',
    color: '#EF4444', // Red
    icon: (color) => <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: color }} />,
  },
];

function isAutoApproveEnabled(): boolean {
  try {
    const raw = localStorage.getItem('ahri_settings_agent');
    if (!raw) return false;
    const parsed = JSON.parse(raw);
    return parsed?.auto_approve_tasks === true;
  } catch {
    return false;
  }
}

interface AgentPermissionSelectorProps {
  theme: { primary: string; secondary: string; shadow: string };
}

export function AgentPermissionSelector({ theme }: AgentPermissionSelectorProps) {
  const [open, setOpen] = useState(false);
  const [showWarning, setShowWarning] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const permissionMode = useAgentModeStore((s) => s.permissionMode);
  const setPermissionMode = useAgentModeStore((s) => s.setPermissionMode);

  const currentMode = PERMISSION_MODES.find((m) => m.id === permissionMode) || PERMISSION_MODES[1];

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleSelect = (mode: AgentPermissionMode) => {
    if (mode === 'auto' && !isAutoApproveEnabled()) {
      setShowWarning(true);
      setTimeout(() => setShowWarning(false), 3000);
      return;
    }
    setPermissionMode(mode);
    setOpen(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full transition-all duration-300 hover:bg-white/5 active:scale-95 border border-transparent"
        style={{
          fontSize: '0.75rem',
          fontFamily: 'var(--font-sans)',
          fontWeight: 500,
          color: 'var(--text-secondary)', // Cohesion: use secondary color for trigger
        }}
      >
        <span>{currentMode.shortLabel}</span>
        <svg
          width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
          className={`opacity-40 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Popup */}
      {open && (
        <div
          className="absolute bottom-full right-0 mb-2 w-64 rounded-lg overflow-hidden z-50 animate-fade-in-up"
          style={{
            background: 'var(--surface-solid)',
            border: '1px solid var(--glass-border)',
            boxShadow: `0 8px 32px rgba(0,0,0,0.3), 0 0 12px ${theme.shadow}`,
          }}
        >
          {/* Header */}
          <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--glass-border)' }}>
            <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
              Modo de Permissão
            </span>
          </div>

          {/* Options */}
          <div className="py-1">
            {PERMISSION_MODES.map((mode) => {
              const isActive = mode.id === permissionMode;
              const isDisabled = mode.id === 'auto' && !isAutoApproveEnabled();

              return (
                <button
                  key={mode.id}
                  onClick={() => handleSelect(mode.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-colors ${
                    isDisabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-[var(--surface-hover)]'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div
                      className="text-xs font-medium"
                      style={{ color: isActive ? mode.color : 'var(--text-primary)' }}
                    >
                      {mode.label}
                    </div>
                    <div className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                      {isDisabled ? 'Habilite nas Configurações > Agente' : mode.description}
                    </div>
                  </div>
                  {isActive && (
                    <svg
                      width="14" height="14" viewBox="0 0 24 24" fill="none"
                      stroke={mode.color} strokeWidth="3" className="flex-shrink-0"
                    >
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>

          {/* Warning tooltip */}
          {showWarning && (
            <div
              className="px-3 py-2 border-t text-[10px] animate-fade-in"
              style={{
                borderColor: 'var(--glass-border)',
                color: 'var(--warning)',
                background: 'color-mix(in srgb, var(--warning) 10%, transparent)',
              }}
            >
              ⚠ Habilite "Auto-aprovar tarefas" em Configurações &gt; Agente &gt; Geral
            </div>
          )}
        </div>
      )}
    </div>
  );
}
