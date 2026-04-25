from pydantic import BaseModel


class MetricsSnapshot(BaseModel):
    snapshot_id: str
    run_id: str
    sim_time: float
    total_queue_length: float = 0.0
    max_queue_length: float = 0.0
    avg_queue_length: float = 0.0
    total_throughput: int = 0
    avg_delay_per_vehicle: float = 0.0
    ev_progress_pct: float = 0.0
    corridor_avg_speed: float = 0.0
    per_intersection: dict = {}


class ComparisonResult(BaseModel):
    pair_id: str
    agent_run_id: str
    baseline_run_id: str
    agent_ev_delay: float
    baseline_ev_delay: float
    ev_delay_improvement_pct: float
    agent_avg_queue: float
    baseline_avg_queue: float
    queue_improvement_pct: float
    agent_throughput: int
    baseline_throughput: int
    throughput_improvement_pct: float
