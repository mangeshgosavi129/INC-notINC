export interface DirectionInfo {
  current_link: string | null;
  distance_remaining_m: number;
  next_intersection_name: string;
  total_distance_remaining_m: number;
  heading: string;
}

// Mirrors driver_routes.py /status response (lines 45-54)
export interface DriverStatus {
  ev_id: string;
  status: string;
  instruction: 'PROCEED' | 'STOP' | 'SLOW_DOWN' | 'STANDBY';
  next_intersection: string | null;
  next_signal_state: string | null;
  time_to_green_s: number | null;
  eta_destination_s: number | null;
  progress_pct: number;
  directions?: DirectionInfo | null;
  start_node: string | null;
  destination_node: string | null;
}

// Mirrors /route response (lines 70-78)
export interface RouteLink {
  index: number;
  from: string;
  to: string;
  distance_m: number;
  intersection_name: string;
  signal_state: string;
  signal_phase: number | null;
}

// Mirrors /clearance response (lines 107-112)
export interface ClearanceInfo {
  intersection_id: string;
  signal_green: boolean;
  ev_cleared: boolean;
  ev_waiting: boolean;
}

// Mirrors /eta response (lines 132-136)
export interface ETAInfo {
  eta_s: number | null;
  free_flow_eta_s: number | null;
  progress_pct: number;
}

// Mirrors /live-corridor response (lines 152-168)
export interface LiveIntersection {
  intersection_id: string;
  name: string;
  signal_state: string;
  green_movements: string[];
  total_queue: number;
}

export interface LiveCorridor {
  start_node: string | null;
  destination_node: string | null;
  intersections: LiveIntersection[];
  ev: {
    position_link_index: number;
    position_on_link: number;
    status: string;
  } | null;
}

export interface EVJourneySummary {
  ev_id: string;
  free_flow_time_s: number;
  actual_time_s: number;
  total_signal_delay_s: number;
  intersections_cleared: number;
  intersections_waited: number;
}
