from pydantic import BaseModel


class WSMessage(BaseModel):
    type: str
    data: dict
    sim_time: float | None = None


# --- Admin WS: Server → Client ---

class StateUpdateMessage(WSMessage):
    type: str = "state_update"


class MCTSDecisionMessage(WSMessage):
    type: str = "mcts_decision"


class EVStatusChangeMessage(WSMessage):
    type: str = "ev_status_change"


class MetricsSnapshotMessage(WSMessage):
    type: str = "metrics_snapshot"


class SignalPhaseChangeMessage(WSMessage):
    type: str = "signal_phase_change"


class AlertMessage(WSMessage):
    type: str = "alert"


# --- Admin WS: Client → Server ---

class DispatchEVCommand(BaseModel):
    action: str = "dispatch_ev"
    ev_id: str
    vehicle_type: str = "ambulance"
    corridor_id: str = "CORR_01"


class SetSimSpeedCommand(BaseModel):
    action: str = "set_sim_speed"
    speed: float


class SimControlCommand(BaseModel):
    action: str  # "pause", "resume", "stop"


class OverrideSignalCommand(BaseModel):
    action: str = "override_signal"
    intersection_id: str
    target_phase: int


# --- Driver WS: Server → Client ---

class RouteUpdateMessage(WSMessage):
    type: str = "route_update"


class SignalAheadMessage(WSMessage):
    type: str = "signal_ahead"


class InstructionMessage(WSMessage):
    type: str = "instruction"


class ArrivalMessage(WSMessage):
    type: str = "arrival"
