"""Lightweight simulator for MCTS rollouts.

NO event queue — steps through horizon_step_s intervals analytically:
- Queue deltas: arrival_rate × dt for red, (arrival_rate - sat_flow) × dt for green
- Signal timing constraints (min_green, amber, all_red delays)
- EV position advancement
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.mcts.actions import Action, ActionType
from backend.app.mcts.state import IntersectionSnapshot, MCTSState


@dataclass
class FFIntersection:
    """Mutable intersection state for fast-forward."""
    intersection_id: str
    current_phase: int
    phase_state: str           # "GREEN", "AMBER", "ALL_RED"
    phase_elapsed: float
    queue_lengths: list[float]
    arrival_rates: list[float]
    movement_ids: list[str]
    green_phase_movements: dict[int, set[str]]  # phase_id -> set of movement_ids
    min_green: float
    max_green: float
    amber: float
    all_red: float
    phase_sequence: list[int]
    total_discharged: float = 0.0
    phase_changes: int = 0

    @staticmethod
    def from_snapshot(snap: IntersectionSnapshot,
                      intersection_config: dict) -> FFIntersection:
        green_map: dict[int, set[str]] = {}
        for p in intersection_config.get("phases", []):
            green_map[p["phase_id"]] = set(p["served_movements"])

        phases = intersection_config.get("phases", [])
        current_phase_cfg = next(
            (p for p in phases if p["phase_id"] == snap.current_phase), None
        )

        rings = intersection_config.get("rings", [])
        phase_seq = rings[0]["phase_sequence"] if rings else [1, 2]

        return FFIntersection(
            intersection_id=snap.intersection_id,
            current_phase=snap.current_phase,
            phase_state=snap.phase_state,
            phase_elapsed=snap.phase_elapsed,
            queue_lengths=list(snap.queue_lengths),
            arrival_rates=list(snap.arrival_rates),
            movement_ids=list(snap.movement_ids),
            green_phase_movements=green_map,
            min_green=current_phase_cfg["min_green"] if current_phase_cfg else 10.0,
            max_green=current_phase_cfg["max_green"] if current_phase_cfg else 45.0,
            amber=current_phase_cfg.get("amber", 3.0) if current_phase_cfg else 3.0,
            all_red=current_phase_cfg.get("all_red", 2.0) if current_phase_cfg else 2.0,
            phase_sequence=phase_seq,
        )

    def get_green_movements(self) -> set[str]:
        if self.phase_state != "GREEN":
            return set()
        return self.green_phase_movements.get(self.current_phase, set())

    def next_phase(self) -> int:
        try:
            idx = self.phase_sequence.index(self.current_phase)
            return self.phase_sequence[(idx + 1) % len(self.phase_sequence)]
        except ValueError:
            return self.phase_sequence[0] if self.phase_sequence else 1

    def apply_action(self, action: Action, dt: float) -> None:
        """Apply action and advance by dt seconds."""
        if action.action_type == ActionType.HOLD:
            self._advance_time(dt)
        elif action.action_type == ActionType.TERMINATE:
            self._terminate_and_advance(dt)
        elif action.action_type == ActionType.SKIP_TO_EV_PHASE:
            self._skip_to_phase(action.target_phase or self.next_phase(), dt)
        elif action.action_type in (ActionType.EXTEND_5, ActionType.EXTEND_10,
                                     ActionType.EXTEND_15):
            # Extend just means HOLD — max_green still enforced
            self._advance_time(dt)
        else:
            self._advance_time(dt)

    def _advance_time(self, dt: float) -> None:
        """Advance queues by dt, handling phase transitions at max_green."""
        remaining = dt
        while remaining > 0.001:
            step = remaining

            if self.phase_state == "GREEN":
                time_to_max = max(0, self.max_green - self.phase_elapsed)
                if time_to_max <= remaining:
                    # Green expires — process green portion then transition
                    self._update_queues(time_to_max)
                    remaining -= time_to_max
                    self._begin_transition()
                    continue
                else:
                    self._update_queues(remaining)
                    self.phase_elapsed += remaining
                    remaining = 0
            elif self.phase_state == "AMBER":
                time_left = max(0, self.amber - self.phase_elapsed)
                if time_left <= remaining:
                    self._update_queues(time_left)
                    remaining -= time_left
                    self.phase_state = "ALL_RED"
                    self.phase_elapsed = 0
                    continue
                else:
                    self._update_queues(remaining)
                    self.phase_elapsed += remaining
                    remaining = 0
            elif self.phase_state == "ALL_RED":
                time_left = max(0, self.all_red - self.phase_elapsed)
                if time_left <= remaining:
                    self._update_queues(time_left)
                    remaining -= time_left
                    self._activate_next_phase()
                    continue
                else:
                    self._update_queues(remaining)
                    self.phase_elapsed += remaining
                    remaining = 0

    def _terminate_and_advance(self, dt: float) -> None:
        """Terminate current phase and advance remaining time."""
        if self.phase_state != "GREEN":
            self._advance_time(dt)
            return

        if self.phase_elapsed < self.min_green:
            # Must wait for min_green
            wait = self.min_green - self.phase_elapsed
            if wait >= dt:
                self._update_queues(dt)
                self.phase_elapsed += dt
                return
            self._update_queues(wait)
            dt -= wait
            self.phase_elapsed = self.min_green

        # Begin transition
        self._begin_transition()
        self.phase_changes += 1
        if dt > 0:
            self._advance_time(dt)

    def _skip_to_phase(self, target_phase: int, dt: float) -> None:
        """Skip to a specific phase (for EV preemption)."""
        if self.current_phase == target_phase and self.phase_state == "GREEN":
            self._advance_time(dt)
            return

        # Set pending target and terminate
        self._pending_target = target_phase
        self._terminate_and_advance(dt)

    def _begin_transition(self) -> None:
        self.phase_state = "AMBER"
        self.phase_elapsed = 0

    def _activate_next_phase(self) -> None:
        target = getattr(self, '_pending_target', None)
        if target is not None:
            self.current_phase = target
            self._pending_target = None
        else:
            self.current_phase = self.next_phase()
        self.phase_state = "GREEN"
        self.phase_elapsed = 0

    def _update_queues(self, dt: float) -> None:
        """Update queue lengths analytically for dt seconds."""
        if dt <= 0:
            return
        green_movements = self.get_green_movements()
        for i, mid in enumerate(self.movement_ids):
            if i >= len(self.queue_lengths) or i >= len(self.arrival_rates):
                continue
            arrival = self.arrival_rates[i]
            if mid in green_movements:
                # Saturation flow ~1.0 veh/s (simplified)
                net = arrival - 1.0
            else:
                net = arrival
            new_q = self.queue_lengths[i] + net * dt
            if new_q < 0:
                discharged = self.queue_lengths[i] + arrival * dt
                self.total_discharged += max(0, discharged)
            elif mid in green_movements and net < 0:
                self.total_discharged += abs(net) * dt
            self.queue_lengths[i] = max(0.0, new_q)


@dataclass
class FFState:
    """Fast-forward state for MCTS rollouts."""
    time: float
    intersections: list[FFIntersection]
    ev_link_index: int
    ev_position: float
    ev_speed_kmph: float
    ev_active: bool
    ev_delay: float = 0.0
    total_phase_changes: int = 0
    ev_phases: dict[str, int] | None = None  # intersection_id -> EV's required phase

    @staticmethod
    def from_mcts_state(state: MCTSState,
                        intersection_configs: list[dict],
                        ev_phases: dict[str, int] | None = None) -> FFState:
        config_map = {c["intersection_id"]: c for c in intersection_configs}
        ff_ints = []
        for snap in state.intersection_states:
            cfg = config_map.get(snap.intersection_id, {})
            ff_ints.append(FFIntersection.from_snapshot(snap, cfg))

        return FFState(
            time=state.time,
            intersections=ff_ints,
            ev_link_index=state.ev_link_index,
            ev_position=state.ev_position_on_link,
            ev_speed_kmph=state.ev_speed,
            ev_active=state.ev_active,
            ev_phases=ev_phases,
        )

    def apply_actions(self, actions: list[Action], step_s: float) -> None:
        """Apply one set of actions (one per intersection) and advance step_s."""
        action_map = {a.intersection_id: a for a in actions}
        for ff_int in self.intersections:
            action = action_map.get(ff_int.intersection_id)
            if action:
                ff_int.apply_action(action, step_s)
            else:
                ff_int._advance_time(step_s)

        self.time += step_s
        self.total_phase_changes += sum(ff.phase_changes for ff in self.intersections)

        # Advance EV
        if self.ev_active:
            self._advance_ev(step_s)

    def _advance_ev(self, dt: float) -> None:
        """Simplified EV advancement — check if EV's specific phase is green."""
        if not self.ev_active or self.ev_link_index >= len(self.intersections):
            return

        target_int = self.intersections[min(self.ev_link_index,
                                             len(self.intersections) - 1)]

        # Check if EV's SPECIFIC approach phase is green (not just any phase)
        ev_has_green = False
        if self.ev_phases and target_int.intersection_id in self.ev_phases:
            ev_required_phase = self.ev_phases[target_int.intersection_id]
            ev_has_green = (
                target_int.phase_state == "GREEN"
                and target_int.current_phase == ev_required_phase
            )
        else:
            # Fallback: check any green (legacy behavior)
            ev_has_green = len(target_int.get_green_movements()) > 0

        if not ev_has_green:
            # EV waiting at red or wrong phase
            self.ev_delay += dt
        else:
            # EV advancing
            speed_mps = self.ev_speed_kmph * 1000.0 / 3600.0
            distance = speed_mps * dt
            self.ev_position += distance / 500.0  # normalized by ~500m link
            if self.ev_position >= 1.0:
                self.ev_position = 0.0
                self.ev_link_index += 1

    def total_queue(self) -> float:
        return sum(sum(ff.queue_lengths) for ff in self.intersections)

    def max_queue(self) -> float:
        all_q = [q for ff in self.intersections for q in ff.queue_lengths]
        return max(all_q) if all_q else 0.0

    def total_discharged(self) -> float:
        return sum(ff.total_discharged for ff in self.intersections)

    def to_mcts_state(self) -> MCTSState:
        """Convert back to MCTSState for tree operations."""
        snapshots = []
        for ff in self.intersections:
            snapshots.append(IntersectionSnapshot(
                intersection_id=ff.intersection_id,
                current_phase=ff.current_phase,
                phase_elapsed=round(ff.phase_elapsed, 2),
                phase_state=ff.phase_state,
                time_to_phase_end=0.0,
                queue_lengths=tuple(round(q, 2) for q in ff.queue_lengths),
                arrival_rates=tuple(ff.arrival_rates),
                movement_ids=tuple(ff.movement_ids),
            ))

        return MCTSState(
            time=round(self.time, 2),
            intersection_states=tuple(snapshots),
            ev_link_index=self.ev_link_index,
            ev_position_on_link=round(self.ev_position, 3),
            ev_speed=self.ev_speed_kmph,
            ev_active=self.ev_active,
        )
