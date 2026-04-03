import { useState, useRef, useCallback, useEffect } from 'react';
import { useChatStore, type Attachment } from '@/stores/chat-store';
import { usePersonaStore } from '@/stores/persona-store';
import { ModelSelector } from '@/components/ModelSelector';

type SearchMode = 'default' | 'web_search' | 'lore_search';

function SpeedModeSelector() {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const model = useChatStore((s) => s.model);
  const reasoningLevel = useChatStore((s) => s.reasoningLevel);
  const setReasoningLevel = useChatStore((s) => s.setReasoningLevel);
  const enableThinking = useChatStore((s) => s.enableThinking);
  const setEnableThinking = useChatStore((s) => s.setEnableThinking);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // LOCAL (Ollama/Qwen) — toggle de pensamento on/off
  if (model === 'LOCAL') {
    return (
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setEnableThinking(!enableThinking)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full transition-all duration-300 hover:bg-white/5 border border-transparent hover:border-white/10"
          style={{
            fontSize: '0.8rem',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            color: enableThinking ? '#F97316' : 'var(--text-secondary)',
          }}
          title="Raciocínio Ativo/Desativado"
        >
          <span>Pensamento: {enableThinking ? 'Ligado' : 'Desligado'}</span>
        </button>
      </div>
    );
  }

  // LITE (Gemini 3.1 Flash Lite) — seletor de thinking budget (baixo/médio/alto)
  if (model === 'LITE') {
    const GEMINI_LEVELS = [
      { id: 'low', label: 'Baixo' },
      { id: 'medium', label: 'Médio' },
      { id: 'high', label: 'Alto' },
    ];

    const currentLabel = GEMINI_LEVELS.find(l => l.id === reasoningLevel)?.label || 'Médio';

    return (
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full transition-all duration-300 hover:bg-white/5 border border-transparent hover:border-white/10"
          style={{
            fontSize: '0.8rem',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            color: 'var(--text-secondary)',
          }}
        >
          <span>Pensamento: {currentLabel}</span>
          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
            className={`opacity-50 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {open && (
          <div
            className="absolute right-0 bottom-full mb-2 rounded-lg overflow-hidden z-50 min-w-[130px] animate-fade-in"
            style={{
              background: 'var(--surface-solid)',
              border: '1px solid var(--glass-border)',
              backdropFilter: 'none',
              boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
            }}
          >
            {GEMINI_LEVELS.map((l) => (
              <button
                key={l.id}
                onClick={() => {
                  setReasoningLevel(l.id);
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-xs transition-colors duration-100"
                style={{
                  color: reasoningLevel === l.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                  background: reasoningLevel === l.id ? 'var(--surface-hover)' : 'transparent',
                }}
              >
                {l.label}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  // DEEPSEEK (R1) — raciocínio embutido no modelo, sem controle externo
  return null;
}

export function ChatInput() {
  const [text, setText] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [plusMenuOpen, setPlusMenuOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>('default');
  const [isFocused, setIsFocused] = useState(false);
  const [errorBanner, setErrorBanner] = useState<{ msg: string; id: number } | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const plusMenuRef = useRef<HTMLDivElement>(null);

  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamingEnabled = useChatStore((s) => s.streamingEnabled);
  const sendMessageStreaming = useChatStore((s) => s.sendMessageStreaming);
  const stopStreaming = useChatStore((s) => s.stopStreaming);
  const sendMessageHttp = useChatStore((s) => s.sendMessage);
  const activePersona = usePersonaStore((s) => s.activePersona);
  const personas = usePersonaStore((s) => s.personas);

  const currentPersona = personas.find((p) => p.name === activePersona);

  // Close menus on click outside
  useEffect(() => {
    if (!plusMenuOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (plusMenuRef.current && !plusMenuRef.current.contains(target) && !target.closest('#attach-btn')) {
        setPlusMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [plusMenuOpen]);

  const handleSend = useCallback(async () => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || isStreaming) return;

    const { internetSearchEnabled, globalEnableThinking, enableThinking, model } = useChatStore.getState();

    if (searchMode === 'web_search' && !internetSearchEnabled) {
      setErrorBanner({ msg: 'A Busca Web está bloqueada. Habilite "Pesquisa na Web" no menu principal de Configurações primeiro.', id: Date.now() });
      return;
    }
    if (model === 'LOCAL' && enableThinking && !globalEnableThinking) {
      setErrorBanner({ msg: 'Raciocínio bloqueado. Habilite "Raciocínio (Modelos Locais)" no menu principal de Configurações.', id: Date.now() });
      return;
    }

    setErrorBanner(null);

    // Slash commands
    if (trimmed.startsWith('/')) {
      await handleSlashCommand(trimmed);
      setText('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      return;
    }

    const send = streamingEnabled ? sendMessageStreaming : sendMessageHttp;
    send(trimmed, attachments, searchMode);
    setText('');
    setAttachments([]);
    setSearchMode('default');

    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [text, attachments, searchMode, isStreaming, streamingEnabled, sendMessageStreaming, sendMessageHttp]);

  const handleSlashCommand = async (cmd: string) => {
    const { api } = await import('@/api/client');
    const { useChatStore } = await import('@/stores/chat-store');

    const userMsg = {
      role: 'user' as const,
      content: cmd,
      images: [] as string[],
      timestamp: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
      meta: {},
    };
    useChatStore.getState().addMessage(userMsg);

    try {
      if (cmd === '/memoria') {
        const profile = await api.getProfile();
        const response = `[SYSTEM] Memory State: ${JSON.stringify(profile.attributes || {}, null, 2)}`;
        useChatStore.getState().addMessage({
          role: 'assistant', content: response, images: [], timestamp: '', meta: { system: true }
        });
      } else {
        useChatStore.getState().addMessage({
          role: 'assistant', content: `Unknown command: ${cmd}`, images: [], timestamp: '', meta: { error: true }
        });
      }
    } catch (e) {
      useChatStore.getState().addMessage({
        role: 'assistant', content: `Error: ${e}`, images: [], timestamp: '', meta: { error: true }
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const processFile = useCallback(async (file: File) => {
    const reader = new FileReader();
    return new Promise<void>((resolve) => {
      reader.onload = (e) => {
        const result = e.target?.result as string;
        let type: 'image' | 'video' | 'pdf' | null = null;
        if (file.type.startsWith('image/')) type = 'image';
        else if (file.type.startsWith('video/')) type = 'video';
        else if (file.type === 'application/pdf') type = 'pdf';

        if (type) {
          setAttachments(prev => [...prev, {
            type: type!,
            data: result,
            name: file.name,
            preview: type === 'image' ? result : undefined
          }]);
        }
        resolve();
      };
      reader.readAsDataURL(file);
    });
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      await Promise.all(files.map(processFile));
      e.target.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      await Promise.all(files.map(processFile));
    }
  };

  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData.items;
    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].kind === 'file') {
        const file = items[i].getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      await Promise.all(files.map(processFile));
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 128) + 'px';
  };

  const handleFileSelect = (accept: string) => {
    if (fileInputRef.current) {
      fileInputRef.current.accept = accept;
      fileInputRef.current.click();
    }
    setPlusMenuOpen(false);
  };

  const selectTool = (mode: SearchMode) => {
    setSearchMode(mode === searchMode ? 'default' : mode);
    setPlusMenuOpen(false);
  };

  return (
    <div
      className="px-4 pb-4 pt-2 max-w-3xl mx-auto w-full animate-fade-in-up"
      style={{ animationDuration: '0.4s' }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Composer Area */}
      <div className={`relative ${isDragging ? 'opacity-50' : ''}`}>
        {errorBanner && (
          <div key={errorBanner.id} className="absolute bottom-full left-0 right-0 mb-3 px-3 py-2 rounded-xl flex items-center justify-between text-[11px] font-semibold animate-shake shadow-lg z-50 backdrop-blur-md" style={{ background: 'color-mix(in srgb, var(--error) 15%, var(--surface-elevated))', border: '1px solid color-mix(in srgb, var(--error) 30%, transparent)', color: 'var(--error)' }}>
            <div className="flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              <span>{errorBanner.msg}</span>
            </div>
            <button onClick={() => setErrorBanner(null)} className="hover:opacity-70 transition-opacity p-1">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        )}
        {/* Plus Menu Popup (floating above, anchored right) */}
        {plusMenuOpen && (
          <div ref={plusMenuRef} className="absolute bottom-full left-0 mb-2 plus-menu animate-fade-in z-50 w-[220px]">
            {/* Tools Section */}
            <div className="plus-menu-section-title">Tools</div>
            <div className="flex flex-col gap-1">
              <button
                onClick={() => selectTool('web_search')}
                className={`plus-menu-item ${searchMode === 'web_search' ? 'active' : ''}`}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--info)' }}>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
                <span>Web Search</span>
              </button>
              <button
                onClick={() => selectTool('lore_search')}
                className={`plus-menu-item ${searchMode === 'lore_search' ? 'active' : ''}`}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--status-working)' }}>
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  <line x1="8" y1="7" x2="16" y2="7" />
                  <line x1="8" y1="11" x2="13" y2="11" />
                </svg>
                <span>Lore Search</span>
              </button>
            </div>

            <div className="plus-menu-divider" />

            {/* Attachments Section */}
            <div className="plus-menu-section-title">Attachments</div>
            <div className="flex flex-col gap-1">
              <button
                onClick={() => handleFileSelect('image/*')}
                className="plus-menu-item"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--success)' }}>
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
                <span>Image</span>
              </button>
              <button
                onClick={() => handleFileSelect('video/*')}
                className="plus-menu-item"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--warning)' }}>
                  <polygon points="23 7 16 12 23 17 23 7" />
                  <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                </svg>
                <span>Video</span>
              </button>
              <button
                onClick={() => handleFileSelect('application/pdf')}
                className="plus-menu-item"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--error)' }}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
                <span>PDF</span>
              </button>
            </div>
          </div>
        )}

        {/* Unified Composer Pill (Gemini Style) */}
        <div
          className={`flex flex-col bg-[var(--sidebar-bg)] rounded-2xl p-2 shadow-lg backdrop-blur-xl transition-all duration-300 ease-out border ${
            isFocused ? 'border-[var(--persona-primary)] shadow-[0_16px_48px_rgba(0,0,0,0.25)] -translate-y-2' : 'border-[var(--glass-border)] translate-y-0'
          }`}
        >
          {/* Attachments Preview Area (Inside Pill) */}
          {attachments.length > 0 && (
            <div className="flex gap-2 flex-wrap px-2 pt-2">
              {attachments.map((att, idx) => (
                <div 
                  key={idx} 
                  className="relative group rounded-xl overflow-hidden border flex-shrink-0 animate-fade-in-up" 
                  style={{ 
                    borderColor: 'var(--glass-border)', 
                    background: 'var(--surface-hover)',
                    animationDuration: '0.3s',
                    animationFillMode: 'both',
                  }}
                >
                  {att.type === 'image' && att.preview ? (
                    <img src={att.preview} alt={att.name} className="w-14 h-14 object-cover" />
                  ) : (
                    <div className="w-14 h-14 flex flex-col items-center justify-center p-1">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: att.type === 'pdf' ? 'var(--error)' : 'var(--warning)' }}>
                        {att.type === 'pdf' ? (
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        ) : (
                          <polygon points="23 7 16 12 23 17 23 7" />
                        )}
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                      <span className="text-[8px] font-mono mt-1 opacity-70 truncate max-w-full px-1">{att.type.toUpperCase()}</span>
                    </div>
                  )}
                  {/* Remove Button Overlay */}
                  <button
                    onClick={() => setAttachments(attachments.filter((_, i) => i !== idx))}
                    className="absolute top-1 right-1 w-4 h-4 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ background: 'rgba(0,0,0,0.6)', color: '#fff' }}
                  >
                    <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
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
              value={text}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={`Converse com ${currentPersona?.display_name || activePersona}...`}
              rows={1}
              className="w-full bg-transparent text-[0.95rem] resize-none outline-none max-h-32 placeholder:font-sans placeholder:text-gray-500"
              style={{
                color: 'var(--text-primary)',
                caretColor: 'var(--persona-primary)',
              }}
              disabled={isStreaming}
            />
          </div>

          {/* BOTTOM: Actions Row */}
          <div className="flex justify-between items-center px-1 mt-1">
            {/* Left Actions */}
            <div className="flex items-center gap-1.5">
              {/* Attach / Plus Menu Button */}
              <button
                id="attach-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setPlusMenuOpen(!plusMenuOpen);
                }}
                className={`flex items-center justify-center w-8 h-8 rounded-full transition-colors ${
                  plusMenuOpen ? 'bg-white/10 text-white' : 'text-[var(--text-tertiary)] hover:bg-white/5 hover:text-white'
                }`}
                title="Tools & Attachments"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="12" y1="5" x2="12" y2="19"></line>
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                </svg>
              </button>

              {/* Tools Badges (Web/Lore) */}
              {searchMode !== 'default' && (
                <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[var(--glass-border)] text-[0.7rem] font-medium transition-colors ${
                  searchMode === 'web_search' ? 'bg-[var(--info)]/20 text-[var(--info)]' : 'bg-[var(--status-working)]/20 text-[var(--status-working)]'
                }`}>
                  {searchMode === 'web_search' ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="2" y1="12" x2="22" y2="12" />
                    </svg>
                  ) : (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                    </svg>
                  )}
                  <span>{searchMode === 'web_search' ? 'Deep Research' : 'Lore Search'}</span>
                  <button
                    onClick={() => setSearchMode('default')}
                    className="hover:opacity-100 opacity-60 transition-opacity ml-1"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              )}

              {/* Model Selector placed right after the tools as a distinct pill */}
              <div className="ml-1">
                <ModelSelector compact />
              </div>
            </div>

            {/* Right Actions */}
            <div className="flex items-center gap-2">
              <SpeedModeSelector />

              {/* Sending / Stop button */}
              <button
                onClick={isStreaming ? stopStreaming : handleSend}
                disabled={(!text.trim() && attachments.length === 0) && !isStreaming}
                className={`flex items-center justify-center w-8 h-8 rounded-full transition-all duration-300 ${
                  (text.trim() || attachments.length > 0 || isStreaming)
                    ? 'bg-[var(--persona-primary)] text-white scale-100 hover:scale-110 shadow-md'
                    : 'bg-[var(--surface-hover)] text-[var(--text-tertiary)] opacity-60 pointer-events-none cursor-default'
                }`}
                style={{
                  background: isStreaming ? 'var(--error)' : undefined
                }}
                title={isStreaming ? 'Parar Geração' : 'Enviar'}
              >
                {isStreaming ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,video/*,application/pdf"
        onChange={handleFileChange}
        className="hidden"
      />
    </div>
  );
}
