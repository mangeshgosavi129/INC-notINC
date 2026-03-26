"""Lazy queue model — queue length computed on demand, not every tick.

Each approach link tracks:
- queue_length (vehicles)
- arrival_rate (veh/s)
- is_green (whether this approach currently has green)
- saturation_flow_rate (veh/s per lane × lanes)
- last_update_time
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ApproachQueue:
    intersection_id: str
    movement_id: str
    queue_length: float = 0.0
    arrival_rate: float = 0.0       # veh/s
    saturation_flow_rate: float = 1.0  # veh/s (total across lanes)
    is_green: bool = False
    last_update_time: float = 0.0
    total_discharged: float = 0.0   # cumulative vehicles discharged

    def materialize(self, now: float) -> float:
        """Compute current queue length using lazy evaluation."""
        dt = now - self.last_update_time
        if dt <= 0:
            return self.queue_length

        if self.is_green:
            net_rate = self.arrival_rate - self.saturation_flow_rate
        else:
            net_rate = self.arrival_rate

        new_queue = self.queue_length + net_rate * dt

        # Track discharge
        if self.is_green and net_rate < 0:
            discharged = min(self.queue_length, abs(net_rate) * dt)
            self.total_discharged += discharged

        self.queue_length = max(0.0, new_queue)
        self.last_update_time = now
        return self.queue_length

    def set_green(self, now: float) -> None:
        self.materialize(now)
        self.is_green = True

    def set_red(self, now: float) -> None:
        self.materialize(now)
        self.is_green = False

    def set_arrival_rate(self, rate_vps: float, now: float) -> None:
        self.materialize(now)
        self.arrival_rate = rate_vps

    def get_queue(self, now: float) -> float:
        return self.materialize(now)


@dataclass
class IntersectionQueues:
    intersection_id: str
    queues: dict[str, ApproachQueue] = field(default_factory=dict)

    def add_approach(self, movement_id: str, saturation_flow_vph: float,
                     lanes: int) -> ApproachQueue:
        sat_flow = (saturation_flow_vph * lanes) / 3600.0  # convert to veh/s
        q = ApproachQueue(
            intersection_id=self.intersection_id,
            movement_id=movement_id,
            saturation_flow_rate=sat_flow,
        )
        self.queues[movement_id] = q
        return q

    def get_queue(self, movement_id: str, now: float) -> float:
        if movement_id not in self.queues:
            return 0.0
        return self.queues[movement_id].get_queue(now)

    def total_queue(self, now: float) -> float:
        return sum(q.get_queue(now) for q in self.queues.values())

    def max_queue(self, now: float) -> float:
        if not self.queues:
            return 0.0
        return max(q.get_queue(now) for q in self.queues.values())

    def total_discharged(self) -> float:
        return sum(q.total_discharged for q in self.queues.values())

    def update_green_phases(self, green_movements: set[str], now: float) -> None:
        """Update which movements have green."""
        for mid, q in self.queues.items():
            if mid in green_movements:
                q.set_green(now)
            else:
                q.set_red(now)
