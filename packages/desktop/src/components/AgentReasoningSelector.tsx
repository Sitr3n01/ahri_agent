import { useState, useRef, useEffect } from 'react';
import { useAgentModeStore } from '@/stores/agent-mode-store';
import type { GeminiReasoningLevel } from '@ahri/shared';

const REASONING_LEVELS: { id: GeminiReasoningLevel; label: string; desc: string }[] = [
  { id: 'off', label: 'Off', desc: 'Sem raciocínio' },
  { id: 'low', label: 'Baixo', desc: '~1K tokens' },
  { id: 'medium', label: 'Médio', desc: '~8K tokens' },
  { id: 'high', label: 'Alto', desc: '~24K tokens' },
];

interface AgentReasoningSelectorProps {
  theme: { primary: string; secondary: string; shadow: string };
}

export function AgentReasoningSelector({ theme }: AgentReasoningSelectorProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const selectedModel = useAgentModeStore((s) => s.selectedModel);
  const reasoningLevel = useAgentModeStore((s) => s.reasoningLevel);
  const setReasoningLevel = useAgentModeStore((s) => s.setReasoningLevel);
  const enableThinking = useAgentModeStore((s) => s.enableThinking);
  const setEnableThinking = useAgentModeStore((s) => s.setEnableThinking);

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

  // Se o modelo for Qwen, vamos mostrar apenas um toggle de on/off no formato de botão dropdown curto?
  // Para ficar igual ao SpeedModeSelector, o botão sempre dirá o modo atual.
  
  if (selectedModel === 'qwen-3.5-local') {
    return (
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setEnableThinking(!enableThinking)}
          className="flex items-center gap-1 px-2 py-1 rounded-full transition-all duration-300 hover:bg-white/5 border border-transparent"
          title="Raciocínio Ativo/Desativado"
        >
          <span className="text-[0.7rem]">{enableThinking ? 'Thinking' : 'Off'}</span>
        </button>
      </div>
    );
  }

  // Se for Gemini (Flash Lite):
  if (selectedModel === 'gemini-flash-lite') {
    const currentLabel = REASONING_LEVELS.find(l => l.id === reasoningLevel)?.label || 'Off';

    return (
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 px-2 py-1 rounded-full transition-all duration-300 hover:bg-white/5 border border-transparent"
          style={{
            fontSize: '0.7rem',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            color: 'var(--text-secondary)',
          }}
        >
          <span>{currentLabel}</span>
          <svg
            width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
            className={`opacity-40 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {open && (
          <div
            className="absolute right-0 bottom-full mb-2 rounded-lg overflow-hidden z-50 min-w-[150px] animate-fade-in"
            style={{
              background: 'var(--surface-solid)',
              border: '1px solid var(--glass-border)',
              backdropFilter: 'none',
              boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
            }}
          >
            {REASONING_LEVELS.map((level) => (
              <button
                key={level.id}
                onClick={() => {
                  setReasoningLevel(level.id);
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-xs transition-colors duration-100"
                style={{
                  color: reasoningLevel === level.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                  background: reasoningLevel === level.id ? 'var(--surface-hover)' : 'transparent',
                }}
                onMouseEnter={(e) => {
                  if (reasoningLevel !== level.id) e.currentTarget.style.background = 'var(--surface-hover)';
                }}
                onMouseLeave={(e) => {
                  if (reasoningLevel !== level.id) e.currentTarget.style.background = 'transparent';
                }}
                title={level.desc}
              >
                {level.label}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return null;
}
