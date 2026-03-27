import React, { createContext, useContext } from 'react';
import { useSimulation } from '../hooks/useSimulation';
import { useSimState } from '../hooks/useSimState';
import type { SimulationState, MetricsSnapshot, MCTSDecision, Alert } from '../types';
import type { SimStatus } from '../hooks/useSimulation';

interface SimContextValue {
  // from useSimulation
  runId: string | null;
  simStatus: SimStatus;
  error: string | null;
  initSim: ReturnType<typeof useSimulation>['initSim'];
  startSim: (overrideId?: string) => Promise<void>;
  pauseSim: () => Promise<void>;
  resumeSim: () => Promise<void>;
  resetSim: () => Promise<void>;
  changeSpeed: (speed: number) => Promise<void>;
  dispatchEV: (params?: { ev_id?: string; vehicle_type?: string; corridor_id?: string; max_speed_kmph?: number; start_intersection?: string; end_intersection?: string }) => Promise<void>;
  loadRun: (id: string) => void;
  // from useSimState
  state: SimulationState | null;
  metricsHistory: MetricsSnapshot[];
  decisions: MCTSDecision[];
  alerts: Alert[];
  isConnected: boolean;
}

const SimContext = createContext<SimContextValue | null>(null);

export function SimulationProvider({ children }: { children: React.ReactNode }) {
  const sim = useSimulation();
  const simState = useSimState(sim.runId);

  const value: SimContextValue = {
    ...sim,
    ...simState,
  };

  return <SimContext.Provider value={value}>{children}</SimContext.Provider>;
}

export function useSimContext(): SimContextValue {
  const ctx = useContext(SimContext);
  if (!ctx) throw new Error('useSimContext must be used within SimulationProvider');
  return ctx;
}
