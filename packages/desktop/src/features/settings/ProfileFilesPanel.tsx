import React, { useState, useEffect } from 'react';
import { useT, useI18nStore } from '@/stores/i18n-store';
import { FileText, ExternalLink, RefreshCw, Save, AlertCircle } from 'lucide-react';

interface ProfileFlattened {
  name: string;
  archetype: string;
  learning_style: string;
  bio: string;
  personality: string[];
  occupation: string;
  interests: string[];
  tech_stack: string[];
  music: string[];
  dislikes: string[];
  foods: string[];
  languages: Record<string, string>;
}

interface ProfileFilesPanelProps {
  config: ProfileFlattened;
  onSync: (newConfig: ProfileFlattened) => void;
}

/**
 * Panel for advanced profile editing.
 * Exports the DB profile to a JSON file, opens it, and allows syncing back.
 */
export function ProfileFilesPanel({ config, onSync }: ProfileFilesPanelProps) {
  const t = useT();
  const locale = useI18nStore((s) => s.locale);
  const [filePath, setFilePath] = useState<string>('');
  const [isExporting, setIsExporting] = useState(false);
  const [lastSync, setLastSync] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const JSON_FILENAME = 'user_profile.json';

  useEffect(() => {
    const resolvePath = async () => {
      if (window.ahri?.agent) {
        try {
          const paths = await window.ahri.agent.getPaths();
          // We'll store it in the backend's data folder if possible, or just app data
          const backendPath = (paths as any).backend;
          if (backendPath) {
            setFilePath(`${backendPath}/data/${JSON_FILENAME}`);
          } else {
            setFilePath(JSON_FILENAME); // Fallback to current dir
          }
        } catch (e) {
          console.error('Failed to resolve paths:', e);
          setFilePath(JSON_FILENAME);
        }
      }
    };
    resolvePath();
  }, []);

  const handleExportAndOpen = async () => {
    if (!window.ahri?.agent) return;
    setIsExporting(true);
    setError(null);

    try {
      const jsonContent = JSON.stringify(config, null, 2);
      await window.ahri.agent.writeFile(filePath, jsonContent);
      await window.ahri.agent.openFile(filePath);
      setLastSync(new Date());
    } catch (err: any) {
      console.error('Export failed:', err);
      setError(locale === 'pt' ? 'Falha ao exportar arquivo.' : 'Failed to export file.');
    } finally {
      setIsExporting(false);
    }
  };

  const handleSyncFromFile = async () => {
    if (!window.ahri?.agent) return;
    setError(null);

    try {
      const content = await window.ahri.agent.readFile(filePath);
      const parsed = JSON.parse(content) as ProfileFlattened;
      
      // Basic validation
      if (!parsed.name && parsed.name !== '') {
        throw new Error('Invalid profile format');
      }

      onSync(parsed);
      setLastSync(new Date());
      alert(locale === 'pt' ? 'Perfil sincronizado com sucesso!' : 'Profile synced successfully!');
    } catch (err: any) {
      console.error('Sync failed:', err);
      setError(locale === 'pt' ? 'Falha ao ler ou processar arquivo JSON.' : 'Failed to read or parse JSON file.');
    }
  };

  return (
    <div className="settings-section-card p-4 rounded-xl border border-[var(--glass-border)] bg-[var(--surface-solid)] mt-4">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400">
          <FileText size={20} />
        </div>
        <div>
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            {locale === 'pt' ? 'Editor de Perfil Avançado' : 'Advanced Profile Editor'}
          </h4>
          <p className="text-[10px] text-[var(--text-tertiary)]">
            {locale === 'pt' 
              ? 'Exporte seu perfil para JSON, edite no VS Code/Notepad e sincronize de volta.' 
              : 'Export your profile to JSON, edit in VS Code/Notepad and sync back.'}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleExportAndOpen}
          disabled={isExporting}
          className="settings-action-btn flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--button-bg)] border border-[var(--glass-border)] text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-all"
        >
          <ExternalLink size={14} />
          {isExporting 
            ? (locale === 'pt' ? 'Exportando...' : 'Exporting...') 
            : (locale === 'pt' ? 'Exportar e Abrir no Editor' : 'Export and Open in Editor')}
        </button>

        <button
          onClick={handleSyncFromFile}
          className="settings-action-btn flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-500/15 border border-purple-500/30 text-xs font-medium text-purple-300 hover:bg-purple-500/20 transition-all"
        >
          <RefreshCw size={14} />
          {locale === 'pt' ? 'Sincronizar do Arquivo' : 'Sync from File'}
        </button>
      </div>

      {lastSync && (
        <p className="text-[10px] mt-3 opacity-60 flex items-center gap-1 text-[var(--text-tertiary)]">
          <Save size={10} />
          {locale === 'pt' ? 'Última sincronização:' : 'Last sync:'} {lastSync.toLocaleTimeString()}
        </p>
      )}

      {error && (
        <div className="mt-3 p-2 rounded bg-red-500/10 border border-red-500/20 flex items-center gap-2 text-[10px] text-red-400">
          <AlertCircle size={12} />
          {error}
        </div>
      )}
    </div>
  );
}
