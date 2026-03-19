import { useEffect, useRef } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { usePersonaStore } from '@/stores/persona-store';
import { getPersonaTheme } from '@ahri/shared';
import { Message as MessageBubble } from './Message';
import { ChatInput } from './ChatInput';

export function ChatView() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamingContent = useChatStore((s) => s.streamingContent);
  const activePersona = usePersonaStore((s) => s.activePersona);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const theme = getPersonaTheme(activePersona);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  return (
    <div className="flex flex-col h-full bg-transparent">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 scroll-smooth chat-messages-area">
        <div className="max-w-3xl mx-auto w-full">
          {messages.length === 0 && !isStreaming ? (
            /* Empty State — clean, no text */
            <div className="flex-1" />
          ) : (
            <>
              {messages.map((msg, i) => (
                <MessageBubble
                  key={`${i}-${msg.timestamp}`}
                  role={msg.role}
                  content={msg.content}
                  timestamp={msg.timestamp}
                  images={msg.images}
                />
              ))}

              {/* Streaming message */}
              {isStreaming && streamingContent && (
                <MessageBubble
                  role="assistant"
                  content={streamingContent}
                  timestamp=""
                  isStreaming
                />
              )}

              {/* Loading indicator (no content yet) */}
              {isStreaming && !streamingContent && (
                <MessageBubble
                  role="assistant"
                  content=""
                  timestamp=""
                  isStreaming
                />
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <ChatInput />
    </div>
  );
}
