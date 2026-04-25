// Mirrors backend engine.py get_state_snapshot() lines 120-136
export interface IntersectionState {
  intersection_id: string;
  phase: number;
  state: 'GREEN' | 'AMBER' | 'ALL_RED';
  green_movements: string[];
  queues: Record<string, number>;
}

// Mirrors engine.py lines 138-147
export interface EVState {
  ev_id: string;
  status: 'idle' | 'dispatched' | 'en_route' | 'waiting_at_signal' | 'traversing_intersection' | 'arrived';
  current_link_index: number;
  position_on_link: number;
  total_delay: number;
  waiting_at: string | null;
}

// Mirrors engine.py capture_metrics() lines 109-116
export interface MetricsSnapshot {
  sim_time: number;
  total_queue_length: number;
  max_queue_length: number;
  avg_queue_length: number;
  total_throughput: number;
  ev_progress_pct: number;
}

// Mirrors simulation_service.py get_state() lines 153-168
export interface SimulationState {
  run_id: string;
  status: string;
  sim_time: number;
  wall_clock_elapsed: number;
  controller_type: string;
  corridor_id: string;
  intersections: IntersectionState[];
  ev: EVState | null;
  metrics: MetricsSnapshot;
}

// Mirrors simulation_service.py get_ev_status() lines 182-202
export interface EVStatusFull {
  ev_id: string;
  status: string;
  vehicle_type: string;
  corridor_id: string;
  current_link_index: number;
  position_on_link: number;
  speed_kmph: number;
  total_delay: number;
  intersections_cleared: number;
  intersections_waited: number;
  progress_pct: number;
  eta_s: number | null;
  waiting_at: string | null;
}

export interface AgentDecision {
  decision_id: string;
  sim_time: number;
  actions: Record<string, { action_type: string; target_phase?: number }>;
  status: string;
  message: string;
  computation_ms: number;
}

export interface WSMessage {
  type: 'state_update' | 'agent_decision' | 'ev_status_change' | 'metrics_snapshot' | 'signal_phase_change' | 'alert' | 'ack' | 'error';
  data: Record<string, any>;
  sim_time?: number;
}

export interface ComparisonResult {
  pair_id: string;
  agent_ev_delay: number;
  baseline_ev_delay: number;
  ev_delay_improvement_pct: number;
  agent_avg_queue: number;
  baseline_avg_queue: number;
  queue_improvement_pct: number;
  agent_throughput: number;
  baseline_throughput: number;
  throughput_improvement_pct: number;
}

export interface SimulationInitParams {
  name?: string;
  corridor_id?: string;
  controller_type?: 'agent' | 'fixed_time';
  duration_s?: number;
  sim_speed?: number;
  random_seed?: number;
  traffic_profile?: string;
  start_time_of_day?: string;
}

export interface Alert {
  type: 'high_queue' | 'ev_delay' | 'blockage';
  severity: 'warning' | 'critical';
  intersection_id?: string;
  queue_length?: number;
  ev_id?: string;
  total_delay?: number;
  from?: string;
  to?: string;
  capacity_factor?: number;
  message?: string;
}

export interface IntersectionConfig {
  intersection_id: string;
  name: string;
  lat: number;
  lon: number;
  approaches: string[];
  movements: Array<{
    movement_id: string;
    from_approach: string;
    to_approach: string;
    movement_type: string;
    lanes: number;
    saturation_flow_vph: number;
  }>;
  phases: Array<{
    phase_id: number;
    served_movements: string[];
    min_green: number;
    max_green: number;
    amber: number;
    all_red: number;
  }>;
}

export interface LinkConfig {
  from_intersection: string;
  to_intersection: string;
  length_meters: number;
  free_flow_speed_kmph: number;
  num_lanes: number;
  capacity_vph: number;
  ev_approach_movement: string;
}

export interface CorridorConfig {
  corridor_id: string;
  name: string;
  intersection_ids: string[];
  links: LinkConfig[];
}

export interface SimRun {
  run_id: string;
  name: string;
  controller_type: string;
  status: string;
  sim_time: number;
  corridor_id: string;
}
