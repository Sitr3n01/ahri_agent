/**
 * Agent Mode WebSocket Manager - Real-time execution updates.
 *
 * Connects to /agent-mode/ws/{execution_id} and streams:
 * - Status updates
 * - Worker progress
 * - TPM quota
 * - Execution completion
 */

export type AgentWSMessageType =
  | 'connected'
  | 'status_update'
  | 'worker_started'
  | 'worker_completed'
  | 'execution_completed'
  | 'tpm_status'
  | 'error';

export interface AgentWSMessage {
  type: AgentWSMessageType;
  data?: any;
  execution_id?: number;
  timestamp?: number;
  message?: string;
}

export interface AgentWSHandlers {
  onConnected?: (data: any) => void;
  onStatusUpdate?: (data: any) => void;
  onWorkerStarted?: (data: any) => void;
  onWorkerCompleted?: (data: any) => void;
  onExecutionCompleted?: (data: any) => void;
  onTPMStatus?: (data: any) => void;
  onError?: (error: string) => void;
  onClose?: () => void;
}

export class AgentWebSocket {
  private ws: WebSocket | null = null;
  private executionId: number;
  private handlers: AgentWSHandlers;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private reconnectDelay = 2000;
  private disposed = false;  // Prevents reconnection after manual close

  constructor(executionId: number, handlers: AgentWSHandlers) {
    this.executionId = executionId;
    this.handlers = handlers;
  }

  connect() {
    if (this.disposed) return;

    const wsUrl = `ws://localhost:8742/agent-mode/ws/${this.executionId}`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log(`[AgentWS] Connected to execution ${this.executionId}`);
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message: AgentWSMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('[AgentWS] Failed to parse message:', error);
      }
    };

    this.ws.onerror = () => {
      // Only report errors if not disposed (user-initiated close doesn't need error)
      if (!this.disposed) {
        console.error('[AgentWS] WebSocket error for execution', this.executionId);
        this.handlers.onError?.('WebSocket connection error');
      }
    };

    this.ws.onclose = () => {
      console.log('[AgentWS] Connection closed');
      if (!this.disposed) {
        this.handlers.onClose?.();

        // Attempt reconnect if not max attempts and not manually closed
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          console.log(`[AgentWS] Reconnecting... (attempt ${this.reconnectAttempts})`);
          setTimeout(() => this.connect(), this.reconnectDelay);
        }
      }
    };
  }

  private handleMessage(message: AgentWSMessage) {
    switch (message.type) {
      case 'connected':
        this.handlers.onConnected?.(message.data || message);
        break;

      case 'status_update':
        this.handlers.onStatusUpdate?.(message.data);
        break;

      case 'worker_started':
        this.handlers.onWorkerStarted?.(message.data);
        break;

      case 'worker_completed':
        this.handlers.onWorkerCompleted?.(message.data);
        break;

      case 'execution_completed':
        this.handlers.onExecutionCompleted?.(message.data);
        this.close(); // Auto-close after completion
        break;

      case 'tpm_status':
        this.handlers.onTPMStatus?.(message.data);
        break;

      case 'error':
        this.handlers.onError?.(message.message || 'Unknown error');
        break;

      default:
        console.warn('[AgentWS] Unknown message type:', message.type);
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  close() {
    this.disposed = true;  // Prevent reconnection and error reporting
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  getReadyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }
}
