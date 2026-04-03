/**
 * MemoryFactCard — renders a single SemanticMemoryTier fact.
 *
 * Shows: content, importance badge, last_reinforced date, tags, flagged warning.
 * Optional delete button when onDelete is provided.
 */
import React from 'react';
import { Trash2, AlertTriangle } from 'lucide-react';
import type { SemanticMemoryItem } from '@ahri/shared/types/memory';

interface MemoryFactCardProps {
  item: SemanticMemoryItem;
  onDelete?: (id: number) => void;
}

function importanceColor(imp: number): string {
  if (imp >= 8) return '#ef4444';  // red
  if (imp >= 6) return '#f59e0b';  // amber
  if (imp >= 4) return '#3b82f6';  // blue
  return '#6b7280';               // gray
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' });
  } catch {
    return '';
  }
}

export function MemoryFactCard({ item, onDelete }: MemoryFactCardProps) {
  return (
    <div
      className="rounded-xl px-3 py-2.5 text-sm flex flex-col gap-1.5 transition-all"
      style={{
        background: 'var(--glass-bg)',
        border: `1px solid ${item.is_flagged ? '#f59e0b' : 'var(--glass-border)'}`,
      }}
    >
      {/* Conflict warning */}
      {item.is_flagged && (
        <div className="flex items-center gap-1.5 text-xs" style={{ color: '#f59e0b' }}>
          <AlertTriangle size={12} />
          <span>{item.conflict_note || 'Conflito com dado anterior'}</span>
        </div>
      )}

      {/* Content row */}
      <div className="flex items-start justify-between gap-2">
        <p className="flex-1 text-xs leading-relaxed" style={{ color: 'var(--text-primary)' }}>
          {item.content}
        </p>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {/* Importance badge */}
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded-full"
            style={{ background: importanceColor(item.importance) + '22', color: importanceColor(item.importance) }}
          >
            {item.importance}
          </span>
          {/* Delete button */}
          {onDelete && (
            <button
              onClick={() => onDelete(item.id)}
              className="p-1 rounded-lg opacity-40 hover:opacity-100 transition-opacity"
              style={{ color: 'var(--text-tertiary)' }}
              title="Remover fato"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Footer: tags + date */}
      <div className="flex items-center gap-2 flex-wrap">
        {item.tags.map((tag) => (
          <span
            key={tag}
            className="text-[10px] px-1.5 py-0.5 rounded-full"
            style={{ background: 'var(--persona-primary)22', color: 'var(--persona-primary)' }}
          >
            {tag}
          </span>
        ))}
        {item.last_reinforced && (
          <span className="text-[10px] ml-auto" style={{ color: 'var(--text-tertiary)' }}>
            {formatDate(item.last_reinforced)}
          </span>
        )}
      </div>
    </div>
  );
}
