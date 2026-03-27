import { useState, useCallback } from 'react';
import type { SimulationInitParams } from '../types';
import * as api from '../api/client';

export type SimStatus = 'idle' | 'initialized' | 'running' | 'paused' | 'complete' | 'error';

export function useSimulation() {
  const [runId, setRunId] = useState<string | null>(null);
  const [simStatus, setSimStatus] = useState<SimStatus>('idle');
  const [error, setError] = useState<string | null>(null);

  const initSim = useCallback(async (params: SimulationInitParams = {}) => {
    try {
      setError(null);
      const res = await api.initSimulation(params);
      setRunId(res.run_id);
      setSimStatus('initialized');
      return res.run_id;
    } catch (e: any) {
      setError(e.message);
      setSimStatus('error');
      return null;
    }
  }, []);

  const startSim = useCallback(async (overrideId?: string) => {
    const id = overrideId ?? runId;
    if (!id) return;
    try {
      await api.startSimulation(id);
      setSimStatus('running');
    } catch (e: any) {
      setError(e.message);
    }
  }, [runId]);

  const pauseSim = useCallback(async () => {
    if (!runId) return;
    try {
      await api.pauseSimulation(runId);
      setSimStatus('paused');
    } catch (e: any) {
      setError(e.message);
    }
  }, [runId]);

  const resumeSim = useCallback(async () => {
    if (!runId) return;
    try {
      await api.resumeSimulation(runId);
      setSimStatus('running');
    } catch (e: any) {
      setError(e.message);
    }
  }, [runId]);

  const resetSim = useCallback(async () => {
    if (!runId) return;
    try {
      await api.resetSimulation(runId);
      setSimStatus('idle');
      setRunId(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [runId]);

  const changeSpeed = useCallback(async (speed: number) => {
    if (!runId) return;
    try {
      await api.setSpeed(runId, speed);
    } catch (e: any) {
      setError(e.message);
    }
  }, [runId]);

  const dispatchEV = useCallback(async (params?: {
    ev_id?: string; vehicle_type?: string; corridor_id?: string; max_speed_kmph?: number;
    start_intersection?: string; end_intersection?: string;
  }) => {
    if (!runId) return;
    try {
      await api.dispatchEV(runId, params);
    } catch (e: any) {
      setError(e.message);
    }
  }, [runId]);

  const loadRun = useCallback((id: string) => {
    setRunId(id);
    setSimStatus('running');
  }, []);

  return {
    runId,
    simStatus,
    error,
    initSim,
    startSim,
    pauseSim,
    resumeSim,
    resetSim,
    changeSpeed,
    dispatchEV,
    loadRun,
  };
}
