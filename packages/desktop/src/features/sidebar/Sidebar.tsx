import { useState } from 'react';
import { usePersonaStore } from '@/stores/persona-store';
import { useChatStore } from '@/stores/chat-store';
import { useAgentStore } from '@/stores/agent-store';
import { useAgentModeStore } from '@/stores/agent-mode-store';
import { useAuthStore } from '@/stores/auth-store';
import { useThemeStore } from '@/stores/theme-store';
import { useT } from '@/stores/i18n-store';
import { getPersonaTheme } from '@ahri/shared';
import { PersonaDrawer } from '@/features/personas/PersonaDrawer';
import { TPMQuotaMeter } from '@/components/TPMQuotaMeter';
import type { AppMode } from '@/App';

interface SidebarProps {
  mode: AppMode;
}

export function Sidebar({ mode }: SidebarProps) {
  const activePersona = usePersonaStore((s) => s.activePersona);
  const personas = usePersonaStore((s) => s.personas);
  const syncPersonaByMusic = usePersonaStore((s) => s.syncPersonaByMusic);
  const isSyncingSpotify = usePersonaStore((s) => s.isSyncingSpotify);
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const loadSession = useChatStore((s) => s.loadSession);
  const createSession = useChatStore((s) => s.createSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const renameSession = useChatStore((s) => s.renameSession);
  const toggleAgentPanel = useAgentStore((s) => s.togglePanel);
  const agentTasks = useAgentStore((s) => s.tasks);
  const logout = useAuthStore((s) => s.logout);
  const appTheme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  const backgroundOpacity = usePersonaStore((s) => s.backgroundOpacity);
  const setBackgroundOpacity = usePersonaStore((s) => s.setBackgroundOpacity);

  const [sessionsSectionOpen, setSessionsSectionOpen] = useState(true);
  const [sliderOpen, setSliderOpen] = useState(false);
  const [editingSessionId, setEditingSessionId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  // Agent mode store (must be called unconditionally for React hooks rules)
  const executions = useAgentModeStore((s) => s.executions);
  const activeExecution = useAgentModeStore((s) => s.activeExecution);
  const setActiveExecution = useAgentModeStore((s) => s.setActiveExecution);
  const deleteExecution = useAgentModeStore((s) => s.deleteExecution);
  const clearHistory = useAgentModeStore((s) => s.clearHistory);
  const tpmStatus = useAgentModeStore((s) => s.tpmStatus);

  const pendingTasks = agentTasks.filter((t) => t.status === 'pending').length;
  const theme = getPersonaTheme(activePersona);
  const t = useT();

  // Token estimate: count chars / 4 (rough GPT-style estimate)
  const messages = useChatStore((s) => s.messages);
  const tokenEstimate = Math.round(
    messages.reduce((sum, m) => sum + (m.content?.length ?? 0), 0) / 4
  );
  const TOKEN_LIMIT = 32000;
  const tokenPct = Math.min((tokenEstimate / TOKEN_LIMIT) * 100, 100);

  const handleSyncPersona = async () => {
    const result = await syncPersonaByMusic();
    if (result) {
      setSyncFeedback(result);
      setTimeout(() => setSyncFeedback(null), 3000);
    } else {
      setSyncFeedback('unchanged');
      setTimeout(() => setSyncFeedback(null), 2000);
    }
  };

  // ─── CHAT MODE SIDEBAR ──────────────────────────────────────
  if (mode === 'chat') {
    return (
      <aside className="chat-sidebar h-full flex flex-col">
        {/* Logo */}
        <div className="px-4 pt-3 pb-2">
          <div className="flex items-center gap-2">
            <span
              className="text-lg font-bold tracking-tight persona-logo-text"
              style={{
                '--logo-primary': theme.primary,
                '--logo-secondary': theme.secondary,
              } as React.CSSProperties}
            >
              {personas.find(p => p.name === activePersona)?.display_name || 'Ahri'}
            </span>
          </div>
        </div>

        {/* ── Persona Drawer ── */}
        <div className="px-3 pb-3">
          <PersonaDrawer />

          {/* Spotify sync row */}
          <div className="flex items-center mt-2 px-0.5">
            <button
              onClick={handleSyncPersona}
              disabled={isSyncingSpotify}
              className="chat-spotify-sync-btn"
              title="Sync persona with Spotify music"
            >
              {isSyncingSpotify ? (
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="animate-spin">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </svg>
              ) : (
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 18V5l12-2v13" />
                  <circle cx="6" cy="18" r="3" />
                  <circle cx="18" cy="16" r="3" />
                </svg>
              )}
              <span>{t('nav.sync')}</span>
            </button>
          </div>

          {/* Sync feedback */}
          {syncFeedback && (
            <div className="text-[10px] text-center mt-1 animate-fade-in" style={{ color: theme.primary }}>
              {syncFeedback === 'unchanged' ? t('nav.sync_unchanged') : `→ ${syncFeedback}`}
            </div>
          )}
        </div>

        {/* Sessions */}
        <div className="flex-1 overflow-y-auto">
          {/* New Chat Button */}
          <div className="p-2">
            <button
              onClick={() => createSession()}
              className="chat-new-session-btn"
              style={{ '--btn-color': theme.primary } as React.CSSProperties}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>{t('nav.new_chat')}</span>
            </button>
          </div>

          {/* Session List */}
          <div className="px-2 pb-2 space-y-0.5">
            {sessions.slice(0, 15).map((s, index) => (
              <div
                key={s.id}
                className={`group chat-session-item ${s.id === activeSessionId ? 'active' : ''}`}
                style={{
                  animation: 'fadeInUp 0.4s ease-out forwards',
                  animationDelay: `${index * 0.04}s`,
                  opacity: 0,
                  ...(s.id === activeSessionId && {
                    '--session-color': theme.primary,
                    '--session-shadow': theme.shadow,
                  })
                } as React.CSSProperties}
                onClick={() => loadSession(s.id)}
              >
                {editingSessionId === s.id ? (
                  <input
                    type="text"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onBlur={() => {
                      if (editingTitle.trim()) renameSession(s.id, editingTitle.trim());
                      setEditingSessionId(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        if (editingTitle.trim()) renameSession(s.id, editingTitle.trim());
                        setEditingSessionId(null);
                      }
                      if (e.key === 'Escape') setEditingSessionId(null);
                    }}
                    autoFocus
                    className="w-full bg-transparent text-xs outline-none py-0.5"
                    style={{ color: 'var(--text-primary)' }}
                  />
                ) : (
                  <div className="flex items-center justify-between gap-1">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs truncate font-medium" style={{ color: 'var(--text-primary)' }}>
                        {s.title}
                      </p>
                      <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                        {s.message_count} msgs
                      </p>
                    </div>
                    <div className="opacity-0 group-hover:opacity-100 flex gap-0.5 flex-shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingSessionId(s.id);
                          setEditingTitle(s.title);
                        }}
                        className="p-1 chat-session-action transition-all duration-300"
                        style={{ color: 'var(--text-tertiary)' }}
                        title={t('common.rename')}
                      >
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteSession(s.id);
                        }}
                        className="p-1 chat-session-action transition-all duration-300"
                        style={{ color: 'var(--text-tertiary)' }}
                        title={t('common.delete')}
                      >
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            {sessions.length > 15 && (
              <p className="text-[10px] text-center py-1" style={{ color: 'var(--text-tertiary)' }}>
                +{sessions.length - 15} more
              </p>
            )}
          </div>
        </div>

        {/* Bottom bar — controls */}
        <div className="px-3 py-2 flex-shrink-0 relative" style={{ borderTop: '1px solid var(--glass-border)' }}>
          {/* Slider popover — floats upward */}
          <div
            className="absolute left-2 right-2 rounded-lg px-3 py-2"
            style={{
              bottom: '100%',
              marginBottom: '4px',
              background: 'var(--sidebar-bg)',
              border: '1px solid var(--glass-border)',
              backdropFilter: 'blur(30px)',
              boxShadow: '0 -4px 16px rgba(0,0,0,0.2)',
              transformOrigin: 'bottom center',
              transition: 'all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
              opacity: sliderOpen ? 1 : 0,
              transform: sliderOpen ? 'scale(1) translateY(0)' : 'scale(0.9) translateY(8px)',
              pointerEvents: sliderOpen ? 'auto' : 'none',
              zIndex: 50,
            }}
          >
              <div className="flex items-center gap-2">
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  value={backgroundOpacity}
                  onChange={(e) => setBackgroundOpacity(Number(e.target.value))}
                  className="chat-opacity-slider flex-1"
                  style={{
                    '--slider-color': theme.primary,
                    '--slider-percent': `${backgroundOpacity}%`,
                  } as React.CSSProperties}
                />
                <span
                  className="text-[10px] font-mono w-7 text-right flex-shrink-0"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  {backgroundOpacity}%
                </span>
              </div>
            </div>
          <div className="flex items-center gap-1">
            {/* Slider toggle */}
            <button
              onClick={() => setSliderOpen(!sliderOpen)}
              className="chat-sidebar-icon-btn"
              title="Background opacity"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                style={{ transform: sliderOpen ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
                <path d="M9 18l6-6-6-6" />
              </svg>
            </button>
            {/* Theme toggle */}
            <button
              onClick={toggleTheme}
              className="chat-sidebar-icon-btn"
              title={appTheme === 'dark' ? t('common.theme_light') : t('common.theme_dark')}
            >
              {appTheme === 'dark' ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              )}
            </button>
            {/* Logout */}
            <button onClick={logout} className="chat-sidebar-icon-btn" title={t('nav.logout')}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        </div>
      </aside>
    );
  }

  // ─── AGENT MODE SIDEBAR ──────────────────────────────────────
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#22c55e';
      case 'failed': return '#ef4444';
      case 'running': return '#3b82f6';
      default: return '#eab308';
    }
  };

  const timeAgo = (date: string) => {
    const diff = Date.now() - new Date(date).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'agora';
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    return `${Math.floor(hrs / 24)}d`;
  };

  return (
    <aside className="chat-sidebar h-full flex flex-col">
      {/* Header */}
      <div className="px-4 pt-3 pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className="text-lg font-bold tracking-tight persona-logo-text"
              style={{
                '--logo-primary': theme.primary,
                '--logo-secondary': theme.secondary,
              } as React.CSSProperties}
            >
              {personas.find(p => p.name === activePersona)?.display_name || 'Ahri'}
            </span>
          </div>
          <button
            onClick={toggleAgentPanel}
            className="chat-sidebar-icon-btn relative"
            title="Agent Tasks"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M9 11h6M9 15h6" />
            </svg>
            {pendingTasks > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full"
                style={{ background: 'var(--error)' }}
              />
            )}
          </button>
        </div>
      </div>

      {/* TPM Quota Meter */}
      <div className="px-3 pb-3">
        <TPMQuotaMeter
          tokensUsed={tpmStatus.tokensUsed}
          tokensRemaining={tpmStatus.tokensRemaining}
          limitTPM={tpmStatus.limitTPM}
          utilizationPercent={tpmStatus.utilizationPercent}
        />
      </div>

      {/* Execution History */}
      <div className="flex-1 overflow-y-auto">
        {/* New Task Button */}
        <div className="p-2">
          <button
            onClick={() => setActiveExecution(null)}
            className="chat-new-session-btn"
            style={{ '--btn-color': theme.primary } as React.CSSProperties}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>Nova Tarefa</span>
          </button>
        </div>

        {/* Execution List */}
        <div className="px-2 pb-2 space-y-0.5">
          {executions.length === 0 && (
            <p className="text-[10px] text-center py-4" style={{ color: 'var(--text-tertiary)' }}>
              Nenhuma execução ainda
            </p>
          )}
          {executions.slice(0, 20).map((exec, index) => (
            <div
              key={exec.id}
              className={`group agent-execution-item ${exec.id === activeExecution?.id ? 'active' : ''}`}
              style={{
                animation: 'fadeInUp 0.4s ease-out forwards',
                animationDelay: `${index * 0.04}s`,
                opacity: 0,
              } as React.CSSProperties}
              onClick={() => setActiveExecution(exec)}
            >
              <div className="flex items-center justify-between gap-1">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <div
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${exec.status === 'running' ? 'animate-pulse' : ''}`}
                    style={{ background: getStatusColor(exec.status) }}
                  />
                  <p className="text-xs truncate font-medium" style={{ color: 'var(--text-primary)' }}>
                    {exec.goal}
                  </p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                    {exec.created_at ? timeAgo(exec.created_at) : ''}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteExecution(exec.id); }}
                    className="p-0.5 chat-session-action opacity-0 group-hover:opacity-100 transition-all duration-300"
                    style={{ color: 'var(--text-tertiary)' }}
                    title={t('common.delete')}
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              </div>
              {exec.worker_tasks && exec.worker_tasks.length > 0 && (
                <div className="flex items-center gap-1 mt-1 ml-4">
                  <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                    {exec.worker_tasks.length} workers
                  </span>
                </div>
              )}
            </div>
          ))}
          {executions.length > 20 && (
            <p className="text-[10px] text-center py-1" style={{ color: 'var(--text-tertiary)' }}>
              +{executions.length - 20} mais
            </p>
          )}
        </div>
      </div>

      {/* Clear History */}
      {executions.length > 0 && (
        <div className="px-3 py-1">
          <button
            onClick={clearHistory}
            className="w-full text-[10px] py-1.5 rounded-lg transition-all duration-300"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)'; e.currentTarget.style.background = 'rgba(239, 68, 68, 0.08)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.background = 'transparent'; }}
          >
            Limpar Histórico
          </button>
        </div>
      )}

      {/* Bottom bar — controls */}
      <div className="px-3 py-2 flex-shrink-0" style={{ borderTop: '1px solid var(--glass-border)' }}>
        <div className="flex items-center gap-1">
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="chat-sidebar-icon-btn"
            title={appTheme === 'dark' ? t('common.theme_light') : t('common.theme_dark')}
          >
            {appTheme === 'dark' ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
          {/* Logout */}
          <button onClick={logout} className="chat-sidebar-icon-btn" title={t('nav.logout')}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}
