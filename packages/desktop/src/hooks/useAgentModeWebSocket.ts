/**
 * useAgentModeWebSocket - Real-time agent mode execution updates
 *
 * Connects to backend WebSocket for live worker status, execution progress,
 * and TPM quota monitoring.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { AgentExecution, AgentWorkerTask } from '@ahri/shared';

interface WebSocketMessage {
  type: 'connected' | 'status_update' | 'worker_started' | 'worker_completed' | 'execution_completed' | 'tpm_status' | 'error';
  execution_id?: number;
  timestamp?: number;
  message?: string;
  data?: any;
}

interface UseAgentModeWebSocketReturn {
  isConnected: boolean;
  execution: AgentExecution | null;
  workerTasks: Map<number, AgentWorkerTask>;
  tpmStatus: {
    tokens_used_window: number;
    tokens_remaining: number;
    limit_tpm: number;
    utilization_percent: number;
  } | null;
  error: string | null;
  reconnect: () => void;
}

export function useAgentModeWebSocket(
  executionId: number | null,
  enabled: boolean = true
): UseAgentModeWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [execution, setExecution] = useState<AgentExecution | null>(null);
  const [workerTasks, setWorkerTasks] = useState<Map<number, AgentWorkerTask>>(new Map());
  const [tpmStatus, setTpmStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnect = useRef(true);
  const executionStatusRef = useRef<string | null>(null);

  // Keep ref in sync with execution status (avoids stale closure in onclose)
  useEffect(() => {
    executionStatusRef.current = execution?.status ?? null;
  }, [execution?.status]);

  const connect = useCallback(() => {
    if (!executionId || !enabled || !shouldReconnect.current) return;

    // Clear existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Determine WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = import.meta.env.PROD
      ? window.location.host
      : 'localhost:8742';
    const wsUrl = `${wsProtocol}//${wsHost}/agent-mode/ws/${executionId}`;

    console.log('[AgentMode WebSocket] Connecting to:', wsUrl);

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[AgentMode WebSocket] Connected');
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        console.log('[AgentMode WebSocket] Message:', message.type, message);

        if (!message.data && message.type !== 'connected' && message.type !== 'error') {
          console.warn('[AgentMode WebSocket] Missing data in message:', message.type);
          return;
        }

        switch (message.type) {
          case 'connected':
            console.log('[AgentMode WebSocket] Initial connection confirmed');
            break;

          case 'status_update':
            setExecution(prev => prev ? {
              ...prev,
              status: message.data.status,
              plan: message.data.plan || prev.plan
            } : null);
            break;

          case 'worker_started':
            setWorkerTasks(prev => {
              const updated = new Map(prev);
              updated.set(message.data.task_id, {
                id: message.data.task_id,
                execution_id: executionId,
                worker_type: message.data.worker_type,
                model: message.data.model,
                input_data: message.data.input_data,
                output_data: {},
                tokens_used: 0,
                duration_ms: 0,
                status: 'running',
                error: '',
                created_at: message.data.created_at,
                completed_at: null,
                retry_count: 0,
                reflexion_notes: []
              });
              return updated;
            });
            break;

          case 'worker_completed':
            setWorkerTasks(prev => {
              const updated = new Map(prev);
              const existing = updated.get(message.data.task_id);
              if (existing) {
                updated.set(message.data.task_id, {
                  ...existing,
                  status: message.data.status,
                  output_data: message.data.output_data,
                  error: message.data.error,
                  completed_at: message.data.completed_at,
                  duration_ms: message.data.duration_ms || 0,
                  tokens_used: message.data.tokens_used || 0
                });
              }
              return updated;
            });
            break;

          case 'execution_completed':
            setExecution(prev => prev ? {
              ...prev,
              status: message.data.status,
              result: message.data.result,
              error: message.data.error,
              completed_at: message.data.completed_at
            } : null);

            // Close connection after completion
            shouldReconnect.current = false;
            ws.close();
            break;

          case 'tpm_status':
            setTpmStatus(message.data);
            break;

          case 'error':
            console.error('[AgentMode WebSocket] Error:', message.message);
            setError(message.message || 'Unknown error');
            break;

          default:
            console.warn('[AgentMode WebSocket] Unknown message type:', message.type);
        }
      } catch (err) {
        console.error('[AgentMode WebSocket] Failed to parse message:', err);
      }
    };

    ws.onerror = (event) => {
      console.error('[AgentMode WebSocket] Connection error:', event);
      setError('WebSocket connection error');
      setIsConnected(false);
    };

    ws.onclose = (event) => {
      console.log('[AgentMode WebSocket] Disconnected:', event.code, event.reason);
      setIsConnected(false);

      // Use ref to avoid stale closure — reads current status without being a dependency
      const status = executionStatusRef.current;
      if (shouldReconnect.current && status && ['planning', 'running'].includes(status)) {
        console.log('[AgentMode WebSocket] Reconnecting in 2s...');
        reconnectTimeoutRef.current = setTimeout(() => {
          if (shouldReconnect.current) {
            connect();
          }
        }, 2000);
      }
    };

    wsRef.current = ws;
  }, [executionId, enabled]);

  // Auto-connect when execution ID changes
  useEffect(() => {
    if (executionId && enabled) {
      shouldReconnect.current = true;
      connect();
    }

    return () => {
      shouldReconnect.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [executionId, enabled, connect]);

  const reconnect = useCallback(() => {
    shouldReconnect.current = true;
    connect();
  }, [connect]);

  return {
    isConnected,
    execution,
    workerTasks,
    tpmStatus,
    error,
    reconnect
  };
}
