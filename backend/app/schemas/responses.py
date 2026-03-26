from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    error_code: str


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class SimulationStateResponse(BaseModel):
    run_id: str
    status: str
    sim_time: float
    wall_clock_elapsed: float
    controller_type: str
    corridor_id: str
    intersections: list[dict]
    ev: dict | None = None
    metrics: dict


class SimulationInitResponse(BaseModel):
    run_id: str
    status: str
    message: str


class EVStatusResponse(BaseModel):
    ev_id: str
    status: str
    corridor_id: str
    current_intersection: str | None = None
    position_pct: float
    speed_kmph: float
    total_delay: float
    eta_s: float | None = None


class MCTSDecisionResponse(BaseModel):
    decision_id: str
    sim_time: float
    actions: dict
    reward: float
    iterations: int
    computation_ms: float


class ComparisonResponse(BaseModel):
    pair_id: str
    mcts_ev_delay: float
    baseline_ev_delay: float
    ev_delay_improvement_pct: float
    mcts_avg_queue: float
    baseline_avg_queue: float
    queue_improvement_pct: float
    mcts_throughput: int
    baseline_throughput: int
    throughput_improvement_pct: float


class DriverStatusResponse(BaseModel):
    ev_id: str
    status: str
    current_instruction: str  # "PROCEED", "WAIT", "SLOW_DOWN"
    next_intersection: str | None = None
    next_signal_state: str | None = None
    time_to_green_s: float | None = None
    eta_destination_s: float | None = None
    progress_pct: float
    journey_stats: dict | None = None


class PaginatedResponse(BaseModel):
    items: list[dict]
    total: int
    offset: int
    limit: int
