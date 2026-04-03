interface MessageBubbleProps {
  role: string;
  content: string;
  timestamp: string;
  images?: string[];
  isStreaming?: boolean;
}

export function MessageBubble({ role, content, timestamp, images, isStreaming }: MessageBubbleProps) {
  const isUser = role === 'user';
  const isError = content.startsWith('[Erro]') || content.startsWith('[Error]');

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} message-enter`}>
      <div
        className={`
          max-w-[75%] rounded-2xl px-4 py-3
          ${isUser
            ? 'bg-blue-600/80 text-white border border-blue-500/50'
            : isError
              ? 'bg-red-500/10 border border-red-500/30 text-red-200'
              : 'bg-white/5 text-white/90 border border-white/10'
          }
        `}
      >
        {/* Images */}
        {images && images.length > 0 && (
          <div className="grid grid-cols-2 gap-2 mb-3">
            {images.map((img_b64, idx) => (
              <img
                key={idx}
                src={`data:image/jpeg;base64,${img_b64}`}
                alt={`Attachment ${idx + 1}`}
                className="rounded-lg w-full object-cover max-h-48 border border-white/10"
              />
            ))}
          </div>
        )}

        {/* Content with basic formatting */}
        <div
          className={`text-sm leading-relaxed whitespace-pre-wrap break-words ${isStreaming ? 'streaming-cursor' : ''}`}
          dangerouslySetInnerHTML={{ __html: formatContent(content) }}
        />

        {/* Timestamp */}
        {timestamp && (
          <div className="text-[10px] font-medium tracking-wide uppercase opacity-70 mt-1.5 text-right w-full mix-blend-overlay">
            {timestamp}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Formata conteúdo com markdown básico para HTML.
 * Suporta: **bold**, *italic*, `code`, ```code blocks```, links
 */
function formatContent(text: string): string {
  let html = escapeHtml(text);

  // Code blocks (```...```)
  html = html.replace(
    /```(\w*)\n?([\s\S]*?)```/g,
    '<pre class="bg-black/30 rounded-lg p-3 my-2 overflow-x-auto text-xs font-mono"><code>$2</code></pre>',
  );

  // Inline code (`...`)
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="bg-white/10 px-1.5 py-0.5 rounded text-xs font-mono">$1</code>',
  );

  // Bold (**...**)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold">$1</strong>');

  // Italic (*...*)
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
