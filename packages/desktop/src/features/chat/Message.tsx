import { memo, useCallback, useState } from 'react';
import { usePersonaStore } from '@/stores/persona-store';
import { usePersonaTheme } from '@/hooks/usePersonaTheme';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface MessageProps {
  role: string;
  content: string;
  timestamp: string;
  images?: string[];
  isStreaming?: boolean;
  showTimestamp?: boolean;
}

export const Message = memo(function Message({ role, content, timestamp, images, isStreaming, showTimestamp = true }: MessageProps) {
  const isUser = role === 'user';
  const isError = content.startsWith('[Erro]') || content.startsWith('[Error]');
  const activePersonaId = usePersonaStore((s) => s.activePersona);
  const personas = usePersonaStore((s) => s.personas);
  const activePersonaObj = personas.find(p => p.name === activePersonaId);
  const personaTheme = usePersonaTheme(activePersonaId);
  const personaAvatar = personaTheme.avatar;

  const [userImgError, setUserImgError] = useState(false);

  const handleCopy = useCallback((code: string) => {
    navigator.clipboard.writeText(code);
  }, []);

  return (
    <div className="message-enter mb-5">
      {/* Message Row */}
      <div className={`flex items-end gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        {/* Avatar */}
        <div className="flex-shrink-0">
          {isUser ? (
            /* User avatar (no glow) */
            <div
              className="w-10 h-10 rounded-full overflow-hidden border-2 flex items-center justify-center"
              style={{ borderColor: 'var(--glass-border)', background: 'var(--button-bg)' }}
            >
              {!userImgError ? (
                <img
                  src="/profile.png"
                  alt="User"
                  className="w-full h-full object-cover"
                  onError={() => setUserImgError(true)}
                />
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                  style={{ color: 'var(--text-tertiary)' }}>
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              )}
            </div>
          ) : (
            /* Persona avatar (with glow ring) */
            <div className="w-10 h-10 rounded-full persona-avatar-ring">
              <img
                src={`/${personaAvatar}`}
                alt="Persona"
                className="w-full h-full object-cover rounded-full"
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  target.style.display = 'none';
                  target.parentElement!.style.background = 'var(--persona-primary)';
                }}
              />
            </div>
          )}
        </div>

        {/* Bubble Container */}
        <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'} flex-1 min-w-0`}>
          {/* Message Bubble */}
          <div
            className={`
              ${isError
                ? 'chat-bubble-error'
                : isUser
                  ? 'chat-bubble-user'
                  : 'chat-bubble-assistant'
              }
              ${!content && !isUser ? 'chat-bubble-none' : ''}
            `}
          >
            {!content && !isUser && (
              <div className="flex items-center min-h-[40px] px-2">
                <span 
                  className="text-base font-bold tracking-tight persona-logo-text animate-pulse italic whitespace-nowrap" 
                  style={{ 
                    '--logo-primary': personaTheme.primary,
                    '--logo-secondary': personaTheme.secondary,
                  } as React.CSSProperties}
                >
                  {activePersonaObj ? activePersonaObj.display_name : 'Ahri'} está pensando...
                </span>
              </div>
            )}
            {/* Images */}
            {images && images.length > 0 && (
              <div className={`grid gap-2 mb-3 ${images.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>
                {images.map((img_b64, idx) => (
                  <img
                    key={idx}
                    src={`data:image/jpeg;base64,${img_b64}`}
                    alt={`Attachment ${idx + 1}`}
                    className="rounded-xl w-full object-cover max-h-48"
                  />
                ))}
              </div>
            )}

            {/* Error icon */}
            {isError && (
              <div className="flex items-center gap-2 mb-1">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="flex-shrink-0" style={{ color: 'var(--error)' }}>
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span className="text-xs font-mono" style={{ color: 'var(--error)' }}>Error</span>
              </div>
            )}

            {/* Content with react-markdown or typing indicator */}
            {content && (
              <div className={`text-sm leading-relaxed ${isStreaming ? 'streaming-cursor' : ''} markdown-body`}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code({ className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className || '');
                      const codeString = String(children).replace(/\n$/, '');

                      if (match) {
                        return (
                          <div className="relative my-3 group">
                            <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                              <button
                                onClick={() => handleCopy(codeString)}
                                className="px-2 py-1 text-[10px] font-mono rounded-md transition-colors"
                                style={{
                                  background: 'var(--code-bg)',
                                  color: 'var(--text-secondary)',
                                  border: '1px solid var(--glass-border)',
                                }}
                              >
                                COPY
                              </button>
                            </div>
                            {match[1] && (
                              <div className="text-[10px] font-mono uppercase tracking-wider px-3 pt-2 pb-0" style={{ color: 'var(--text-tertiary)' }}>
                                {match[1]}
                              </div>
                            )}
                            <SyntaxHighlighter
                              style={oneDark as any}
                              language={match[1]}
                              PreTag="div"
                              customStyle={{
                                margin: 0,
                                padding: '12px',
                                borderRadius: '12px',
                                fontSize: '12px',
                                background: 'var(--code-bg)',
                                border: '1px solid var(--glass-border)',
                              }}
                            >
                              {codeString}
                            </SyntaxHighlighter>
                          </div>
                        );
                      }

                      // Inline code
                      return (
                        <code
                          className="px-1.5 py-0.5 rounded-md text-xs font-mono"
                          style={{
                            background: 'var(--code-bg)',
                            border: '1px solid var(--glass-border)',
                          }}
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    },
                    a({ href, children }) {
                      return (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ color: 'var(--persona-primary)', textDecoration: 'underline', textUnderlineOffset: '2px' }}
                        >
                          {children}
                        </a>
                      );
                    },
                    strong({ children }) {
                      return <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{children}</strong>;
                    },
                    p({ children }) {
                      return <p className="mb-1.5 last:mb-0">{children}</p>;
                    },
                    ul({ children }) {
                      return <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>;
                    },
                    ol({ children }) {
                      return <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>;
                    },
                    blockquote({ children }) {
                      return (
                        <blockquote className="border-l-2 pl-3 my-2 italic" style={{ borderColor: 'var(--persona-primary)', color: 'var(--text-secondary)' }}>
                          {children}
                        </blockquote>
                      );
                    },
                    table({ children }) {
                      return (
                        <div className="overflow-x-auto my-2">
                          <table className="text-xs border-collapse w-full" style={{ border: '1px solid var(--glass-border)' }}>
                            {children}
                          </table>
                        </div>
                      );
                    },
                    th({ children }) {
                      return (
                        <th className="px-3 py-1.5 text-left font-semibold" style={{ background: 'var(--code-bg)', borderBottom: '1px solid var(--glass-border)' }}>
                          {children}
                        </th>
                      );
                    },
                    td({ children }) {
                      return (
                        <td className="px-3 py-1.5" style={{ borderBottom: '1px solid var(--glass-border)' }}>
                          {children}
                        </td>
                      );
                    },
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            )}
          </div>

          {/* Timestamp (below bubble) */}
          {showTimestamp && timestamp && (
            <span className={`text-[10px] font-medium tracking-wide uppercase px-2 opacity-60 mix-blend-overlay ${isUser ? 'text-right' : 'text-left'}`} style={{ color: 'var(--text-tertiary)' }}>
              {timestamp}
            </span>
          )}

          {/* Streaming indicator removed */}
        </div>
      </div>
    </div>
  );
});

// Export also as MessageBubble for compatibility
export { Message as MessageBubble };
