/**
 * DirectorySelector - Popup for selecting a project directory.
 *
 * Shows up to 3 recent directories + "Browse..." button.
 * Uses Electron IPC for native file dialog and persistence.
 */

import { useState, useEffect, useRef } from 'react';
import { useAgentModeStore } from '@/stores/agent-mode-store';

interface DirectorySelectorProps {
  theme: { primary: string; secondary: string; shadow: string };
}

export function DirectorySelector({ theme }: DirectorySelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedDirectory = useAgentModeStore((s) => s.selectedDirectory);
  const recentDirectories = useAgentModeStore((s) => s.recentDirectories);
  const setSelectedDirectory = useAgentModeStore((s) => s.setSelectedDirectory);
  const loadRecentDirectories = useAgentModeStore((s) => s.loadRecentDirectories);

  // Load recent dirs on mount
  useEffect(() => {
    loadRecentDirectories();
  }, [loadRecentDirectories]);

  // Close popup on outside click
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

  const handleBrowse = async () => {
    if (!window.ahri?.agent?.selectDirectory) return;
    const dir = await window.ahri.agent.selectDirectory();
    if (dir) {
      setSelectedDirectory(dir);
      setIsOpen(false);
    }
  };

  const handleSelectRecent = (dir: string) => {
    setSelectedDirectory(dir);
    setIsOpen(false);
  };

  // Extract folder name from full path
  const folderName = (fullPath: string) => {
    const parts = fullPath.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || fullPath;
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-all duration-300 hover:bg-[var(--surface-hover)] border border-transparent"
        style={{
          background: selectedDirectory
            ? `color-mix(in srgb, ${theme.primary} 15%, transparent)`
            : 'transparent',
          color: selectedDirectory ? theme.primary : 'var(--text-secondary)',
        }}
        title={selectedDirectory || 'Selecionar diretório'}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
        {selectedDirectory && (
          <>
            <span className="max-w-[80px] truncate">{folderName(selectedDirectory)}</span>
            <div
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setSelectedDirectory(null);
              }}
              className="ml-0.5 p-0.5 rounded-full hover:bg-[color-mix(in_srgb,var(--error)_20%,transparent)] transition-colors hover:text-[var(--error)]"
              title="Remover diretório"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </div>
          </>
        )}
      </button>

      {isOpen && (
        <div
          className="absolute bottom-full left-0 mb-2 w-64 rounded-lg overflow-hidden z-50 animate-fade-in-up"
          style={{
            background: 'var(--surface-solid)',
            border: '1px solid var(--glass-border)',
            boxShadow: `0 8px 32px rgba(0,0,0,0.3), 0 0 12px ${theme.shadow}`,
          }}
        >
          {/* Header */}
          <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--glass-border)' }}>
            <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
              Diretório do Projeto
            </span>
          </div>

          {/* Recent directories */}
          {recentDirectories.length > 0 && (
            <div className="py-1">
              {recentDirectories.map((dir) => (
                <button
                  key={dir}
                  onClick={() => handleSelectRecent(dir)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-[var(--surface-hover)]"
                  title={dir}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
                    style={{ color: dir === selectedDirectory ? theme.primary : 'var(--text-tertiary)', flexShrink: 0 }}>
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                  </svg>
                  <span className="truncate" style={{ color: dir === selectedDirectory ? theme.primary : 'var(--text-secondary)' }}>
                    {folderName(dir)}
                  </span>
                  {dir === selectedDirectory && (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={theme.primary} strokeWidth="3" className="ml-auto flex-shrink-0">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* Divider if has recent dirs */}
          {recentDirectories.length > 0 && (
            <div style={{ borderTop: '1px solid var(--glass-border)' }} />
          )}

          {/* Browse button */}
          <button
            onClick={handleBrowse}
            className="w-full flex items-center gap-2 px-3 py-2.5 text-left text-xs transition-colors hover:bg-[var(--surface-hover)]"
            style={{ color: 'var(--text-secondary)' }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="flex-shrink-0">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <span>Navegar...</span>
          </button>
        </div>
      )}
    </div>
  );
}
