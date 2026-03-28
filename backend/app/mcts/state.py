"""MCTS State — compact, hashable snapshots for tree search.

Uses frozen dataclasses with tuples so states can be used as dict keys
and compared efficiently.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntersectionSnapshot:
    intersection_id: str
    current_phase: int
    phase_elapsed: float
    phase_state: str          # "GREEN", "AMBER", "ALL_RED"
    time_to_phase_end: float
    queue_lengths: tuple[float, ...]   # one per movement
    arrival_rates: tuple[float, ...]   # one per movement
    movement_ids: tuple[str, ...]      # movement IDs matching queue order


@dataclass(frozen=True)
class MCTSState:
    time: float
    intersection_states: tuple[IntersectionSnapshot, ...]
    ev_link_index: int
    ev_position_on_link: float
    ev_speed: float
    ev_active: bool

    @staticmethod
    def from_simulation(sim_state, sim_time: float) -> MCTSState:
        """Build MCTSState from live SimulationState."""
        snapshots = []
        for iid in sim_state.corridor.intersection_ids:
            fsm = sim_state.signal_fsms.get(iid)
            iq = sim_state.intersection_queues.get(iid)

            if fsm is None:
                continue

            phase_elapsed = sim_time - fsm.state.phase_start_time
            time_to_end = fsm.time_until_phase_ends(sim_time)

            queue_lengths = []
            arrival_rates = []
            movement_ids = []
            if iq:
                for mid, q in iq.queues.items():
                    movement_ids.append(mid)
                    queue_lengths.append(round(q.get_queue(sim_time), 2))
                    arrival_rates.append(q.arrival_rate)

            snapshots.append(IntersectionSnapshot(
                intersection_id=iid,
                current_phase=fsm.state.current_phase,
                phase_elapsed=round(phase_elapsed, 2),
                phase_state=fsm.state.current_state.value,
                time_to_phase_end=round(time_to_end, 2),
                queue_lengths=tuple(queue_lengths),
                arrival_rates=tuple(arrival_rates),
                movement_ids=tuple(movement_ids),
            ))

        ev = sim_state.ev
        ev_active = ev is not None and ev.status.value not in ("idle", "arrived")

        return MCTSState(
            time=round(sim_time, 2),
            intersection_states=tuple(snapshots),
            ev_link_index=ev.current_link_index if ev else 0,
            ev_position_on_link=round(ev.position_on_link, 3) if ev else 0.0,
            ev_speed=ev.speed_kmph if ev else 0.0,
            ev_active=ev_active,
        )

    def total_queue(self) -> float:
        return sum(sum(s.queue_lengths) for s in self.intersection_states)

    def max_queue(self) -> float:
        all_q = [q for s in self.intersection_states for q in s.queue_lengths]
        return max(all_q) if all_q else 0.0
