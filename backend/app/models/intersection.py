from pydantic import BaseModel


class Movement(BaseModel):
    movement_id: str          # e.g. "NBT" (northbound through)
    from_approach: str        # "N", "S", "E", "W"
    to_approach: str
    movement_type: str        # "through", "left", "right"
    lanes: int
    saturation_flow_vph: float = 1800.0  # per lane


class Phase(BaseModel):
    phase_id: int             # NEMA phase (1-8)
    served_movements: list[str]
    min_green: float          # seconds, typ 7-15
    max_green: float          # seconds, typ 30-60
    amber: float = 3.0
    all_red: float = 2.0


class Ring(BaseModel):
    ring_id: int
    phase_sequence: list[int]


class Intersection(BaseModel):
    intersection_id: str
    name: str
    lat: float | None = None
    lon: float | None = None
    approaches: list[str]
    movements: list[Movement]
    phases: list[Phase]
    rings: list[Ring]

    def get_phase(self, phase_id: int) -> Phase:
        for p in self.phases:
            if p.phase_id == phase_id:
                return p
        raise ValueError(f"Phase {phase_id} not found in {self.intersection_id}")

    def get_next_phase(self, current_phase_id: int, ring_id: int = 1) -> int:
        ring = next(r for r in self.rings if r.ring_id == ring_id)
        seq = ring.phase_sequence
        idx = seq.index(current_phase_id)
        return seq[(idx + 1) % len(seq)]

    def get_phase_for_movement(self, movement_id: str) -> Phase | None:
        for p in self.phases:
            if movement_id in p.served_movements:
                return p
        return None
