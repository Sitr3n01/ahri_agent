import { useState, useRef, useEffect } from 'react';
import { usePersonaTheme } from '@/hooks/usePersonaTheme';
import { usePersonaStore } from '@/stores/persona-store';
import { useThemeStore } from '@/stores/theme-store';
import { useUIStore } from '@/stores/ui-store';
import { useEngineStore } from '@/stores/engine-store';
import { useT } from '@/stores/i18n-store';
import type { AppMode } from '@/App';

interface ToolbarProps {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  previousMode?: AppMode;
}

export function Toolbar({ mode, setMode, previousMode = 'chat' }: ToolbarProps) {
  const theme = usePersonaTheme();
  const appTheme = useThemeStore((s) => s.theme);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const t = useT();
  const [menuOpen, setMenuOpen] = useState(false);
  const [hwAccelEnabled, setHwAccelEnabled] = useState(true);
  const menuRef = useRef<HTMLDivElement>(null);

  // Load hardware acceleration state from Electron settings
  useEffect(() => {
    window.ahri?.settings?.getHwAccel().then(setHwAccelEnabled).catch(() => {});
  }, []);

  const modes: { key: AppMode; label: string }[] = [
    { key: 'chat', label: t('nav.chat') },
  ];

  // Close menu on click outside
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as HTMLElement)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  const iconColor = 'var(--text-tertiary)';
  const iconHoverColor = 'var(--text-primary)';

  return (
    <div className="app-toolbar">
      {/* LEFT: Hamburger menu + Settings */}
      <div className="absolute left-3 flex items-center gap-0.5 app-toolbar-no-drag">
        {/* Hamburger menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-1.5 rounded-md transition-colors duration-150"
            style={{
              color: menuOpen ? theme.primary : iconColor,
              background: menuOpen
                ? `color-mix(in srgb, ${theme.primary} 10%, transparent)`
                : 'transparent',
            }}
            title="Menu"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>

          {/* Dropdown menu — simple solid, no glassmorphism */}
          {menuOpen && (
            <div
              className="absolute top-full left-0 mt-1 z-50 w-[180px] rounded-lg py-1 animate-fade-in"
              style={{
                background: 'var(--surface-solid)',
                border: '1px solid var(--glass-border)',
                boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
              }}
            >
              {/* About — shows GPU info */}
              <button
                onClick={async () => {
                  setMenuOpen(false);
                  if (window.ahri?.settings) {
                    try {
                      const info = await window.ahri.settings.getGpuInfo();
                      const gpu = (info.gpuInfo as Record<string, unknown>);
                      const gpuDevices = (gpu?.gpuDevice as Array<Record<string, unknown>>) || [];
                      const gpuName = gpuDevices.length > 0
                        ? `${gpuDevices[0].vendorId} - ${gpuDevices[0].deviceId}`
                        : 'N/A';
                      const features = Object.entries(info.featureStatus)
                        .filter(([, v]) => v !== 'unavailable')
                        .map(([k, v]) => `  ${k}: ${v}`)
                        .join('\n');
                      alert(`Ahri V3\n\nGPU: ${gpuName}\nAceleração: ${info.hardwareAcceleration ? 'Ativada' : 'Desativada'}\n\nFeatures:\n${features}`);
                    } catch {
                      alert('Ahri V3\n\nNão foi possível obter informações da GPU.');
                    }
                  }
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors toolbar-menu-item"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--info)' }}>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="16" x2="12" y2="12" />
                  <line x1="12" y1="8" x2="12.01" y2="8" />
                </svg>
                <span>Sobre Ahri V3</span>
              </button>

              {/* Hardware Acceleration toggle */}
              <button
                onClick={async () => {
                  const newValue = !hwAccelEnabled;
                  await window.ahri?.settings?.setHwAccel(newValue);
                  const restart = confirm(
                    newValue
                      ? 'Aceleração de hardware ativada. Reiniciar agora para aplicar?'
                      : 'Aceleração de hardware desativada. Reiniciar agora para aplicar?'
                  );
                  if (restart) {
                    await window.ahri?.settings?.restartApp();
                  }
                  setHwAccelEnabled(newValue);
                  setMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors toolbar-menu-item"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
                  style={{ color: hwAccelEnabled ? 'var(--success)' : 'var(--text-tertiary)' }}>
                  <rect x="4" y="4" width="16" height="16" rx="2" />
                  <rect x="8" y="8" width="8" height="8" rx="1" />
                  <line x1="2" y1="9" x2="4" y2="9" /><line x1="2" y1="15" x2="4" y2="15" />
                  <line x1="20" y1="9" x2="22" y2="9" /><line x1="20" y1="15" x2="22" y2="15" />
                  <line x1="9" y1="2" x2="9" y2="4" /><line x1="15" y1="2" x2="15" y2="4" />
                  <line x1="9" y1="20" x2="9" y2="22" /><line x1="15" y1="20" x2="15" y2="22" />
                </svg>
                <span>GPU: {hwAccelEnabled ? 'Ativada' : 'Desativada'}</span>
                <div className={`w-1.5 h-1.5 rounded-full ml-auto ${hwAccelEnabled ? 'bg-green-400' : 'bg-red-400'}`} />
              </button>

              {/* Reload */}
              <button
                onClick={() => { window.location.reload(); setMenuOpen(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors toolbar-menu-item"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--success)' }}>
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                <span>Recarregar</span>
              </button>
              <div className="mx-2 my-1" style={{ height: '1px', background: 'var(--glass-border)' }} />

              {/* Exit */}
              <button
                onClick={() => { window.close(); setMenuOpen(false); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors toolbar-menu-item"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--error)' }}>
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
                <span>Sair</span>
              </button>
            </div>
          )}
        </div>

        {/* Sidebar toggle (hidden in settings mode) */}
        {mode !== 'settings' && (
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-md transition-colors duration-150"
            style={{
              color: sidebarOpen ? iconColor : theme.primary,
              background: !sidebarOpen
                ? `color-mix(in srgb, ${theme.primary} 10%, transparent)`
                : 'transparent',
            }}
            title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <line x1="9" y1="3" x2="9" y2="21" />
            </svg>
          </button>
        )}
      </div>

      {/* CENTER: Mode selector pill */}
      <div className="app-toolbar-no-drag relative flex items-center p-0.5 rounded-lg"
        style={{
          background: 'var(--surface-hover)',
          minWidth: '130px', /* Fix width for stable slider */
          border: '1px solid var(--border-subtle)',
        }}
      >
        {/* Animated Slide Background */}
        <div
          className="absolute inset-y-0.5 rounded-md transition-transform duration-300 cubic-bezier(0.16, 1, 0.3, 1)"
          style={{
            width: 'calc(100% - 4px)',
            left: '2px',
            background: `linear-gradient(135deg, ${theme.primary}, ${theme.secondary})`,
            boxShadow: `0 0 10px ${theme.shadow}`,
            zIndex: 0,
          }}
        />
        {modes.map((m) => {
          const isEngineRunning = m.key === 'chat' && useEngineStore.getState().isRunning;
          return (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className="relative z-10 flex-1 py-1 text-xs font-medium rounded-md transition-all duration-200 text-center flex items-center justify-center gap-1.5 cursor-pointer"
              style={{
                color: mode === m.key ? 'rgba(0,0,0,0.85)' : 'var(--text-secondary)',
              }}
            >
              {m.label}
              {isEngineRunning && (
                <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#3b82f6' }} />
              )}
            </button>
          );
        })}
      </div>

      {/* RIGHT: empty — reserved for native window controls (titleBarOverlay) */}
    </div>
  );
}
