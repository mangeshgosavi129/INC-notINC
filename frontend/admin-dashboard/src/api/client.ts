import type {
  SimulationInitParams,
  SimulationState,
  MetricsSnapshot,
  MCTSDecision,
  ComparisonResult,
  Alert,
  IntersectionConfig,
  CorridorConfig,
  SimRun,
} from '../types';

const BASE = import.meta.env.VITE_API_URL ?? '';

async function request<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
}

// ── Simulation lifecycle ──
export const initSimulation = (params: SimulationInitParams) =>
  post<{ run_id: string; status: string; message: string }>('/api/simulation/init', params);

export const startSimulation = (runId: string) =>
  post<{ run_id: string; status: string }>(`/api/simulation/start/${runId}`);

export const pauseSimulation = (runId: string) =>
  post<{ run_id: string; status: string }>(`/api/simulation/pause/${runId}`);

export const resumeSimulation = (runId: string) =>
  post<{ run_id: string; status: string }>(`/api/simulation/resume/${runId}`);

export const resetSimulation = (runId: string) =>
  post<{ run_id: string; status: string }>(`/api/simulation/reset/${runId}`);

export const runSimulation = (runId: string) =>
  post<{ run_id: string; status: string }>(`/api/simulation/run/${runId}`);

export const stepSimulation = (runId: string) =>
  post<{ run_id: string; status: string; event: Record<string, any> | null }>(`/api/simulation/step/${runId}`);

export const setSpeed = (runId: string, speed: number) =>
  post<{ run_id: string; speed: number }>(`/api/simulation/speed/${runId}`, { speed });

// ── State ──
export const getState = (runId: string) =>
  request<SimulationState>(`/api/simulation/state/${runId}`);

export const getMetrics = (runId: string) =>
  request<MetricsSnapshot[]>(`/api/simulation/metrics/${runId}`);

export const getEventHistory = (runId: string, limit = 500) =>
  request<Record<string, any>[]>(`/api/simulation/history/${runId}?limit=${limit}`);

// ── EV ──
export const dispatchEV = (runId: string, params?: {
  ev_id?: string; vehicle_type?: string; corridor_id?: string; max_speed_kmph?: number;
  start_intersection?: string; end_intersection?: string;
}) =>
  post<Record<string, any>>(`/api/ev/dispatch/${runId}`, params ?? {});

export const getEVStatus = (runId: string) =>
  request<Record<string, any>>(`/api/ev/status/${runId}`);

// ── MCTS Control ──
export const getDecisionLog = (runId: string) =>
  request<MCTSDecision[]>(`/api/control/decision-log/${runId}`);

export const explainLastDecision = (runId: string) =>
  request<{ decision: Record<string, any>; explanation: string }>(`/api/control/explain-last-decision/${runId}`);

export const forceDecision = (runId: string) =>
  post<Record<string, any>>(`/api/control/decide/${runId}`);

export const setBaseline = (runId: string) =>
  post<Record<string, any>>(`/api/control/set-baseline/${runId}`);

export const setMCTS = (runId: string) =>
  post<Record<string, any>>(`/api/control/set-mcts/${runId}`);

// ── Config ──
export const getConfig = () =>
  request<Record<string, any>>('/api/config');

export const loadConfig = (configType: string, configJson: unknown) =>
  post<{ status: string }>('/api/config/load', { config_type: configType, config_json: configJson });

export const resetConfig = () =>
  post<{ status: string }>('/api/config/reset');

export const getIntersections = () =>
  request<IntersectionConfig[]>('/api/intersections');

export const getCorridors = () =>
  request<CorridorConfig[]>('/api/corridors');

// ── Admin ──
export const createBlockage = (runId: string, params: {
  from_intersection: string; to_intersection: string;
  capacity_reduction_pct?: number; duration_s?: number;
}) =>
  post<Record<string, any>>(`/api/admin/blockage/${runId}`, params);

export const removeBlockage = (runId: string, from: string, to: string) =>
  post<Record<string, any>>(`/api/admin/unblock/${runId}?from_intersection=${from}&to_intersection=${to}`);

export const overrideSignal = (runId: string, params: {
  intersection_id: string; target_phase: number; reason?: string;
}) =>
  post<Record<string, any>>(`/api/admin/override-signal/${runId}`, params);

export const getControlRoom = (runId: string) =>
  request<Record<string, any>>(`/api/admin/control-room/${runId}`);

export const getAlerts = (runId: string) =>
  request<Alert[]>(`/api/admin/alerts/${runId}`);

// ── Analytics ──
export const getQueueHistory = (runId: string) =>
  request<Record<string, any>>(`/api/analytics/queue/${runId}`);

export const getDelayHistory = (runId: string) =>
  request<Record<string, any>>(`/api/analytics/delay/${runId}`);

export const getThroughputHistory = (runId: string) =>
  request<Record<string, any>>(`/api/analytics/throughput/${runId}`);

export const getEVJourney = (runId: string) =>
  request<Record<string, any>>(`/api/analytics/ev-journey/${runId}`);

export const compareBaseline = (mctsRunId: string, baselineRunId: string) =>
  request<ComparisonResult>(`/api/analytics/compare-baseline?mcts_run_id=${mctsRunId}&baseline_run_id=${baselineRunId}`);

export const getPlotsData = (runId: string) =>
  request<Record<string, any>>(`/api/analytics/plots/${runId}`);

// ── Runs ──
export const listSimulations = () =>
  request<SimRun[]>('/api/simulation/list');

export const exportRun = (runId: string) =>
  request<Record<string, any>>(`/api/simulation/export/${runId}`);

// ── Health ──
export const getHealth = () =>
  request<{ status: string; version: string; viz_mode: string }>('/api/health');
