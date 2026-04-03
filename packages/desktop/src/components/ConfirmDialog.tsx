import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirmar',
  cancelLabel = 'Cancelar',
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center animate-fade-in" style={{ animationDuration: '0.15s' }}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onCancel} />

      {/* Dialog */}
      <div
        className="relative z-10 w-full max-w-md p-6 rounded-2xl border shadow-2xl"
        style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-solid)' }}
      >
        <div className="flex items-start gap-4">
          {destructive && (
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
            <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{message}</p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-xl text-xs font-medium border transition-colors hover:bg-white/5"
            style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }}
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 rounded-xl text-xs font-semibold text-white transition-all ${
              destructive
                ? 'bg-red-500 hover:bg-red-600 shadow-lg shadow-red-500/20'
                : 'shadow-lg'
            }`}
            style={
              destructive
                ? undefined
                : { background: 'var(--persona-primary)', boxShadow: '0 4px 12px var(--persona-shadow)' }
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
