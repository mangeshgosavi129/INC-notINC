import { useRef, useState, useCallback, useEffect } from 'react';
import type { WSMessage } from '../types';

export type ConnectionState = 'connecting' | 'open' | 'closed' | 'error';

export function useAdminWebSocket(
  simId: string | null,
  onMessage?: (msg: WSMessage) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const reconnectDelay = useRef(1000);
  const [connectionState, setConnectionState] = useState<ConnectionState>('closed');
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!simId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = import.meta.env.VITE_WS_URL || `${protocol}//${window.location.host}`;
    const url = `${host}/ws/admin/${simId}`;

    setConnectionState('connecting');
    const ws = new WebSocket(url);

    ws.onopen = () => {
      setConnectionState('open');
      reconnectDelay.current = 1000;
    };

    ws.onmessage = (e) => {
      try {
        const msg: WSMessage = JSON.parse(e.data);
        onMessageRef.current?.(msg);
      } catch { /* ignore non-JSON */ }
    };

    ws.onerror = () => setConnectionState('error');

    ws.onclose = () => {
      setConnectionState('closed');
      wsRef.current = null;
      // auto-reconnect
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 10000);
        connect();
      }, reconnectDelay.current);
    };

    wsRef.current = ws;
  }, [simId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const send = useCallback((action: Record<string, any>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(action));
    }
  }, []);

  return { send, connectionState };
}
