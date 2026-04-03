import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useEngineStore } from '@/stores/engine-store';
import { usePersonaStore } from '@/stores/persona-store';
import { useThemeStore } from '@/stores/theme-store';
import { usePersonaTheme } from '@/hooks/usePersonaTheme';
import type { EngineEvent } from '@ahri/shared';

import { DirectorySelector } from '@/components/DirectorySelector';
import { AgentModelSelector } from '@/components/AgentModelSelector';
import { AgentReasoningSelector } from '@/components/AgentReasoningSelector';
import { AgentPermissionSelector } from '@/components/AgentPermissionSelector';
import { useAgentModeStore } from '@/stores/agent-mode-store';

type Attachment = { type: 'image' | 'video' | 'pdf'; data: string; name: string; preview?: string };

// Utility to parse latest relevant ticker message
function getTickerMessage(events: EngineEvent[]): string {
  if (events.length === 0) return 'Iniciando engine...';
  
  // iterate backwards to find the last meaningful actionable event
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === 'tool_use_start') {
      return `Executando ${e.data.tool_name}...`;
    }
    if (e.type === 'tool_use_end') {
      return `Concluiu ${e.data.tool_name}.`;
    }
    if (e.type === 'agent_spawn') {
      return `Novo Sub-agente: ${e.data.agent_type}`;
    }
    if (e.type === 'iteration_start') {
      return `Analisando próximo passo...`;
    }
    if (e.type === 'tool_permission_ask') {
      return `Aguardando permissão humana...`;
    }
    if (e.type === 'final_response') {
      return `Tarefa concluída.`;
    }
  }
  return 'Processando...';
}

