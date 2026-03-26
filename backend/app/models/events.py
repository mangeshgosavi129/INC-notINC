from enum import Enum

from pydantic import BaseModel


class EventType(str, Enum):
    # Signal events
    SIGNAL_PHASE_START = "signal_phase_start"
    SIGNAL_MIN_GREEN_EXPIRE = "signal_min_green_expire"
    SIGNAL_MAX_GREEN_EXPIRE = "signal_max_green_expire"
    SIGNAL_AMBER_START = "signal_amber_start"
    SIGNAL_AMBER_END = "signal_amber_end"
    SIGNAL_ALL_RED_START = "signal_all_red_start"
    SIGNAL_ALL_RED_END = "signal_all_red_end"

    # Traffic events
    VEHICLE_ARRIVAL = "vehicle_arrival"
    QUEUE_DISCHARGE_TICK = "queue_discharge_tick"

    # EV events
    EV_DEPART_ORIGIN = "ev_depart_origin"
    EV_ARRIVE_INTERSECTION = "ev_arrive_intersection"
    EV_ENTER_INTERSECTION = "ev_enter_intersection"
    EV_REACH_DESTINATION = "ev_reach_destination"

    # MCTS events
    MCTS_REPLAN_TRIGGER = "mcts_replan_trigger"

    # Monitoring events
    CONGESTION_SNAPSHOT = "congestion_snapshot"
    TRAFFIC_PROFILE_SHIFT = "traffic_profile_shift"

    # Scenario events
    BLOCKAGE_START = "blockage_start"
    BLOCKAGE_END = "blockage_end"
    CONGESTION_SPIKE = "congestion_spike"


class SimEvent(BaseModel):
    event_id: str
    event_type: EventType
    scheduled_time: float
    payload: dict
    source: str = "simulation"  # "simulation", "mcts", "user", "baseline"

    def __lt__(self, other: "SimEvent") -> bool:
        return self.scheduled_time < other.scheduled_time
