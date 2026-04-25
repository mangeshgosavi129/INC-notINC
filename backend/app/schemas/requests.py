from pydantic import BaseModel


class SimulationInitRequest(BaseModel):
    name: str = "Unnamed Run"
    corridor_id: str = "CORR_01"
    controller_type: str = "agent"  # "agent" or "fixed_time"
    duration_s: float = 3600.0
    sim_speed: float = 1.0
    random_seed: int | None = None
    traffic_profile: str = "default"
    start_time_of_day: str = "08:00"


class EVDispatchRequest(BaseModel):
    ev_id: str = "AMB_01"
    vehicle_type: str = "ambulance"
    corridor_id: str = "CORR_01"
    max_speed_kmph: float = 60.0
    start_intersection: str | None = None
    end_intersection: str | None = None


class EVRouteRequest(BaseModel):
    ev_id: str
    corridor_id: str


class BlockageRequest(BaseModel):
    from_intersection: str
    to_intersection: str
    capacity_reduction_pct: float = 50.0
    duration_s: float | None = None


class SignalOverrideRequest(BaseModel):
    intersection_id: str
    target_phase: int
    reason: str = "manual"


class AgentParamsUpdate(BaseModel):
    replan_interval_s: float | None = None
    replan_interval_ev_s: float | None = None
    config: dict | None = None


class ConfigLoadRequest(BaseModel):
    config_type: str  # "intersections", "corridor", "timing", "traffic_profiles", "agent"
    config_json: dict


class SimSpeedRequest(BaseModel):
    speed: float  # 1.0, 2.0, 5.0

    @property
    def validated_speed(self) -> float:
        allowed = {1.0, 2.0, 5.0}
        if self.speed not in allowed:
            closest = min(allowed, key=lambda x: abs(x - self.speed))
            return closest
        return self.speed
