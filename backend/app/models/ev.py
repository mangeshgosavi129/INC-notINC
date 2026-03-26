from enum import Enum

from pydantic import BaseModel


class EVStatus(str, Enum):
    IDLE = "idle"
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    WAITING_AT_SIGNAL = "waiting_at_signal"
    TRAVERSING_INTERSECTION = "traversing_intersection"
    ARRIVED = "arrived"


class EmergencyVehicle(BaseModel):
    ev_id: str
    vehicle_type: str = "ambulance"  # "ambulance", "fire", "police"
    corridor_id: str
    current_link_index: int = 0
    position_on_link: float = 0.0    # 0.0 to 1.0
    speed_kmph: float = 0.0
    max_speed_kmph: float = 60.0
    status: EVStatus = EVStatus.IDLE
    dispatch_time: float | None = None
    arrival_time: float | None = None
    total_delay_at_signals: float = 0.0
    route: list[str] = []            # ordered intersection_ids
    waiting_at_intersection: str | None = None
    intersections_cleared: int = 0
    intersections_waited: int = 0