export function AgentModeView() {
  const themeMode = useThemeStore((s) => s.theme);
  const isLight = themeMode === 'light';
  const theme = usePersonaTheme();

  const [goal, setGoal] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // V4 Engine Store
  const startExecution = useEngineStore(s => s.startExecution);
  const cancelExecution = useEngineStore(s => s.cancelExecution);
  const sendResponse = useEngineStore(s => s.sendResponse);
  const currentExecution = useEngineStore(s => s.currentExecution);
  const isRunning = useEngineStore(s => s.isRunning);
  const events = useEngineStore(s => s.events);

  // We read the selected model from V3 store because AgentModelSelector saves it there
  const selectedModel = useAgentModeStore(s => s.selectedModel);
  const permissionMode = useAgentModeStore(s => s.permissionMode);
  const selectedDirectory = useAgentModeStore(s => s.selectedDirectory);
  const internetSearchEnabled = useAgentModeStore(s => s.internetSearchEnabled);

  // Auto-resize textarea
  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 128) + 'px';
  }, []);

  const processFile = useCallback(async (file: File) => {
    // Basic file processor (just for placeholder ui symmetry)
    const reader = new FileReader();
    return new Promise<void>((resolve) => {
      reader.onload = (e) => {
        const result = e.target?.result as string;
        let type: 'image' | 'video' | 'pdf' | null = null;
        if (file.type.startsWith('image/')) type = 'image';
        else if (file.type.startsWith('video/')) type = 'video';
        else if (file.type === 'application/pdf') type = 'pdf';
        if (type) {
          setAttachments(prev => [...prev, { type: type!, data: result, name: file.name, preview: type === 'image' ? result : undefined }]);
        }
        resolve();
      };
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      await Promise.all(Array.from(e.target.files).map(processFile));
      e.target.value = '';
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length) {
      await Promise.all(Array.from(e.dataTransfer.files).map(processFile));
    }
  };

  const handleSubmit = async () => {
    if ((!goal.trim() && attachments.length === 0) || isRunning) return;

    // Build goal with attachment context
    let enrichedGoal = goal;
    if (attachments.length > 0) {
      const attachmentInfo = attachments
        .map((a, i) => `[Arquivo ${i + 1}: ${a.name} (${a.type})]`)
        .join('\n');
      enrichedGoal = `${goal}\n\n--- Anexos ---\n${attachmentInfo}`;
    }

    startExecution(enrichedGoal, {
      model: selectedModel,
      permissionMode,
      directory: selectedDirectory || undefined,
    });
    setGoal('');
    setAttachments([]);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const permissionEvent = events.slice().reverse().find(e => e.type === 'tool_permission_ask');
  const finalResponse = events.find(e => e.type === 'final_response');
  const tickerLabel = getTickerMessage(events);

  // Smooth scroll to bottom on new updates
  useEffect(() => {
    if (!drawerOpen) {
       messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [events.length, currentExecution?.status, drawerOpen]);

  // Cinematic blur if awaiting permission
  const canvasBlur = permissionEvent ? 'blur(24px) grayscale(50%)' : 'none';

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative" style={{ background: 'transparent' }}>
      
      {/* Cinematic dimming overlay when asking permission */}
      {permissionEvent && (
        <div className="absolute inset-0 z-40 bg-black/40 backdrop-blur-md animate-fade-in flex items-center justify-center p-6">
          <div className="bg-[var(--sidebar-bg)] border border-[var(--error)]/50 rounded-2xl p-6 shadow-2xl max-w-lg w-full">
            <div className="flex items-center gap-3 mb-4 text-[var(--warning)]">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <h2 className="text-lg font-bold">Autorização Requirida</h2>
            </div>
            <p className="text-sm opacity-80 mb-4">A engine pausou para solicitar permissão para:</p>
            <div className="mb-4 text-xs font-bold uppercase tracking-widest opacity-60">Tool: {permissionEvent.data?.tool_name}</div>
            <pre className="bg-black/50 p-4 rounded-xl border border-white/5 font-mono text-xs overflow-x-auto text-red-300 mb-6">
              {JSON.stringify(permissionEvent.data?.arguments || permissionEvent.data?.tool_kwargs || {}, null, 2)}
            </pre>
            <div className="flex justify-end gap-3">
              <button 
                onClick={() => sendResponse({ approved: false })}
                className="px-4 py-2 rounded-lg text-xs font-bold transition-all bg-white/5 hover:bg-white/10"
              >
                Bloquear
              </button>
              <button 
                onClick={() => sendResponse({ approved: true })}
                className="px-4 py-2 rounded-lg text-xs font-bold transition-all bg-[var(--persona-primary)] text-black shadow-[0_0_15px_var(--persona-glow)] hover:scale-105"
              >
                Autorizar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Clean Canvas */}
      <div 
        className="flex-1 overflow-y-auto px-6 py-6 pb-40 scroll-smooth transition-all duration-700" 
        style={{ filter: canvasBlur }}
      >
        <div className="max-w-4xl mx-auto w-full space-y-6">
          
          {/* Main Request Representation */}
          {currentExecution && (
            <div className="flex justify-end animate-fade-in-up">
              <div 
                className="text-[var(--text-primary)] px-5 py-3 rounded-2xl rounded-tr-sm max-w-[80%] backdrop-blur-md shadow-lg"
                style={{ 
                  background: 'color-mix(in srgb, var(--persona-primary) 15%, transparent)',
                  borderColor: 'color-mix(in srgb, var(--persona-primary) 30%, transparent)',
                  borderWidth: '1px',
                  borderStyle: 'solid'
                }}
              >
                <p className="text-sm leading-relaxed">{currentExecution.goal}</p>
              </div>
            </div>
          )}

          {/* Subagents Representation (Mission Cards) */}
          {events.filter(e => e.type === 'agent_spawn').map((e, idx) => (
             <div key={idx} className="ml-8 border-l-2 pl-6 py-2 relative animate-fade-in-up" style={{ borderColor: 'var(--glass-border)' }}>
                <div className="absolute w-3 h-3 rounded-full border-2 border-[var(--sidebar-bg)] -left-[7px] top-4 shadow-[0_0_10px_var(--persona-primary)]" style={{ background: 'var(--persona-primary)' }} />
                <div className="bg-white/5 border border-white/10 p-4 rounded-xl backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-2 text-xs font-bold opacity-70">
                     <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--info)" strokeWidth="2">
                       <circle cx="12" cy="12" r="10" />
                       <path d="M12 16v-4" />
                       <path d="M12 8h.01" />
                     </svg>
                     Sub-agente: {e.data?.agent_type || 'Worker'}
                  </div>
                  <p className="text-sm opacity-90">{e.data?.goal || 'Missão particionada...'}</p>
                </div>
             </div>
          ))}

          {/* Final Results */}
          {finalResponse && (
            <div className="mt-8 animate-fade-in">
              <div className="flex items-center gap-3 mb-4">
                 <div className="w-8 h-8 rounded-xl flex items-center justify-center bg-gradient-to-br from-[var(--persona-primary)] to-[var(--persona-secondary)] text-black shadow-[0_0_15px_var(--persona-glow)]">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                 </div>
                 <span className="font-bold tracking-widest uppercase text-xs opacity-70">Desfecho</span>
              </div>
              <div className="bg-[var(--sidebar-bg)]/80 border border-[var(--glass-border)] p-6 rounded-2xl shadow-xl backdrop-blur-xl text-sm leading-relaxed whitespace-pre-wrap">
                 {finalResponse.data?.content || ''}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} className="h-20" />
        </div>
      </div>

      {/* Diagnostics Drawer (Hidden by default) */}
      <div className={`absolute top-0 right-0 bottom-0 w-80 bg-[var(--sidebar-bg)] border-l border-[var(--glass-border)] shadow-2xl backdrop-blur-2xl transition-transform duration-500 z-30 ${drawerOpen ? 'translate-x-0' : 'translate-x-[105%]'}`}>
        <div className="p-4 border-b border-[var(--glass-border)] flex justify-between items-center">
          <h3 className="text-xs font-bold tracking-widest uppercase text-[var(--text-secondary)]">Activity Trail</h3>
          <button onClick={() => setDrawerOpen(false)} className="opacity-50 hover:opacity-100 transition-opacity">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-4 space-y-3 overflow-y-auto h-[calc(100%-60px)] custom-scrollbar">
          {events.map((ev, i) => (
             <div key={i} className="text-[10px] font-mono p-2 rounded bg-black/20 border border-white/5 break-words">
                <span className="text-[var(--persona-primary)] font-bold">{ev.type}</span>
                <div className="opacity-60 mt-1">{JSON.stringify(ev.data, null, 2)}</div>
             </div>
          ))}
          {events.length === 0 && <div className="text-xs opacity-40 text-center mt-10">Trail vazio.</div>}
        </div>
      </div>

      {/* Bottom Interface Dock */}
      <div 
        className="absolute bottom-0 left-0 right-0 z-20 px-4 pb-8 flex flex-col items-center gap-3 pointer-events-none"
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        
        {/* Status Ticker (Floats above input) */}
        {isRunning && (
           <div className="pointer-events-auto bg-[var(--sidebar-bg)]/90 backdrop-blur-xl border border-[var(--glass-border)] px-4 py-1.5 rounded-full shadow-lg flex items-center gap-3 animate-fade-in-up cursor-pointer hover:bg-white/5 transition-all"
                onClick={() => setDrawerOpen(!drawerOpen)}>
              {/* Firefly indicator */}
              <div className="relative w-3 h-3 flex items-center justify-center">
                <div className="absolute w-2 h-2 rounded-full bg-[var(--persona-primary)]" />
                <div className="absolute w-4 h-4 rounded-full border border-[var(--persona-primary)] animate-ping opacity-50" />
              </div>
              <span className="text-xs font-medium text-[var(--text-primary)] opacity-80">{tickerLabel}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-40">
                <path d="M15 18l-6-6 6-6" />
              </svg>
           </div>
        )}

        {/* Unified Composer Pill */}
        <div className={`max-w-[720px] w-full pointer-events-auto transition-all duration-300 ${isDragging ? 'opacity-50 scale-95' : 'scale-100'}`}>
          <div className="flex flex-col rounded-2xl p-2 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-2xl border border-[var(--glass-border)] focus-within:border-[var(--persona-primary)] focus-within:shadow-[0_16px_48px_rgba(0,0,0,0.4)] focus-within:-translate-y-1 transition-all" style={{ background: 'var(--sidebar-bg)' }}>
            
            {/* Attachments Preview Area (Inside Pill) */}
            {attachments.length > 0 && (
              <div className="flex gap-2 flex-wrap px-2 pt-2">
                {attachments.map((att, idx) => (
                  <div key={idx} className="relative group rounded-xl overflow-hidden border border-[var(--glass-border)] bg-[var(--surface-hover)] w-14 h-14 flex items-center justify-center">
                    {att.type === 'image' && att.preview ? (
                      <img src={att.preview} alt={att.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-[8px] font-mono opacity-70">{att.type.toUpperCase()}</span>
                    )}
                    <button onClick={() => setAttachments(attachments.filter((_, i) => i !== idx))} className="absolute top-1 right-1 w-4 h-4 rounded-full bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                      <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* TOP: Textarea */}
            <div className="px-2 pt-2 pb-1 relative">
              <textarea
                ref={textareaRef}
                value={goal}
                disabled={isRunning}
                onChange={(e) => { setGoal(e.target.value); autoResize(); }}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || !e.shiftKey)) { e.preventDefault(); handleSubmit(); } }}
                placeholder="Orquestre uma tarefa no modo agente..."
                className="w-full bg-transparent text-[0.95rem] resize-none outline-none max-h-32 placeholder:text-gray-500/70"
                style={{ color: 'var(--text-primary)', caretColor: 'var(--persona-primary)' }}
                rows={1}
              />
            </div>

            {/* BOTTOM: Actions Row */}
            <div className="flex justify-between items-center px-1 mt-1 pb-1">
              <div className="flex items-center gap-1.5">
                <button onClick={() => fileInputRef.current?.click()} className="flex items-center justify-center w-8 h-8 rounded-full text-[var(--text-secondary)] hover:bg-white/5 transition-colors">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                  </svg>
                </button>
                <DirectorySelector theme={theme} />
              </div>

              <div className="flex items-center gap-1.5">
                <AgentModelSelector theme={theme} />
                <button
                  onClick={isRunning ? cancelExecution : handleSubmit}
                  disabled={isRunning ? false : (!goal.trim() && attachments.length === 0)}
                  className={`flex items-center justify-center w-8 h-8 rounded-full transition-all duration-300 shadow-md ${
                    isRunning 
                      ? 'bg-[var(--error)] hover:scale-105 hover:bg-red-500 text-white shadow-[0_0_15px_rgba(239,68,68,0.4)]' 
                      : (goal.trim() || attachments.length > 0)
                        ? 'bg-[var(--persona-primary)] hover:scale-105 text-black shadow-[0_0_15px_var(--persona-glow)]'
                        : 'bg-[var(--surface-hover)] text-[var(--text-tertiary)] opacity-60 pointer-events-none'
                  }`}
                >
                  {isRunning ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" /></svg>
                  )}
                </button>
              </div>
            </div>
            
          </div>
        </div>

      </div>

      <input ref={fileInputRef} type="file" multiple accept="image/*,video/*,application/pdf" onChange={handleFileChange} className="hidden" />
    </div>
  );
}
