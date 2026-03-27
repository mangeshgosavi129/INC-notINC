import { useState, useEffect, useRef } from 'react';
import type { DriverStatus, LiveCorridor, ETAInfo } from '../types';
import { useDriverWebSocket } from './useDriverWebSocket';

const BASE = import.meta.env.VITE_API_URL ?? '';

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export function useDriverState(simId: string | null, evId: string | null, onSimLost?: () => void) {
  const [status, setStatus] = useState<DriverStatus | null>(null);
  const [corridor, setCorridor] = useState<LiveCorridor | null>(null);
  const [eta, setEta] = useState<ETAInfo | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval>>();
  const failCount = useRef(0);

  const { lastMessage, connectionState } = useDriverWebSocket(simId, evId);

  useEffect(() => {
    if (!simId) return;
    failCount.current = 0;

    const poll = async () => {
      try {
        const [s, c, e] = await Promise.all([
          fetchJSON<DriverStatus>(`/api/driver/status/${simId}`),
          fetchJSON<LiveCorridor>(`/api/driver/live-corridor/${simId}`),
          fetchJSON<ETAInfo>(`/api/driver/eta/${simId}`),
        ]);
        setStatus(s);
        setCorridor(c);
        setEta(e);
        failCount.current = 0;
      } catch {
        failCount.current++;
        // If simulation is gone for 5+ consecutive polls, notify parent
        if (failCount.current >= 5 && onSimLost) {
          onSimLost();
        }
      }
    };

    poll();
    pollRef.current = setInterval(poll, 1000);
    return () => clearInterval(pollRef.current);
  }, [simId]);

  return { status, corridor, eta, isConnected: connectionState === 'open' };
}
