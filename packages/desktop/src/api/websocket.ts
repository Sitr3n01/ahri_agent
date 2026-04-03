/**
 * WebSocket manager para streaming de chat.
 */
import { api } from './client';

type ChunkHandler = (content: string) => void;
type DoneHandler = (data: {
  content: string;
  agent_tasks: unknown[];
  memory_notifications: string[];
}) => void;
type ErrorHandler = (error: string) => void;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private onChunk: ChunkHandler = () => { };
  private onDone: DoneHandler = () => { };
  private onError: ErrorHandler = () => { };
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private isManuallyDisconnected = false;
  private isConnecting = false;

  async connect(): Promise<boolean> {
    if (this.ws?.readyState === WebSocket.OPEN) return true;
    if (this.isConnecting) return false;

    this.isConnecting = true;
    this.isManuallyDisconnected = false;

    return new Promise((resolve) => {
      try {
        if (this.ws) {
          this.ws.close();
          this.ws = null;
        }

        this.ws = api.createChatWebSocket();

        this.ws.onopen = () => {
          // Send auth immediately
          this.ws?.send(
            JSON.stringify({ type: 'auth', token: api.getAccessToken() }),
          );
        };

        this.ws.onmessage = (event) => {
          const data = JSON.parse(event.data);

          switch (data.type) {
            case 'auth':
              if (data.status === 'ok') {
                this.reconnectAttempts = 0;
                this.isConnecting = false;
                resolve(true);
              } else {
                this.isConnecting = false;
                resolve(false);
                // Auth failed, probably shouldn't retry endlessly without new token
                this.disconnect();
              }
              break;
            case 'chunk':
              this.onChunk(data.content);
              break;
            case 'done':
              this.onDone(data);
              break;
            case 'error':
              this.onError(data.detail || 'Unknown error');
              break;
          }
        };

        this.ws.onerror = () => {
          if (this.isConnecting) {
            this.isConnecting = false;
            resolve(false);
          }
          // onerror usually precedes onclose, so we let onclose handle reconnect
        };

        this.ws.onclose = () => {
          this.ws = null;
          if (this.isConnecting) {
            this.isConnecting = false;
            resolve(false);
          }

          if (!this.isManuallyDisconnected) {
            this.scheduleReconnect();
          }
        };
      } catch (e) {
        this.isConnecting = false;
        resolve(false);
        if (!this.isManuallyDisconnected) {
          this.scheduleReconnect();
        }
      }
    });
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[ChatWS] Max reconnect attempts reached');
      return;
    }

    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);

    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

    console.log(`[ChatWS] Reconnecting in ${delay}ms (Attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  sendMessage(
    message: string,
    model: string,
    sessionId?: number,
    images: string[] = [],
    video?: { data: string; name: string },
    pdfs?: { data: string; name: string }[],
    mode: 'default' | 'web_search' | 'lore_search' = 'default',
    reasoning?: { reasoning_level?: string; enable_thinking?: boolean; auto_save_tags?: boolean }
  ) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.onError('WebSocket not connected');
      // Try to reconnect for next time, though this message will fail (fallback handled by store)
      if (!this.isConnecting && !this.isManuallyDisconnected) {
        this.connect();
      }
      return;
    }

    this.ws.send(
      JSON.stringify({
        type: 'message',
        message,
        model,
        session_id: sessionId,
        images,
        video,
        pdfs,
        mode,
        reasoning_level: reasoning?.reasoning_level,
        enable_thinking: reasoning?.enable_thinking,
        auto_save_tags: reasoning?.auto_save_tags,
      }),
    );
  }

  setHandlers(handlers: {
    onChunk?: ChunkHandler;
    onDone?: DoneHandler;
    onError?: ErrorHandler;
  }) {
    if (handlers.onChunk) this.onChunk = handlers.onChunk;
    if (handlers.onDone) this.onDone = handlers.onDone;
    if (handlers.onError) this.onError = handlers.onError;
  }

  disconnect() {
    this.isManuallyDisconnected = true;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      // Prevent onclose from triggering reconnect by setting flag (already done above)
      // Remove handlers to avoid potential memory leaks or zombie callbacks
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      this.ws.onopen = null;
      this.ws.close();
      this.ws = null;
    }
    this.isConnecting = false;
  }

  cancel() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'cancel' }));
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const chatWs = new ChatWebSocket();
