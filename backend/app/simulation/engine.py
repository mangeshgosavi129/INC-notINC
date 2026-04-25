"""Event-driven simulation engine.

Priority-queue-driven loop. Time is float seconds from simulation epoch.
No fixed timestep — state changes ONLY when events fire.
"""

from __future__ import annotations

import asyncio
import heapq
import json
from pathlib import Path
from typing import Any, Protocol

from backend.app.models.corridor import Corridor
from backend.app.models.ev import EVStatus, EmergencyVehicle
from backend.app.models.events import EventType, SimEvent
from backend.app.models.intersection import Intersection
from backend.app.models.signal_controller import SignalControllerState
from backend.app.simulation.clock import SimulationClock
from backend.app.simulation.event_handlers import EVENT_HANDLERS
from backend.app.simulation.queue_model import ApproachQueue, IntersectionQueues
from backend.app.simulation.signal_fsm import SignalFSM
from backend.app.simulation.traffic_profile import TrafficProfile
from backend.app.utils.helpers import gen_id


class Controller(Protocol):
    """Protocol for signal controllers."""
    def decide(self, state: SimulationState, sim_time: float) -> list[SimEvent]: ...


class SimulationState:
    """Complete simulation state — mutated by event handlers."""

    def __init__(
        self,
        intersections: list[Intersection],
        corridor: Corridor,
        traffic_profile: TrafficProfile,
        controller: Controller | None = None,
        start_time_of_day_s: float = 28800.0,  # 08:00
        replan_interval_s: float = 10.0,
        replan_interval_ev_s: float = 5.0,
        snapshot_interval_s: float = 5.0,
    ):
        self.intersections = {ix.intersection_id: ix for ix in intersections}
        self.corridor = corridor
        self.traffic_profile = traffic_profile
        self.controller = controller
        self.start_time_of_day_s = start_time_of_day_s
        self.replan_interval_s = replan_interval_s
        self.replan_interval_ev_s = replan_interval_ev_s
        self.snapshot_interval_s = snapshot_interval_s

        # Signal FSMs
        self.signal_fsms: dict[str, SignalFSM] = {}
        self.signal_states: dict[str, SignalControllerState] = {}
        for ix in intersections:
            ctrl_state = SignalControllerState(intersection_id=ix.intersection_id)
            self.signal_states[ix.intersection_id] = ctrl_state
            self.signal_fsms[ix.intersection_id] = SignalFSM(ix, ctrl_state)

        # Queue model
        self.intersection_queues: dict[str, IntersectionQueues] = {}
        for ix in intersections:
            iq = IntersectionQueues(intersection_id=ix.intersection_id)
            for mov in ix.movements:
                iq.add_approach(mov.movement_id, mov.saturation_flow_vph, mov.lanes)
            self.intersection_queues[ix.intersection_id] = iq

        # EV state
        self.ev: EmergencyVehicle | None = None
        self.ev_wait_start_time: float = 0.0

        # EV sub-corridor (set when EV is dispatched with start/end)
        self.ev_corridor: Corridor | None = None

        # Blockage factors: (from_id, to_id) -> capacity multiplier
        self.blockage_factors: dict[tuple[str, str], float] = {}

        # Metrics collection
        self.metrics_history: list[dict] = []
        self.event_log: list[dict] = []

    def time_of_day(self, sim_time: float) -> float:
        """Convert sim_time to time of day in seconds."""
        return (self.start_time_of_day_s + sim_time) % 86400.0

    def capture_metrics(self, sim_time: float) -> dict:
        """Capture current metrics snapshot."""
        total_queue = 0.0
        max_queue = 0.0
        queue_count = 0
        total_discharged = 0.0

        for iq in self.intersection_queues.values():
            tq = iq.total_queue(sim_time)
            mq = iq.max_queue(sim_time)
            total_queue += tq
            max_queue = max(max_queue, mq)
            queue_count += len(iq.queues)
            total_discharged += iq.total_discharged()

        avg_queue = total_queue / max(1, queue_count)

        ev_progress = 0.0
        if self.ev is not None:
            from backend.app.simulation.ev_movement import compute_ev_progress
            ev_progress = compute_ev_progress(self.ev, self.corridor)

        per_intersection = {}
        for iid, iq in self.intersection_queues.items():
            per_intersection[iid] = {
                "total_queue": round(iq.total_queue(sim_time), 2),
                "max_queue": round(iq.max_queue(sim_time), 2),
                "per_movement": {
                    mid: round(q.get_queue(sim_time), 2)
                    for mid, q in iq.queues.items()
                },
            }

        metrics = {
            "sim_time": sim_time,
            "total_queue_length": round(total_queue, 2),
            "max_queue_length": round(max_queue, 2),
            "avg_queue_length": round(avg_queue, 2),
            "total_throughput": int(total_discharged),
            "ev_progress_pct": round(ev_progress, 1),
            "per_intersection": per_intersection,
        }
        self.metrics_history.append(metrics)
        return metrics

    def get_state_snapshot(self, sim_time: float) -> dict:
        """Full state snapshot for WS broadcast."""
        intersections = []
        for iid, fsm in self.signal_fsms.items():
            iq = self.intersection_queues.get(iid)
            queues = {}
            if iq:
                for mid, q in iq.queues.items():
                    queues[mid] = round(q.get_queue(sim_time), 2)

            intersections.append({
                "intersection_id": iid,
                "phase": fsm.state.current_phase,
                "state": fsm.state.current_state.value,
                "green_movements": list(fsm.green_movements()),
                "queues": queues,
            })

        ev_data = None
        if self.ev is not None:
            ev_data = {
                "ev_id": self.ev.ev_id,
                "status": self.ev.status.value,
                "current_link_index": self.ev.current_link_index,
                "position_on_link": self.ev.position_on_link,
                "total_delay": self.ev.total_delay_at_signals,
                "waiting_at": self.ev.waiting_at_intersection,
            }

        return {
            "sim_time": sim_time,
            "intersections": intersections,
            "ev": ev_data,
        }


