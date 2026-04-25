import { useState, useCallback, useEffect, useRef } from 'react';
import type { SimulationState, MetricsSnapshot, AgentDecision, Alert, WSMessage } from '../types';
import { useAdminWebSocket } from './useAdminWebSocket';
import { getState, getMetrics, getDecisionLog } from '../api/client';

interface SimStateHook {
  state: SimulationState | null;
  metricsHistory: MetricsSnapshot[];
  decisions: AgentDecision[];
  alerts: Alert[];
  isConnected: boolean;
}

export function useSimState(runId: string | null): SimStateHook {
  const [state, setState] = useState<SimulationState | null>(null);
  const [metricsHistory, setMetricsHistory] = useState<MetricsSnapshot[]>([]);
  const [decisions, setDecisions] = useState<AgentDecision[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case 'state_update':
        setState((prev) => {
          const simTime = msg.sim_time ?? msg.data?.sim_time ?? 0;
          const intersections = msg.data?.intersections ?? prev?.intersections ?? [];
          const ev = msg.data?.ev !== undefined ? msg.data.ev : (prev?.ev ?? null);
          if (!prev) {
            return {
              run_id: '',
              status: 'running',
              sim_time: simTime,
              wall_clock_elapsed: 0,
              controller_type: '',
              corridor_id: '',
              intersections,
              ev,
              metrics: {} as MetricsSnapshot,
            };
          }
          return { ...prev, sim_time: simTime, intersections, ev };
        });
        break;
      case 'metrics_snapshot':
        if (msg.data) {
          setMetricsHistory((prev) => [...prev.slice(-199), msg.data as MetricsSnapshot]);
        }
        break;
      case 'agent_decision':
        if (msg.data) {
          setDecisions((prev) => [...prev, msg.data as AgentDecision]);
        }
        break;
      case 'alert':
        if (msg.data) {
          setAlerts((prev) => [...prev.slice(-49), msg.data as Alert]);
        }
        break;
      case 'ev_status_change':
        setState((prev) => {
          if (!prev) return prev;
          return { ...prev, ev: msg.data as any };
        });
        break;
    }
  }, []);

  const { connectionState } = useAdminWebSocket(runId, handleMessage);

  // Poll REST for full state — this is the primary data source
  useEffect(() => {
    if (!runId) {
      setState(null);
      setMetricsHistory([]);
      setDecisions([]);
      setAlerts([]);
      return;
    }

    let active = true;

    const fetchState = async () => {
      if (!active) return;
      try {
        const s = await getState(runId);
        if (active) setState(s);
      } catch { /* ignore */ }
    };

    const fetchMetrics = async () => {
      if (!active) return;
      try {
        const m = await getMetrics(runId);
        if (active && m.length > 0) setMetricsHistory(m);
      } catch { /* ignore */ }
    };

    const fetchDecisions = async () => {
      if (!active) return;
      try {
        const d = await getDecisionLog(runId);
        if (active && d.length > 0) setDecisions(d);
      } catch { /* ignore */ }
    };

    // Fetch immediately
    fetchState();
    fetchMetrics();
    fetchDecisions();

    // Poll every 1s
    pollRef.current = setInterval(() => {
      fetchState();
      fetchMetrics();
      fetchDecisions();
    }, 1000);

    return () => {
      active = false;
      clearInterval(pollRef.current);
    };
  }, [runId]);

  return {
    state,
    metricsHistory,
    decisions,
    alerts,
    isConnected: connectionState === 'open',
  };
}
