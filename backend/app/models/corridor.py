from pydantic import BaseModel


class CorridorLink(BaseModel):
    from_intersection: str
    to_intersection: str
    length_meters: float
    free_flow_speed_kmph: float
    num_lanes: int
    capacity_vph: float
    ev_approach_movement: str  # movement_id EV uses at to_intersection


class Corridor(BaseModel):
    corridor_id: str
    name: str
    intersection_ids: list[str]
    links: list[CorridorLink]

    def get_link(self, from_id: str, to_id: str) -> CorridorLink | None:
        for link in self.links:
            if link.from_intersection == from_id and link.to_intersection == to_id:
                return link
        return None

    def free_flow_travel_time_s(self) -> float:
        total = 0.0
        for link in self.links:
            speed_mps = link.free_flow_speed_kmph * 1000.0 / 3600.0
            total += link.length_meters / speed_mps
        return total