class EventDrivenSimulator:
    """Core simulation engine using heapq event loop."""

    def __init__(self, state: SimulationState, end_time: float = 3600.0,
                 seed: int | None = None):
        self.state = state
        self.end_time = end_time
        self.seed = seed
        self.clock = SimulationClock()
        self._event_queue: list[tuple[float, int, SimEvent]] = []
        self._seq = 0
        self._running = False
        self._broadcast_callback: Any = None
        self.processed_events: int = 0

    def set_broadcast_callback(self, callback) -> None:
        self._broadcast_callback = callback

    def schedule(self, event: SimEvent) -> None:
        heapq.heappush(self._event_queue, (event.scheduled_time, self._seq, event))
        self._seq += 1

    def schedule_many(self, events: list[SimEvent]) -> None:
        for e in events:
            self.schedule(e)

    def initialize(self) -> None:
        """Set up initial events: signal starts, traffic shifts, snapshots, replans."""
        # Start all signal FSMs
        import random
        rng = random.Random(self.seed)
        for iid, fsm in self.state.signal_fsms.items():
            events = fsm.start_initial_phase(0.0)
            
            # Apply random offset (-0 to -60s) to phase logic so they aren't artificially synced
            fsm.state.phase_start_time = -rng.uniform(0.0, 60.0)
            
            self.schedule_many(events)

        # Set initial arrival rates
        tod = self.state.time_of_day(0.0)
        rate_vps = self.state.traffic_profile.get_rate_vps(tod)
        for iq in self.state.intersection_queues.values():
            n_approaches = max(1, len(iq.queues))
            per_approach = rate_vps / n_approaches
            for q in iq.queues.values():
                q.arrival_rate = per_approach

        # Traffic profile shift events
        shift_events = self.state.traffic_profile.generate_shift_events(
            self.state.start_time_of_day_s, self.end_time
        )
        self.schedule_many(shift_events)

        # Congestion snapshot events
        self.schedule(SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.CONGESTION_SNAPSHOT,
            scheduled_time=self.state.snapshot_interval_s,
            payload={},
            source="simulation",
        ))

        # Dynamic controller replan trigger (if controller is set)
        if self.state.controller is not None:
            self.schedule(SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.AGENT_REPLAN_TRIGGER,
                scheduled_time=self.state.replan_interval_s,
                payload={},
                source="simulation",
            ))

    def step(self) -> SimEvent | None:
        """Process one event. Returns the processed event or None if done."""
        if not self._event_queue:
            return None

        time, _, event = heapq.heappop(self._event_queue)
        if time > self.end_time:
            return None

        self.clock.advance_to(time)

        handler = EVENT_HANDLERS.get(event.event_type)
        if handler is not None:
            new_events = handler(self.state, event)
            self.schedule_many(new_events)

        self.processed_events += 1

        # Log event
        self.state.event_log.append({
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "sim_time": time,
            "payload": event.payload,
        })

        return event

    def run_to_completion(self) -> None:
        """Run all events until end_time or queue empty."""
        self._running = True
        while self._running and self._event_queue:
            event = self.step()
            if event is None:
                break

    async def run_realtime(self) -> None:
        """Run with real-time pacing and WS broadcast support."""
        self._running = True
        last_broadcast_time = 0.0
        broadcast_interval = 1.0 / max(1, self.state.snapshot_interval_s)

        while self._running and self._event_queue:
            if self.clock.paused:
                await asyncio.sleep(0.1)
                continue

            event = self.step()
            if event is None:
                break

            # Broadcast periodically to keep clients updated
            time_since_broadcast = self.clock.sim_time - last_broadcast_time

            if self._broadcast_callback and time_since_broadcast >= 0.5:
                snapshot = self.state.get_state_snapshot(self.clock.sim_time)
                await self._broadcast_callback(snapshot)
                last_broadcast_time = self.clock.sim_time

            # Pace simulation
            if self._event_queue:
                next_time = self._event_queue[0][0]
                sim_delta = next_time - self.clock.sim_time
                if sim_delta > 0:
                    wall_delay = self.clock.wall_delay_for_sim_delta(sim_delta)
                    if wall_delay > 0.001:  # Don't sleep for tiny delays
                        await asyncio.sleep(min(wall_delay, 0.1))

    def stop(self) -> None:
        self._running = False

    def dispatch_ev(self, ev_id: str, vehicle_type: str,
                    corridor_id: str, max_speed_kmph: float,
                    sim_time: float,
                    start_intersection: str | None = None,
                    end_intersection: str | None = None) -> None:
        """Dispatch an emergency vehicle onto the corridor."""
        from backend.app.simulation.ev_movement import dispatch_ev

        ev = EmergencyVehicle(
            ev_id=ev_id,
            vehicle_type=vehicle_type,
            corridor_id=corridor_id,
            max_speed_kmph=max_speed_kmph,
        )
        self.state.ev = ev
        events, effective_corridor = dispatch_ev(
            ev, self.state.corridor, sim_time,
            start_intersection, end_intersection,
        )
        # Use sub-corridor for EV traversal
        self.state.ev_corridor = effective_corridor
        self.schedule_many(events)

    @property
    def sim_time(self) -> float:
        return self.clock.sim_time

    @property
    def event_count(self) -> int:
        return len(self._event_queue)


def load_default_config() -> tuple[list[Intersection], Corridor, TrafficProfile]:
    """Load default Pune corridor configuration from JSON files."""
    from backend.app.config import settings

    data_dir = settings.data_dir

    with open(data_dir / "pune_default_intersections.json") as f:
        ix_data = json.load(f)
    intersections = [Intersection(**ix) for ix in ix_data["intersections"]]

    with open(data_dir / "pune_default_corridor.json") as f:
        corr_data = json.load(f)
    corridor = Corridor(**corr_data["corridor"])

    with open(data_dir / "pune_traffic_profiles.json") as f:
        prof_data = json.load(f)
    profile = TrafficProfile(prof_data["profiles"]["default"])

    return intersections, corridor, profile
