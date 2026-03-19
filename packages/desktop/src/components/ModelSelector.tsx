import { useState, useEffect } from 'react';
import { useChatStore } from '@/stores/chat-store';

// Fallback models (used if API doesn't return models)
const FALLBACK_ENGINES = [
  { id: 'PRO', display_name: 'Gemini Pro', provider: 'google_apikey' as const, color: '#8b5cf6' },
  { id: 'GOOGLE', display_name: 'Gemma 27B', provider: 'google_apikey' as const, color: '#3b82f6' },
  { id: 'DEEPSEEK', display_name: 'DeepSeek R1', provider: 'openrouter' as const, color: '#22c55e' },
  { id: 'LOCAL', display_name: 'Ollama Local', provider: 'ollama' as const, color: '#f59e0b' },
];

function shortLabel(displayName: string): string {
  if (displayName.startsWith('Gemini ')) return displayName.replace('Gemini ', '');
  if (displayName.startsWith('Gemma ')) return displayName;
  return displayName.split(' ')[0];
}

interface ModelSelectorProps {
  compact?: boolean;
}

export function ModelSelector({ compact = false }: ModelSelectorProps) {
  const model = useChatStore((s) => s.model);
  const setModel = useChatStore((s) => s.setModel);
  const availableModels = useChatStore((s) => s.availableModels);
  const fetchAvailableModels = useChatStore((s) => s.fetchAvailableModels);
  const [open, setOpen] = useState(false);

  const engines = availableModels.length > 0 ? availableModels : FALLBACK_ENGINES;
  const currentEngine = engines.find((e) => e.id === model) || engines[0];

  useEffect(() => {
    fetchAvailableModels();
  }, [fetchAvailableModels]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('.model-selector-container')) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // ── Compact variant (for meta bar below composer) ──
  if (compact) {
    return (
      <div className="relative model-selector-container">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full transition-all duration-300 hover:bg-white/5 active:scale-95 border border-transparent"
          style={{
            background: 'transparent',
            cursor: 'pointer',
            fontSize: '0.75rem',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            color: 'var(--text-secondary)',
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{ background: currentEngine.color }}
          />
          <span>{shortLabel(currentEngine.display_name)}</span>
          <svg
            width="8"
            height="8"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            className={`opacity-40 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {open && (
          <div
            className="absolute left-0 bottom-full mb-2 rounded-lg overflow-hidden z-50 min-w-[170px] animate-fade-in"
            style={{
              background: 'var(--surface-solid)',
              border: '1px solid var(--glass-border)',
              backdropFilter: 'none',
              boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
            }}
          >
            {engines.map((engine) => (
              <button
                key={engine.id}
                onClick={() => {
                  setModel(engine.id);
                  setOpen(false);
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors duration-100"
                style={{
                  color: engine.id === model ? 'var(--text-primary)' : 'var(--text-secondary)',
                  background: engine.id === model ? 'var(--surface-hover)' : 'transparent',
                }}
                onMouseEnter={(e) => {
                  if (engine.id !== model) e.currentTarget.style.background = 'var(--surface-hover)';
                }}
                onMouseLeave={(e) => {
                  if (engine.id !== model) e.currentTarget.style.background = 'transparent';
                }}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ background: engine.color }}
                />
                <span className="flex-1 text-left">{engine.display_name}</span>
                {engine.id === model && (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── Default variant (full-width, for sidebar or standalone use) ──
  return (
    <div className="relative model-selector-container">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors duration-150"
        style={{
          background: 'var(--button-bg)',
          border: '1px solid var(--glass-border)',
          color: 'var(--text-primary)',
        }}
      >
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: currentEngine.color }}
        />
        <span className="flex-1 text-left font-mono truncate">
          {shortLabel(currentEngine.display_name)}
        </span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          className={`opacity-40 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute left-0 right-0 top-full mt-1 rounded-lg overflow-hidden z-50"
          style={{
            background: 'var(--sidebar-bg)',
            border: '1px solid var(--glass-border)',
            backdropFilter: 'blur(30px)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }}
        >
          {engines.map((engine) => (
            <button
              key={engine.id}
              onClick={() => {
                setModel(engine.id);
                setOpen(false);
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors duration-100"
              style={{
                color: engine.id === model ? 'var(--text-primary)' : 'var(--text-secondary)',
                background: engine.id === model ? 'var(--surface-hover)' : 'transparent',
              }}
              onMouseEnter={(e) => {
                if (engine.id !== model) e.currentTarget.style.background = 'var(--surface-hover)';
              }}
              onMouseLeave={(e) => {
                if (engine.id !== model) e.currentTarget.style.background = 'transparent';
              }}
            >
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ background: engine.color }}
              />
              <span className="flex-1 text-left">{engine.display_name}</span>
              {engine.id === model && (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
