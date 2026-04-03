import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/api/client';
import { useI18nStore } from '@/stores/i18n-store';
import {
  Search, Plus, RefreshCw, Trash2, FileText, ChevronDown, ChevronRight,
  Database, BookOpen, MessageCircle, X, Edit3, Maximize2,
  Sparkles, Zap, Clock, ArrowUpRight,
} from 'lucide-react';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { MemoryChunkModal } from '@/components/MemoryChunkModal';
import type { RagFileInfo, RagStats, RagMemoryItem } from '@ahri/shared';

interface Props {
  persona: string;
}

export function RagMemoriesSection({ persona }: Props) {
  const { locale } = useI18nStore();
  const [files, setFiles] = useState<RagFileInfo[]>([]);
  const [stats, setStats] = useState<RagStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<RagMemoryItem[] | null>(null);
  const [expandedFile, setExpandedFile] = useState<string | null>(null);
  const [fileChunks, setFileChunks] = useState<Record<string, RagMemoryItem[]>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [addTitle, setAddTitle] = useState('');
  const [addContent, setAddContent] = useState('');
  const [reindexing, setReindexing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<{ filename: string; sourceType: string } | null>(null);
  const [confirmClearDynamic, setConfirmClearDynamic] = useState(false);
  const [modalChunk, setModalChunk] = useState<RagMemoryItem | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [filesData, statsData] = await Promise.all([
        api.getRagFiles(persona),
        api.getRagStats(persona),
      ]);
      setFiles(filesData);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to load RAG data:', err);
    } finally {
      setLoading(false);
    }
  }, [persona]);

  useEffect(() => { load(); }, [load]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    try {
      setIsSearching(true);
      const result = await api.searchRagMemories(searchQuery, undefined, 20);
      setSearchResults(result.memories);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setIsSearching(false);
    }
  };

  const handleExpandFile = async (filename: string, sourceType: string) => {
    if (expandedFile === filename) { setExpandedFile(null); return; }
    setExpandedFile(filename);
    if (!fileChunks[filename]) {
      try {
        const result = await api.listMemories(sourceType);
        const chunks = result.memories.filter((m: any) => m.filename === filename);
        setFileChunks((prev) => ({ ...prev, [filename]: chunks }));
      } catch (err) {
        console.error('Failed to load chunks:', err);
      }
    }
  };

  const handleDeleteFile = async () => {
    if (!confirmDelete) return;
    try {
      await api.deleteRagFile(confirmDelete.filename, confirmDelete.sourceType);
      setConfirmDelete(null);
      setExpandedFile(null);
      load();
    } catch (err) {
      console.error('Failed to delete file:', err);
    }
  };

  const handleClearAllDynamic = async () => {
    const dynamicFiles = files.filter((f) => f.source_type === 'dynamic_knowledge');
    for (const file of dynamicFiles) {
      await api.deleteRagFile(file.filename, 'dynamic_knowledge');
    }
    setConfirmClearDynamic(false);
    load();
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      await api.reindexRag(persona);
      load();
    } catch (err) {
      console.error('Reindex failed:', err);
    } finally {
      setReindexing(false);
    }
  };

  const handleAddMemory = async () => {
    if (!addTitle.trim() || !addContent.trim()) return;
    try {
      await api.saveMemory(addTitle, addContent);
      setAddTitle('');
      setAddContent('');
      setShowAddForm(false);
      load();
    } catch (err) {
      console.error('Failed to add memory:', err);
    }
  };

  const handleDeleteChunk = async (chunkId: string) => {
    try {
      await api.deleteMemory(chunkId);
      // Refresh chunks for expanded file
      if (expandedFile) {
        setFileChunks((prev) => ({
          ...prev,
          [expandedFile]: (prev[expandedFile] || []).filter((c) => c.id !== chunkId),
        }));
      }
      load();
    } catch (err) {
      console.error('Failed to delete chunk:', err);
    }
  };

  const handleSaveChunk = async (chunkId: string, newContent: string) => {
    try {
      await api.updateMemory(chunkId, newContent);
      setModalChunk(null);
      if (expandedFile) {
        setFileChunks((prev) => ({
          ...prev,
          [expandedFile]: (prev[expandedFile] || []).map((c) =>
            c.id === chunkId ? { ...c, content: newContent } : c
          ),
        }));
      }
    } catch (err) {
      console.error('Failed to update chunk:', err);
    }
  };

  const staticFiles = files.filter((f) => f.source_type === 'static_lore');
  const dynamicFiles = files.filter((f) => f.source_type === 'dynamic_knowledge');

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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
    <div className="flex flex-col gap-5 mt-4">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {/* Search */}
        <div className="flex-1 min-w-[200px] flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
            <input
              type="text"
              className="settings-input w-full !pl-10 text-xs bg-[var(--surface-solid)] border-[var(--glass-border)]"
              placeholder={locale === 'pt' ? 'Buscar memórias...' : 'Search memories...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
          </div>
          {searchQuery && (
            <button onClick={() => { setSearchQuery(''); setSearchResults(null); }}
              className="p-1.5 rounded-lg hover:bg-white/5 text-[var(--text-tertiary)]">
              <X size={12} />
            </button>
          )}
          <button
            onClick={handleSearch}
            disabled={isSearching || !searchQuery.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold bg-[var(--persona-primary)] text-white transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap shadow-lg shadow-[var(--persona-shadow)]"
          >
            <Sparkles size={12} className={isSearching ? 'animate-pulse' : ''} />
            {locale === 'pt' ? 'Busca Semântica' : 'Semantic Search'}
          </button>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold border border-[var(--glass-border)] transition-all hover:bg-white/5 whitespace-nowrap"
            style={{ color: 'var(--persona-primary)' }}
          >
            <Plus size={12} />
            {locale === 'pt' ? 'Adicionar' : 'Add'}
          </button>

          <button
            onClick={handleReindex}
            disabled={reindexing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-semibold border border-[var(--glass-border)] transition-all hover:bg-white/5 text-[var(--text-secondary)] whitespace-nowrap"
          >
            <RefreshCw size={12} className={reindexing ? 'animate-spin' : ''} />
            Re-index
          </button>

          {/* Stats */}
          {stats && (
            <span className="text-[9px] font-mono text-[var(--text-tertiary)] bg-white/5 px-2 py-1 rounded-full whitespace-nowrap">
              {stats.total_chunks} chunks
            </span>
          )}
        </div>
      </div>

      {/* Add Memory Form */}
      {showAddForm && (
        <div className="p-4 rounded-xl border" style={{ borderColor: 'var(--glass-border)', background: 'rgba(0,0,0,0.1)' }}>
          <div className="space-y-3">
            <input
              type="text"
              className="settings-input w-full text-xs"
              placeholder={locale === 'pt' ? 'Título da memória' : 'Memory title'}
              value={addTitle}
              onChange={(e) => setAddTitle(e.target.value)}
            />
            <textarea
              className="settings-input w-full text-xs min-h-[80px] resize-none"
              placeholder={locale === 'pt' ? 'Conteúdo...' : 'Content...'}
              value={addContent}
              onChange={(e) => setAddContent(e.target.value)}
            />
            <div className="flex items-center gap-2 justify-end">
              <button onClick={() => setShowAddForm(false)}
                className="px-3 py-1.5 rounded-xl text-[10px] font-medium border transition-colors hover:bg-white/5"
                style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }}>
                {locale === 'pt' ? 'Cancelar' : 'Cancel'}
              </button>
              <button onClick={handleAddMemory}
                className="px-3 py-1.5 rounded-xl text-[10px] font-semibold text-white transition-all"
                style={{ background: 'var(--persona-primary)', boxShadow: '0 2px 8px var(--persona-shadow)' }}>
                {locale === 'pt' ? 'Salvar' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Search Results */}
      {searchResults && (
        <div className="p-5 rounded-2xl border animate-in fade-in slide-in-from-top-4 duration-300" 
             style={{ borderColor: 'var(--glass-border)', background: 'rgba(255,255,255,0.02)' }}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-[var(--persona-primary)]/20 text-[var(--persona-primary)]">
                <Zap size={14} />
              </div>
              <div>
                <h3 className="text-xs font-bold text-[var(--text-primary)]">
                  {locale === 'pt' ? 'Resultados RAG' : 'RAG Results'}
                </h3>
                <p className="text-[10px] text-[var(--text-tertiary)]">
                  {locale === 'pt' ? `${searchResults.length} correspondências encontradas` : `${searchResults.length} matches found`}
                </p>
              </div>
            </div>
            <button onClick={() => setSearchResults(null)} className="p-2 rounded-xl hover:bg-white/5 text-[var(--text-tertiary)] transition-colors">
              <X size={14} />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[500px] overflow-y-auto custom-scrollbar p-1">
            {searchResults.map((mem) => (
              <ChunkCard 
                key={mem.id} 
                chunk={mem} 
                onView={() => setModalChunk(mem)} 
                onDelete={() => handleDeleteChunk(mem.id)} 
              />
            ))}
          </div>
        </div>
      )}

      {/* Static Lore Files */}
      <FileGroup
        icon={<Database size={14} className="text-blue-400" />}
        title={locale === 'pt' ? 'Base de Dados (Fixo)' : 'Static Lore (Read-only)'}
        files={staticFiles}
        expandedFile={expandedFile}
        fileChunks={fileChunks}
        onExpandFile={handleExpandFile}
        onDeleteFile={(f) => setConfirmDelete({ filename: f.filename, sourceType: f.source_type })}
        onViewChunk={setModalChunk}
        onDeleteChunk={handleDeleteChunk}
        formatSize={formatSize}
        readOnly
      />

      {/* Dynamic Knowledge Files */}
      <FileGroup
        icon={<BookOpen size={14} className="text-emerald-400" />}
        title={locale === 'pt' ? 'Notas da IA (Aprendizado)' : 'AI Notes (Learned)'}
        files={dynamicFiles}
        expandedFile={expandedFile}
        fileChunks={fileChunks}
        onExpandFile={handleExpandFile}
        onDeleteFile={(f) => setConfirmDelete({ filename: f.filename, sourceType: f.source_type })}
        onViewChunk={setModalChunk}
        onDeleteChunk={handleDeleteChunk}
        formatSize={formatSize}
        onClearAll={dynamicFiles.length > 0 ? () => setConfirmClearDynamic(true) : undefined}
      />

      {/* Chunk Modal */}
      {modalChunk && (
        <MemoryChunkModal
          open
          chunkId={modalChunk.id}
          content={modalChunk.content}
          filename={modalChunk.filename}
          type={modalChunk.type}
          readOnly={modalChunk.type === 'static_lore'}
          onClose={() => setModalChunk(null)}
          onSave={handleSaveChunk}
        />
      )}

      {/* Confirm Dialogs */}
      <ConfirmDialog
        open={!!confirmDelete}
        title={locale === 'pt' ? 'Deletar Arquivo' : 'Delete File'}
        message={locale === 'pt'
          ? `Isso vai deletar o arquivo "${confirmDelete?.filename}" do disco E todos os chunks do ChromaDB. Esta ação não pode ser desfeita.`
          : `This will delete the file "${confirmDelete?.filename}" from disk AND all ChromaDB chunks. This cannot be undone.`}
        confirmLabel={locale === 'pt' ? 'Deletar' : 'Delete'}
        destructive
        onConfirm={handleDeleteFile}
        onCancel={() => setConfirmDelete(null)}
      />

      <ConfirmDialog
        open={confirmClearDynamic}
        title={locale === 'pt' ? 'Limpar Notas da IA' : 'Clear AI Notes'}
        message={locale === 'pt'
          ? 'Isso vai deletar TODOS os arquivos de conhecimento dinâmico e seus chunks. A IA perderá tudo que aprendeu nesta persona.'
          : 'This will delete ALL dynamic knowledge files and their chunks. The AI will lose everything it learned for this persona.'}
        confirmLabel={locale === 'pt' ? 'Limpar Tudo' : 'Clear All'}
        destructive
        onConfirm={handleClearAllDynamic}
        onCancel={() => setConfirmClearDynamic(false)}
      />
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────

function FileGroup({
  icon, title, files, expandedFile, fileChunks, onExpandFile, onDeleteFile,
  onViewChunk, onDeleteChunk, formatSize, readOnly, onClearAll,
}: {
  icon: React.ReactNode;
  title: string;
  files: RagFileInfo[];
  expandedFile: string | null;
  fileChunks: Record<string, RagMemoryItem[]>;
  onExpandFile: (filename: string, sourceType: string) => void;
  onDeleteFile: (file: RagFileInfo) => void;
  onViewChunk: (chunk: RagMemoryItem) => void;
  onDeleteChunk: (id: string) => void;
  formatSize: (bytes: number) => string;
  readOnly?: boolean;
  onClearAll?: () => void;
}) {
  const { locale } = useI18nStore();

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-xs font-semibold text-[var(--text-primary)]">{title}</span>
          <span className="text-[9px] font-mono text-[var(--text-tertiary)] bg-white/5 px-1.5 py-0.5 rounded-full">
            {files.length} {locale === 'pt' ? 'arquivos' : 'files'}
          </span>
        </div>
        {onClearAll && (
          <button onClick={onClearAll}
            className="flex items-center justify-center gap-1.5 px-2 py-1 rounded-lg text-[9px] font-medium text-red-400/60 hover:text-red-400 hover:bg-red-500/5 transition-all border border-transparent hover:border-red-500/20"
          >
            <Trash2 size={10} />
            {locale === 'pt' ? 'Limpar tudo' : 'Clear all'}
          </button>
        )}
      </div>

      {files.length === 0 ? (
        <p className="text-[10px] text-[var(--text-tertiary)] italic py-2">
          {locale === 'pt' ? 'Nenhum arquivo.' : 'No files.'}
        </p>
      ) : (
        <div className="space-y-1.5">
          {files.map((file) => {
            const isExpanded = expandedFile === file.filename;
            const chunks = fileChunks[file.filename] || [];
            return (
              <div key={file.filename}>
                <div
                  className="flex items-center gap-3 p-3 rounded-xl border cursor-pointer hover:bg-white/[0.02] transition-colors"
                  style={{ borderColor: 'var(--glass-border)' }}
                  onClick={() => onExpandFile(file.filename, file.source_type)}
                >
                  {isExpanded ? <ChevronDown size={12} className="text-[var(--text-tertiary)]" /> : <ChevronRight size={12} className="text-[var(--text-tertiary)]" />}
                  <FileText size={14} className="text-[var(--text-tertiary)] flex-shrink-0" />
                  <span className="flex-1 text-xs font-medium text-[var(--text-primary)] truncate">{file.filename}</span>
                  <span className="text-[9px] font-mono text-[var(--text-tertiary)]">{formatSize(file.size_bytes)}</span>
                  <span className="text-[9px] font-mono text-[var(--text-tertiary)] bg-white/5 px-1.5 py-0.5 rounded-full">{file.chunk_count} chunks</span>
                  <div className="flex items-center gap-1">
                    {!readOnly && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onDeleteFile(file); }}
                        className="p-1 rounded-lg hover:bg-red-500/10 text-red-400/40 hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>

                {isExpanded && chunks.length > 0 && (
                  <div className="ml-8 mt-1 space-y-1 animate-fade-in" style={{ animationDuration: '0.15s' }}>
                    {chunks.map((chunk) => (
                      <ChunkRow key={chunk.id} chunk={chunk} onView={() => onViewChunk(chunk)} onDelete={readOnly ? undefined : () => onDeleteChunk(chunk.id)} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ChunkCard({ chunk, onView, onDelete }: { chunk: RagMemoryItem; onView: () => void; onDelete?: () => void }) {
  const { locale } = useI18nStore();
  
  // Calcula score visual (distância invertida e normalizada)
  // ChromaDB distance 0.0 = exato, > 1.25 = irrelevante
  const similarity = chunk.distance !== undefined ? 
    Math.max(0, Math.min(100, Math.round((1 - (chunk.distance / 1.5)) * 100))) : 
    null;

  return (
    <div
      className="group relative flex flex-col gap-3 p-4 rounded-2xl border bg-white/[0.01] hover:bg-white/[0.03] hover:border-[var(--persona-primary)]/30 transition-all duration-300"
      style={{ borderColor: 'var(--glass-border)' }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="px-1.5 py-0.5 rounded text-[8px] font-mono font-bold bg-white/10 text-[var(--text-tertiary)] uppercase tracking-tight">
              ID: {chunk.id.slice(0, 8)}...
            </span>
            {similarity !== null && (
              <span 
                className="px-1.5 py-0.5 rounded text-[8px] font-bold"
                style={{ 
                  background: similarity > 70 ? 'var(--persona-primary)' : 'rgba(255,255,255,0.1)',
                  color: similarity > 70 ? 'white' : 'var(--text-secondary)'
                }}
              >
                {similarity}% {locale === 'pt' ? 'MATCH' : 'MATCH'}
              </span>
            )}
          </div>
          <h4 className="text-[11px] font-bold text-[var(--text-primary)] truncate">
            {chunk.filename || (locale === 'pt' ? 'Memória Direta' : 'Direct Memory')}
          </h4>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={onView} className="p-1.5 rounded-lg hover:bg-white/10 text-[var(--text-tertiary)] hover:text-white transition-colors">
            <Maximize2 size={13} />
          </button>
          {onDelete && (
            <button onClick={onDelete} className="p-1.5 rounded-lg hover:bg-red-500/10 text-red-400/40 hover:text-red-400 transition-colors">
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Content Preview */}
      <div className="relative">
        <p className="text-[10px] text-[var(--text-secondary)] line-clamp-3 leading-relaxed font-serif italic">
          "{chunk.content}"
        </p>
        <div className="absolute inset-x-0 bottom-0 h-4 bg-gradient-to-t from-transparent to-transparent pointer-events-none" />
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-white/5 mt-auto">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-[8px] text-[var(--text-tertiary)]">
            <Clock size={10} />
            {chunk.type === 'static_lore' ? (locale === 'pt' ? 'FONTE FIXA' : 'STATIC') : (locale === 'pt' ? 'APRENDIDO' : 'LEARNED')}
          </div>
          {chunk.filename && (
            <div className="flex items-center gap-1 text-[8px] text-[var(--text-tertiary)] max-w-[80px] truncate">
              <FileText size={10} />
              {chunk.filename}
            </div>
          )}
        </div>
        <ArrowUpRight size={12} className="text-[var(--text-tertiary)] group-hover:text-[var(--persona-primary)] group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
      </div>
    </div>
  );
}

function ChunkRow({ chunk, onView, onDelete }: { chunk: RagMemoryItem; onView: () => void; onDelete?: () => void }) {
  return (
    <div
      className="flex items-center gap-2 p-2 rounded-lg border group hover:bg-white/[0.02] transition-colors"
      style={{ borderColor: 'rgba(255,255,255,0.03)' }}
    >
      <p className="flex-1 text-[10px] text-[var(--text-secondary)] truncate leading-relaxed">{chunk.content.slice(0, 120)}...</p>
      <button onClick={onView} className="p-1 rounded-lg hover:bg-white/5 text-[var(--text-tertiary)] opacity-0 group-hover:opacity-100 transition-all">
        <Maximize2 size={12} />
      </button>
      {onDelete && (
        <button onClick={onDelete} className="p-1 rounded-lg hover:bg-red-500/10 text-red-400/40 opacity-0 group-hover:opacity-100 hover:!text-red-400 transition-all">
          <Trash2 size={10} />
        </button>
      )}
    </div>
  );
}
