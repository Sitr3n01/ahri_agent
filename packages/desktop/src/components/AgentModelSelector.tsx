/**
 * AgentModelSelector - Popup for selecting agent mode LLM model.
 *
 * Two options: Qwen 3 8B (local/Ollama) or Gemini 3.1 Flash Lite (API).
 * Includes reasoning level controls:
 * - Gemini: off/low/medium/high thinking budget
 * - Qwen: thinking on/off toggle
 * Selection persists in localStorage via agent-mode-store.
 */

import { useState, useEffect, useRef } from 'react';
import { useAgentModeStore } from '@/stores/agent-mode-store';
import type { AgentModelId, GeminiReasoningLevel } from '@ahri/shared';

interface AgentModelSelectorProps {
  theme: { primary: string; secondary: string; shadow: string };
}

const MODELS: { id: AgentModelId; name: string; shortName: string; provider: string; color: string }[] = [
  {
    id: 'gemini-flash-lite',
    name: 'Gemini 3.1 Flash Lite',
    shortName: 'Flash Lite',
    provider: 'API',
    color: '#4285F4',
  },
  {
    id: 'qwen-3.5-local',
    name: 'Qwen 3.5 9b',
    shortName: 'Qwen 3.5',
    provider: 'Ollama',
    color: '#F97316',
  },
];

const REASONING_LEVELS: { id: GeminiReasoningLevel; label: string; desc: string }[] = [
  { id: 'off', label: 'Off', desc: 'Sem raciocínio' },
  { id: 'low', label: 'Low', desc: '~1K tokens' },
  { id: 'medium', label: 'Med', desc: '~8K tokens' },
  { id: 'high', label: 'High', desc: '~24K tokens' },
];

export function AgentModelSelector({ theme }: AgentModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedModel = useAgentModeStore((s) => s.selectedModel);
  const setSelectedModel = useAgentModeStore((s) => s.setSelectedModel);
  const reasoningLevel = useAgentModeStore((s) => s.reasoningLevel);
  const setReasoningLevel = useAgentModeStore((s) => s.setReasoningLevel);
  const enableThinking = useAgentModeStore((s) => s.enableThinking);
  const setEnableThinking = useAgentModeStore((s) => s.setEnableThinking);

  const activeModel = MODELS.find((m) => m.id === selectedModel) || MODELS[0];

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [isOpen]);

  const handleSelect = (modelId: AgentModelId) => {
    setSelectedModel(modelId);
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1 px-2 py-1 rounded-full transition-all duration-300 hover:bg-white/5 active:scale-95 border border-transparent"
        style={{
          background: 'transparent',
          cursor: 'pointer',
          fontSize: '0.7rem',
          fontFamily: 'var(--font-sans)',
          fontWeight: 500,
          color: 'var(--text-secondary)',
        }}
      >
        <span>{activeModel.shortName}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
          className={`opacity-40 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Popup */}
      {isOpen && (
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
              Modelo do Agente
            </span>
          </div>

          {/* Model options */}
          <div className="py-1">
            {MODELS.map((model) => {
              const isActive = model.id === selectedModel;
              return (
                <div key={model.id}>
                  <button
                    onClick={() => handleSelect(model.id)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-[var(--surface-hover)]"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium" style={{ color: isActive ? model.color : 'var(--text-primary)' }}>
                        {model.name}
                      </div>
                      <div className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                        {model.provider}
                      </div>
                    </div>
                    {isActive && (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={model.color} strokeWidth="3" className="flex-shrink-0">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </button>

                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
