import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/api/client';
import { useI18nStore } from '@/stores/i18n-store';
import { RefreshCw, Trash2, ChevronDown, ChevronRight, Star, Calendar, Filter, X, Search } from 'lucide-react';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import type { EpisodicMemoryEntry } from '@ahri/shared';

interface Props {
  persona: string;
}

export function EpisodicMemorySection({ persona }: Props) {
  const { locale } = useI18nStore();
  const [episodes, setEpisodes] = useState<EpisodicMemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Filters
  const [showFilters, setShowFilters] = useState(false);
  const [minImportance, setMinImportance] = useState(1);
  const [searchText, setSearchText] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getEpisodes({
        persona,
        min_importance: minImportance > 1 ? minImportance : undefined,
        limit: 100,
      });
      setEpisodes(data);
    } catch (err) {
      console.error('Failed to load episodes:', err);
    } finally {
      setLoading(false);
    }
  }, [persona, minImportance]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async () => {
    if (confirmDelete === null) return;
    try {
      await api.deleteEpisode(confirmDelete);
      setConfirmDelete(null);
      load();
    } catch (err) {
      console.error('Failed to delete episode:', err);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    try {
      await api.bulkDeleteEpisodes(Array.from(selectedIds));
      setSelectedIds(new Set());
      setConfirmBulkDelete(false);
      load();
    } catch (err) {
      console.error('Failed to bulk delete:', err);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Client-side text filter
  const filtered = searchText.trim()
    ? episodes.filter(
        (ep) =>
          ep.summary.toLowerCase().includes(searchText.toLowerCase()) ||
          ep.topics.some((t) => t.toLowerCase().includes(searchText.toLowerCase()))
      )
    : episodes;

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
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[180px]">
          <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
          <input
            type="text"
            className="settings-input w-full !pl-10 text-xs bg-[var(--surface-solid)] border-[var(--glass-border)]"
            placeholder={locale === 'pt' ? 'Filtrar por texto...' : 'Filter by text...'}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
          {searchText && (
            <button onClick={() => { setSearchText(''); }}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-lg hover:bg-white/5 text-[var(--text-tertiary)]">
              <X size={10} />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold border transition-all hover:bg-white/5 whitespace-nowrap ${showFilters ? 'border-[var(--persona-primary)] bg-[var(--persona-primary)]/5' : 'border-[var(--glass-border)]'}`}
            style={{ color: showFilters ? 'var(--persona-primary)' : 'var(--text-secondary)' }}
          >
            <Filter size={12} />
            {locale === 'pt' ? 'Filtros' : 'Filters'}
          </button>

          {selectedIds.size > 0 && (
            <button
              onClick={() => setConfirmBulkDelete(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold bg-red-500/10 text-red-400 border border-red-500/20 transition-all hover:bg-red-500/20 whitespace-nowrap"
            >
              <Trash2 size={12} />
              {locale === 'pt' ? `Deletar ${selectedIds.size}` : `Delete ${selectedIds.size}`}
            </button>
          )}

          <span className="text-[9px] font-mono text-[var(--text-tertiary)] bg-white/5 px-2 py-1 rounded-full whitespace-nowrap">
            {filtered.length} {locale === 'pt' ? 'episódios' : 'episodes'}
          </span>
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="flex items-center gap-4 p-3 rounded-xl border animate-fade-in"
          style={{ borderColor: 'var(--glass-border)', background: 'rgba(0,0,0,0.1)', animationDuration: '0.15s' }}>
          <div className="flex items-center gap-2">
            <Star size={12} className="text-amber-400" />
            <span className="text-[10px] text-[var(--text-tertiary)]">
              {locale === 'pt' ? 'Importância mín:' : 'Min importance:'}
            </span>
            <input
              type="range"
              min={1}
              max={10}
              value={minImportance}
              onChange={(e) => setMinImportance(Number(e.target.value))}
              className="w-24 accent-amber-400"
            />
            <span className="text-[10px] font-mono text-amber-400">{minImportance}</span>
          </div>
        </div>
      )}

      {/* Episodes List */}
      {filtered.length === 0 ? (
        <p className="text-[10px] text-[var(--text-tertiary)] italic py-4 text-center">
          {locale === 'pt' ? 'Nenhuma memória episódica encontrada.' : 'No episodic memories found.'}
        </p>
      ) : (
        <div className="space-y-2">
          {filtered.map((ep) => {
            const isExpanded = expandedId === ep.id;
            const isSelected = selectedIds.has(ep.id);

            return (
              <div
                key={ep.id}
                className={`rounded-xl border transition-all ${isSelected ? 'border-red-500/30' : ''}`}
                style={{ borderColor: isSelected ? undefined : 'var(--glass-border)', background: 'rgba(0,0,0,0.05)' }}
              >
                {/* Episode Header */}
                <div className="flex items-center gap-3 p-3">
                  {/* Checkbox */}
                  <button
                    onClick={() => toggleSelect(ep.id)}
                    className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-all ${
                      isSelected ? 'bg-red-500 border-red-500' : 'border-[var(--glass-border)] hover:border-[var(--text-tertiary)]'
                    }`}
                  >
                    {isSelected && <span className="text-white text-[8px]">✓</span>}
                  </button>

                  {/* Expand toggle */}
                  <button onClick={() => setExpandedId(isExpanded ? null : ep.id)} className="text-[var(--text-tertiary)]">
                    {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  </button>

                  {/* Content */}
                  <div className="flex-1 min-w-0 cursor-pointer" onClick={() => setExpandedId(isExpanded ? null : ep.id)}>
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* Date */}
                      <span className="text-[9px] font-mono text-[var(--text-tertiary)] flex items-center gap-1">
                        <Calendar size={10} />
                        {ep.date.split(' ')[0]}
                      </span>

                      {/* Topics */}
                      {ep.topics.map((topic) => (
                        <span key={topic} className="text-[8px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-white/5 text-[var(--text-secondary)]">
                          {topic}
                        </span>
                      ))}

                      {/* Emotional tone */}
                      {ep.emotional_tone && (
                        <span className="text-[8px] italic text-[var(--text-tertiary)]">{ep.emotional_tone}</span>
                      )}
                    </div>

                    <p className="text-[10px] text-[var(--text-secondary)] mt-1 truncate">{ep.summary}</p>
                  </div>

                  {/* Importance stars */}
                  <div className="hidden sm:flex items-center gap-0.5 flex-shrink-0 ml-auto">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star key={i} size={8} className={i < Math.ceil(ep.importance / 2) ? 'text-amber-400 fill-amber-400' : 'text-white/10'} />
                    ))}
                  </div>

                  {/* Importance Number (Mobile) */}
                  <div className="flex sm:hidden items-center gap-1 flex-shrink-0 ml-auto bg-amber-500/10 px-1.5 py-0.5 rounded-md">
                    <Star size={8} className="text-amber-400 fill-amber-400" />
                    <span className="text-[9px] font-bold text-amber-400">{ep.importance}</span>
                  </div>

                  {/* Delete */}
                  <button
                    onClick={() => setConfirmDelete(ep.id)}
                    className="p-1 rounded-lg hover:bg-red-500/10 text-red-400/40 hover:text-red-400 transition-colors flex-shrink-0"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div className="px-12 pb-3 animate-fade-in" style={{ animationDuration: '0.15s' }}>
                    <p className="text-[10px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">{ep.summary}</p>
                    {ep.outcomes && ep.outcomes.length > 0 && (
                      <div className="mt-3">
                        <span className="text-[9px] font-bold uppercase text-[var(--text-tertiary)]">
                          {locale === 'pt' ? 'Resultados:' : 'Outcomes:'}
                        </span>
                        <ul className="mt-1 space-y-0.5">
                          {ep.outcomes.map((outcome, i) => (
                            <li key={i} className="text-[10px] text-[var(--text-secondary)] flex items-start gap-1.5">
                              <span className="text-emerald-400 mt-0.5">•</span>
                              {outcome}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Confirm Dialogs */}
      <ConfirmDialog
        open={confirmDelete !== null}
        title={locale === 'pt' ? 'Deletar Episódio' : 'Delete Episode'}
        message={locale === 'pt'
          ? 'Tem certeza que deseja deletar esta memória episódica?'
          : 'Are you sure you want to delete this episodic memory?'}
        confirmLabel={locale === 'pt' ? 'Deletar' : 'Delete'}
        destructive
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
      />

      <ConfirmDialog
        open={confirmBulkDelete}
        title={locale === 'pt' ? 'Deletar Selecionados' : 'Delete Selected'}
        message={locale === 'pt'
          ? `Deletar ${selectedIds.size} episódios selecionados? Esta ação não pode ser desfeita.`
          : `Delete ${selectedIds.size} selected episodes? This cannot be undone.`}
        confirmLabel={locale === 'pt' ? `Deletar ${selectedIds.size}` : `Delete ${selectedIds.size}`}
        destructive
        onConfirm={handleBulkDelete}
        onCancel={() => setConfirmBulkDelete(false)}
      />
    </div>
  );
}
