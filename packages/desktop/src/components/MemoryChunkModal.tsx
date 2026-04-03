import React, { useState, useEffect } from 'react';
import { X, Save, StickyNote, Edit3 } from 'lucide-react';

interface MemoryChunkModalProps {
  open: boolean;
  chunkId: string;
  content: string;
  filename: string;
  type: string;
  readOnly?: boolean;
  onClose: () => void;
  onSave?: (id: string, newContent: string) => void;
}

export function MemoryChunkModal({
  open,
  chunkId,
  content,
  filename,
  type,
  readOnly = false,
  onClose,
  onSave,
}: MemoryChunkModalProps) {
  const [editContent, setEditContent] = useState(content);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    setEditContent(content);
    setIsEditing(false);
  }, [content, chunkId]);

  if (!open) return null;

  const typeLabel =
    type === 'static_lore' ? 'Base de Dados (Fixo)' :
    type === 'dynamic_knowledge' ? 'Notas da IA' :
    type === 'chat_history' ? 'Histórico de Chat' : type;

  const typeColor =
    type === 'static_lore' ? 'text-blue-400 bg-blue-500/10' :
    type === 'dynamic_knowledge' ? 'text-emerald-400 bg-emerald-500/10' :
    'text-amber-400 bg-amber-500/10';

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center animate-fade-in" style={{ animationDuration: '0.15s' }}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      <div
        className="relative z-10 w-full max-w-2xl max-h-[80vh] flex flex-col rounded-2xl border shadow-2xl"
        style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-solid)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--glass-border)' }}>
          <div className="flex items-center gap-3 min-w-0">
            {isEditing ? (
              <Edit3 size={16} className="text-amber-400 flex-shrink-0" />
            ) : (
              <StickyNote size={16} className="text-blue-400 flex-shrink-0" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{filename}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full ${typeColor}`}>
                  {typeLabel}
                </span>
                <span className="text-[9px] text-[var(--text-tertiary)] font-mono truncate">{chunkId}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {!readOnly && !isEditing && (
              <button
                onClick={() => setIsEditing(true)}
                className="p-2 rounded-lg hover:bg-white/5 transition-colors"
                style={{ color: 'var(--text-secondary)' }}
                title="Editar"
              >
                <Edit3 size={14} />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-white/5 transition-colors"
              style={{ color: 'var(--text-secondary)' }}
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          {isEditing ? (
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-full min-h-[300px] p-3 rounded-xl border text-xs font-mono leading-relaxed resize-none focus:outline-none focus:ring-1"
              style={{
                borderColor: 'var(--glass-border)',
                background: 'rgba(0,0,0,0.2)',
                color: 'var(--text-primary)',
              }}
              autoFocus
            />
          ) : (
            <pre className="text-xs leading-relaxed whitespace-pre-wrap break-words text-[var(--text-secondary)] font-mono">
              {content}
            </pre>
          )}
        </div>

        {/* Footer */}
        {isEditing && (
          <div className="flex items-center justify-end gap-3 p-4 border-t" style={{ borderColor: 'var(--glass-border)' }}>
            <button
              onClick={() => { setIsEditing(false); setEditContent(content); }}
              className="px-4 py-2 rounded-xl text-xs font-medium border transition-colors hover:bg-white/5"
              style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }}
            >
              Cancelar
            </button>
            <button
              onClick={() => {
                onSave?.(chunkId, editContent);
                setIsEditing(false);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white shadow-lg transition-all"
              style={{ background: 'var(--persona-primary)', boxShadow: '0 4px 12px var(--persona-shadow)' }}
            >
              <Save size={12} />
              Salvar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
