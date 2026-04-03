import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/api/client';
import { useI18nStore } from '@/stores/i18n-store';
import { X, Trash2, RefreshCw, Target, Clock, Zap, MessageSquare, ChevronDown, ChevronRight } from 'lucide-react';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { PersonaMemoryData } from '@ahri/shared';

interface Props {
  persona: string;
}

export function PersonaMemorySection({ persona }: Props) {
  const { locale } = useI18nStore();
  const [data, setData] = useState<PersonaMemoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmClear, setConfirmClear] = useState<string | null>(null);
  const [expandedDetailIdx, setExpandedDetailIdx] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const result = await api.getPersonaMemory(persona);
      setData(result);
    } catch (err) {
      console.error('Failed to load persona memory:', err);
    } finally {
      setLoading(false);
    }
  }, [persona]);

  useEffect(() => { load(); }, [load]);

  const handleRemoveQuest = async (key: string) => {
    await api.patchPersonaMemory({ remove_quest_keys: [key] }, persona);
    load();
  };

  const handleRemoveSessionLog = async (index: number) => {
    await api.patchPersonaMemory({ remove_session_log_indices: [index] }, persona);
    load();
  };

  const handleRemoveDetailedLog = async (index: number) => {
    await api.patchPersonaMemory({ remove_session_log_detailed_indices: [index] }, persona);
    load();
  };

  const handleClearBuffer = async () => {
    await api.clearPersonaBuffer(persona);
    setConfirmClear(null);
    load();
  };

  const handleClearCategory = async () => {
    if (!confirmClear) return;
    if (confirmClear === 'buffer') {
      await handleClearBuffer();
      return;
    }
    // For other categories, use patch to clear all entries
    if (confirmClear === 'quests' && data) {
      const keys = Object.keys(data.active_quests);
      if (keys.length > 0) {
        await api.patchPersonaMemory({ remove_quest_keys: keys }, persona);
      }
    } else if (confirmClear === 'session_log' && data) {
      const indices = data.session_log.map((_, i) => i);
      if (indices.length > 0) {
        await api.patchPersonaMemory({ remove_session_log_indices: indices }, persona);
      }
    } else if (confirmClear === 'session_log_detailed' && data) {
      const indices = data.session_log_detailed.map((_, i) => i);
      if (indices.length > 0) {
        await api.patchPersonaMemory({ remove_session_log_detailed_indices: indices }, persona);
      }
    }
    setConfirmClear(null);
    load();
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-[var(--text-tertiary)]">
        <RefreshCw size={14} className="animate-spin" />
        <span className="text-xs">{locale === 'pt' ? 'Carregando...' : 'Loading...'}</span>
      </div>
    );
  }

  // If API call failed, show error state
  if (!data) {
    return (
      <p className="text-xs text-[var(--text-tertiary)] py-4 text-center">
        {locale === 'pt' ? 'Erro ao carregar memória da persona. Verifique se o backend está rodando.' : 'Failed to load persona memory. Check if backend is running.'}
      </p>
    );
  }

  const quests = Object.entries(data.active_quests || {});
  const sessionLogs = data.session_log || [];
  const detailedLogs = data.session_log_detailed || [];
  const buffer = data.last_session_buffer || [];

  return (
    <div className="flex flex-col gap-6 mt-4">
      {/* Active Quests */}
      <SubSection
        icon={<Target size={14} className="text-amber-400" />}
        title={locale === 'pt' ? 'Quests Ativas' : 'Active Quests'}
        count={quests.length}
        onClear={quests.length > 0 ? () => setConfirmClear('quests') : undefined}
        locale={locale}
      >
        {quests.length === 0 ? (
          <EmptyState locale={locale} />
        ) : (
          <div className="space-y-2">
            {quests.map(([key, quest]) => {
              // Handle V2 format (string/array values) and V3 format ({status, current_stage})
              const isObject = quest && typeof quest === 'object' && !Array.isArray(quest);
              const questValue = typeof quest === 'string'
                ? quest
                : Array.isArray(quest)
                  ? quest.join(', ')
                  : null;

              return (
                <div
                  key={key}
                  className="flex items-center justify-between p-3 rounded-xl border"
                  style={{ borderColor: 'var(--glass-border)', background: 'rgba(0,0,0,0.1)' }}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-[var(--text-primary)] truncate">{key}</p>
                    {questValue ? (
                      <p className="text-[10px] text-[var(--text-secondary)] mt-1 line-clamp-2">{questValue}</p>
                    ) : isObject ? (
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full ${
                          (quest as any)?.status === 'Completed' ? 'text-emerald-400 bg-emerald-500/10' :
                          (quest as any)?.status === 'Paused' ? 'text-amber-400 bg-amber-500/10' :
                          'text-blue-400 bg-blue-500/10'
                        }`}>
                          {(quest as any)?.status || 'In Progress'}
                        </span>
                        {(quest as any)?.current_stage && (
                          <span className="text-[9px] text-[var(--text-tertiary)]">{(quest as any).current_stage}</span>
                        )}
                      </div>
                    ) : null}
                  </div>
                  <button
                    onClick={() => handleRemoveQuest(key)}
                    className="p-1.5 rounded-lg hover:bg-red-500/10 text-red-400/60 hover:text-red-400 transition-colors flex-shrink-0"
                  >
                    <X size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </SubSection>

      {/* Session Log */}
      <SubSection
        icon={<Clock size={14} className="text-emerald-400" />}
        title={locale === 'pt' ? 'Log de Sessões' : 'Session Log'}
        count={sessionLogs.length}
        onClear={sessionLogs.length > 0 ? () => setConfirmClear('session_log') : undefined}
        locale={locale}
      >
        {sessionLogs.length === 0 ? (
          <EmptyState locale={locale} />
        ) : (
          <div className="space-y-1.5 max-h-[300px] overflow-y-auto custom-scrollbar pr-1">
            {sessionLogs.slice(-20).map((log, idx) => {
              const realIdx = sessionLogs.length > 20 ? sessionLogs.length - 20 + idx : idx;
              return (
                <div key={idx} className="flex items-start gap-2 group">
                  <p className="flex-1 text-[10px] leading-relaxed text-[var(--text-secondary)] py-1">{log}</p>
                  <button
                    onClick={() => handleRemoveSessionLog(realIdx)}
                    className="p-1 rounded-lg hover:bg-red-500/10 text-red-400/0 group-hover:text-red-400/60 hover:!text-red-400 transition-colors flex-shrink-0"
                  >
                    <X size={10} />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </SubSection>

      {/* Session Log Detailed */}
      {detailedLogs.length > 0 && (
        <SubSection
          icon={<MessageSquare size={14} className="text-blue-400" />}
          title={locale === 'pt' ? 'Sessões Detalhadas' : 'Detailed Sessions'}
          count={detailedLogs.length}
          onClear={() => setConfirmClear('session_log_detailed')}
          locale={locale}
        >
          <div className="space-y-2 max-h-[400px] overflow-y-auto custom-scrollbar pr-1">
            {detailedLogs.slice(-15).map((entry, idx) => {
              const realIdx = detailedLogs.length > 15 ? detailedLogs.length - 15 + idx : idx;
              const isExpanded = expandedDetailIdx === realIdx;

              return (
                <div
                  key={idx}
                  className="rounded-xl border transition-all"
                  style={{ borderColor: 'var(--glass-border)', background: 'rgba(0,0,0,0.05)' }}
                >
                  <div className="flex items-center gap-2 p-3">
                    <button
                      onClick={() => setExpandedDetailIdx(isExpanded ? null : realIdx)}
                      className="text-[var(--text-tertiary)]"
                    >
                      {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    </button>
                    <p className="flex-1 text-[10px] text-[var(--text-secondary)] truncate">
                      {(entry as any)?.summary || (entry as any)?.date || JSON.stringify(entry).slice(0, 80)}
                    </p>
                    <button
                      onClick={() => handleRemoveDetailedLog(realIdx)}
                      className="p-1 rounded-lg hover:bg-red-500/10 text-red-400/40 hover:text-red-400 transition-colors flex-shrink-0"
                    >
                      <X size={10} />
                    </button>
                  </div>
                  {isExpanded && (
                    <div className="px-8 pb-3 animate-fade-in" style={{ animationDuration: '0.15s' }}>
                      <pre className="text-[9px] text-[var(--text-tertiary)] font-mono whitespace-pre-wrap break-words">
                        {JSON.stringify(entry, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </SubSection>
      )}

      {/* Last Session Buffer */}
      <SubSection
        icon={<Zap size={14} className="text-pink-400" />}
        title={locale === 'pt' ? 'Buffer da Última Sessão' : 'Last Session Buffer'}
        count={buffer.length}
        onClear={buffer.length > 0 ? () => setConfirmClear('buffer') : undefined}
        locale={locale}
      >
        {buffer.length === 0 ? (
          <EmptyState locale={locale} message={
            locale === 'pt'
              ? 'Nenhum contexto de sessão anterior. O buffer será preenchido automaticamente.'
              : 'No previous session context. The buffer will be populated automatically.'
          } />
        ) : (
          <div className="space-y-1.5 max-h-[200px] overflow-y-auto custom-scrollbar pr-1">
            {buffer.map((item, idx) => (
              <p key={idx} className="text-[10px] leading-relaxed text-[var(--text-secondary)] py-0.5">{item}</p>
            ))}
          </div>
        )}
      </SubSection>

      {/* Confirm Dialog */}
      <ConfirmDialog
        open={!!confirmClear}
        title={locale === 'pt' ? 'Limpar Categoria' : 'Clear Category'}
        message={locale === 'pt'
          ? `Tem certeza que deseja limpar todos os dados de "${confirmClear}"? Esta ação não pode ser desfeita.`
          : `Are you sure you want to clear all data from "${confirmClear}"? This action cannot be undone.`}
        confirmLabel={locale === 'pt' ? 'Limpar Tudo' : 'Clear All'}
        destructive
        onConfirm={handleClearCategory}
        onCancel={() => setConfirmClear(null)}
      />
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────

function SubSection({
  icon,
  title,
  count,
  onClear,
  locale,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  onClear?: () => void;
  locale: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs font-semibold text-[var(--text-primary)]">{title}</span>
          <span className="text-[9px] font-mono text-[var(--text-tertiary)] bg-white/5 px-1.5 py-0.5 rounded-full">{count}</span>
        </div>
        {onClear && count > 0 && (
          <button
            onClick={onClear}
            className="flex items-center justify-center gap-1.5 px-2 py-1 rounded-lg text-[9px] font-medium text-red-400/60 hover:text-red-400 hover:bg-red-500/5 transition-all border border-transparent hover:border-red-500/20"
          >
            <Trash2 size={10} />
            {locale === 'pt' ? 'Limpar tudo' : 'Clear all'}
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function EmptyState({ locale, message }: { locale: string; message?: string }) {
  return (
    <p className="text-[10px] text-[var(--text-tertiary)] italic py-2">
      {message || (locale === 'pt' ? 'Nenhum dado ainda.' : 'No data yet.')}
    </p>
  );
}
