import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/api/client';
import { useI18nStore } from '@/stores/i18n-store';
import { RefreshCw, Trash2, Edit3, Plus, Upload, X, Save } from 'lucide-react';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { SocialGraphPlatform } from '@ahri/shared';

const PLATFORM_CONFIG: Record<string, { icon: string; color: string }> = {
  instagram: { icon: '📸', color: 'text-pink-400' },
  twitter: { icon: '𝕏', color: 'text-blue-400' },
  youtube: { icon: '▶', color: 'text-red-400' },
  spotify: { icon: '🎵', color: 'text-emerald-400' },
  discord: { icon: '💬', color: 'text-indigo-400' },
  github: { icon: '🐙', color: 'text-gray-400' },
};

export function SocialGraphSection() {
  const { locale } = useI18nStore();
  const [platforms, setPlatforms] = useState<SocialGraphPlatform[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingPlatform, setEditingPlatform] = useState<string | null>(null);
  const [editJson, setEditJson] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [importJson, setImportJson] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newPlatformName, setNewPlatformName] = useState('');
  const [newPlatformData, setNewPlatformData] = useState('{\n  \n}');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getSocialGraph();
      setPlatforms(data);
    } catch (err) {
      console.error('Failed to load social graph:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleEdit = (platform: SocialGraphPlatform) => {
    setEditingPlatform(platform.platform);
    setEditJson(JSON.stringify(platform.data, null, 2));
  };

  const handleSaveEdit = async () => {
    if (!editingPlatform) return;
    try {
      const data = JSON.parse(editJson);
      await api.upsertSocialGraphPlatform(editingPlatform, data);
      setEditingPlatform(null);
      load();
    } catch (err) {
      console.error('Failed to save:', err);
      alert(locale === 'pt' ? 'JSON inválido' : 'Invalid JSON');
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await api.deleteSocialGraphPlatform(confirmDelete);
      setConfirmDelete(null);
      load();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  const handleImport = async () => {
    try {
      const data = JSON.parse(importJson);
      await api.importSocialGraph(data);
      setShowImport(false);
      setImportJson('');
      load();
    } catch (err) {
      console.error('Import failed:', err);
      alert(locale === 'pt' ? 'JSON inválido' : 'Invalid JSON');
    }
  };

  const handleAddPlatform = async () => {
    if (!newPlatformName.trim()) return;
    try {
      const data = JSON.parse(newPlatformData);
      await api.upsertSocialGraphPlatform(newPlatformName.toLowerCase().trim(), data);
      setShowAddForm(false);
      setNewPlatformName('');
      setNewPlatformData('{\n  \n}');
      load();
    } catch (err) {
      console.error('Failed to add:', err);
      alert(locale === 'pt' ? 'JSON inválido' : 'Invalid JSON');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-[var(--text-tertiary)]">
        <RefreshCw size={14} className="animate-spin" />
        <span className="text-xs">{locale === 'pt' ? 'Carregando...' : 'Loading...'}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 mt-4">
      {/* Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold border border-[var(--glass-border)] transition-all hover:bg-white/5 whitespace-nowrap"
          style={{ color: 'var(--persona-primary)' }}
        >
          <Plus size={12} />
          {locale === 'pt' ? 'Adicionar' : 'Add Platform'}
        </button>
        <button
          onClick={() => setShowImport(!showImport)}
          className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold border border-[var(--glass-border)] transition-all hover:bg-white/5 text-[var(--text-secondary)] whitespace-nowrap"
        >
          <Upload size={12} />
          {locale === 'pt' ? 'Importar JSON' : 'Import JSON'}
        </button>
      </div>

      {/* Import Form */}
      {showImport && (
        <div className="p-4 rounded-xl border" style={{ borderColor: 'var(--glass-border)', background: 'rgba(0,0,0,0.1)' }}>
          <p className="text-[10px] text-[var(--text-tertiary)] mb-2">
            {locale === 'pt'
              ? 'Cole o JSON do social graph (formato: {"instagram": {...}, "twitter": {...}})'
              : 'Paste social graph JSON (format: {"instagram": {...}, "twitter": {...}})'}
          </p>
          <textarea
            className="settings-input w-full text-xs font-mono min-h-[120px] resize-none"
            value={importJson}
            onChange={(e) => setImportJson(e.target.value)}
            placeholder='{"instagram": {"interests": [...], "personality": "..."}, ...}'
          />
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setShowImport(false)}
              className="px-3 py-1.5 rounded-xl text-[10px] font-medium border transition-colors hover:bg-white/5"
              style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }}>
              {locale === 'pt' ? 'Cancelar' : 'Cancel'}
            </button>
            <button onClick={handleImport}
              className="px-3 py-1.5 rounded-xl text-[10px] font-semibold text-white transition-all"
              style={{ background: 'var(--persona-primary)' }}>
              {locale === 'pt' ? 'Importar' : 'Import'}
            </button>
          </div>
        </div>
      )}

      {/* Add Platform Form */}
      {showAddForm && (
        <div className="p-4 rounded-xl border" style={{ borderColor: 'var(--glass-border)', background: 'rgba(0,0,0,0.1)' }}>
          <input
            type="text"
            className="settings-input w-full text-xs mb-3"
            placeholder={locale === 'pt' ? 'Nome da plataforma (ex: instagram)' : 'Platform name (e.g., instagram)'}
            value={newPlatformName}
            onChange={(e) => setNewPlatformName(e.target.value)}
          />
          <textarea
            className="settings-input w-full text-xs font-mono min-h-[80px] resize-none"
            value={newPlatformData}
            onChange={(e) => setNewPlatformData(e.target.value)}
          />
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setShowAddForm(false)}
              className="px-3 py-1.5 rounded-xl text-[10px] font-medium border transition-colors hover:bg-white/5"
              style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }}>
              {locale === 'pt' ? 'Cancelar' : 'Cancel'}
            </button>
            <button onClick={handleAddPlatform}
              className="px-3 py-1.5 rounded-xl text-[10px] font-semibold text-white transition-all"
              style={{ background: 'var(--persona-primary)' }}>
              {locale === 'pt' ? 'Adicionar' : 'Add'}
            </button>
          </div>
        </div>
      )}

      {/* Platform Cards */}
      {platforms.length === 0 ? (
        <p className="text-[10px] text-[var(--text-tertiary)] italic py-4 text-center">
          {locale === 'pt'
            ? 'Nenhum perfil social importado. Use "Importar JSON" para adicionar dados de redes sociais.'
            : 'No social profiles imported. Use "Import JSON" to add social media data.'}
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {platforms.map((platform) => {
            const config = PLATFORM_CONFIG[platform.platform] || { icon: '🔗', color: 'text-gray-400' };
            const isEditing = editingPlatform === platform.platform;

            return (
              <div
                key={platform.platform}
                className="p-4 rounded-xl border border-[var(--glass-border)] transition-all hover:border-[var(--persona-primary)]/30"
                style={{ background: 'var(--surface-solid)' }}
              >
                {/* Platform Header */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-base">{config.icon}</span>
                    <span className={`text-xs font-bold uppercase tracking-wider ${config.color}`}>{platform.platform}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {isEditing ? (
                      <>
                        <button onClick={() => setEditingPlatform(null)}
                          className="p-1.5 rounded-lg hover:bg-white/5 text-[var(--text-tertiary)]">
                          <X size={12} />
                        </button>
                        <button onClick={handleSaveEdit}
                          className="p-1.5 rounded-lg hover:bg-emerald-500/10 text-emerald-400">
                          <Save size={12} />
                        </button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => handleEdit(platform)}
                          className="p-1.5 rounded-lg hover:bg-white/5 text-[var(--text-tertiary)]">
                          <Edit3 size={12} />
                        </button>
                        <button onClick={() => setConfirmDelete(platform.platform)}
                          className="p-1.5 rounded-lg hover:bg-red-500/10 text-red-400/60 hover:text-red-400">
                          <Trash2 size={12} />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Platform Data */}
                {isEditing ? (
                  <textarea
                    className="settings-input w-full text-[10px] font-mono min-h-[150px] resize-none"
                    value={editJson}
                    onChange={(e) => setEditJson(e.target.value)}
                    autoFocus
                  />
                ) : (
                  <div className="space-y-1.5 max-h-[200px] overflow-y-auto custom-scrollbar">
                    {Object.entries(platform.data).map(([key, value]) => (
                      <div key={key} className="flex gap-2">
                        <span className="text-[9px] font-bold uppercase text-[var(--text-tertiary)] flex-shrink-0 w-24 truncate">{key}</span>
                        <span className="text-[10px] text-[var(--text-secondary)] break-words">
                          {typeof value === 'string' ? value : Array.isArray(value) ? value.join(', ') : JSON.stringify(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Confirm Delete */}
      <ConfirmDialog
        open={!!confirmDelete}
        title={locale === 'pt' ? 'Deletar Plataforma' : 'Delete Platform'}
        message={locale === 'pt'
          ? `Deletar todos os dados de "${confirmDelete}"? Esta ação não pode ser desfeita.`
          : `Delete all data for "${confirmDelete}"? This cannot be undone.`}
        confirmLabel={locale === 'pt' ? 'Deletar' : 'Delete'}
        destructive
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
