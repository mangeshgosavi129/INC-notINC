import { useRef, useState, useCallback, useEffect } from 'react';

interface WSMessage {
  type: string;
  data: Record<string, any>;
  sim_time?: number;
}

export function useDriverWebSocket(simId: string | null, evId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const [connectionState, setConnectionState] = useState<'connecting' | 'open' | 'closed'>('closed');
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  const connect = useCallback(() => {
    if (!simId || !evId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = `${protocol}//${window.location.host}`;
    const ws = new WebSocket(`${host}/ws/driver/${simId}/${evId}`);

    setConnectionState('connecting');

    ws.onopen = () => setConnectionState('open');

    ws.onmessage = (e) => {
      try {
        setLastMessage(JSON.parse(e.data));
      } catch { /* ignore */ }
    };

    ws.onclose = () => {
      setConnectionState('closed');
      wsRef.current = null;
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    wsRef.current = ws;
  }, [simId, evId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { lastMessage, connectionState };
}
