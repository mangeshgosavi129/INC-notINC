"""Signal-control policies adapted for the dynamic corridor environment."""

from __future__ import annotations

from typing import Mapping

from .models import DynamicCorridorAction, DynamicCorridorObservation, IntersectionObservation

Decision = str


def _phase_queues(observation: Mapping) -> dict[int, float]:
    queues = observation.get("queues") or observation.get("queue_by_phase") or {}
    return {int(phase): float(queue) for phase, queue in queues.items()}


def _valid_phases(observation: Mapping) -> list[int]:
    queues = _phase_queues(observation)
    valid = observation.get("valid_phases") or list(queues)
    return [int(phase) for phase in valid]


def _ev_info(observation: Mapping) -> dict | None:
    ev = observation.get("ev")
    if ev is not None:
        return ev
    eta = float(observation.get("ev_eta_steps", -1.0))
    ev_phase = observation.get("ev_target_phase")
    if eta < 0 or ev_phase is None:
        return None
    return {
        "entry_phase": int(ev_phase),
        "eta_steps": eta,
        "distance_m": float(observation.get("ev_distance_m", -1.0)),
        "cleared": False,
    }


def observation_for_policy(ix: IntersectionObservation) -> dict:
    """Convert a corridor intersection observation to the policy dict shape."""
    ev = None
    if ix.ev_target_phase is not None and ix.ev_eta_steps >= 0:
        ev = {
            "entry_phase": ix.ev_target_phase,
            "eta_steps": ix.ev_eta_steps,
            "distance_m": ix.ev_distance_m,
            "cleared": False,
        }
    return {
        "queues": dict(ix.queue_by_phase),
        "valid_phases": list(ix.valid_phases),
        "current_phase": ix.current_phase,
        "elapsed": ix.elapsed_phase_time,
        "ev": ev,
    }


def target_phase_for_decision(ix: IntersectionObservation, decision: Decision) -> int:
    """Translate a keep/switch decision into a valid SUMO phase target."""
    if decision != "switch":
        return ix.current_phase

    valid_phases = list(ix.valid_phases)
    if not valid_phases:
        return ix.current_phase

    if (
        ix.ev_target_phase is not None
        and ix.ev_target_phase in valid_phases
        and ix.ev_target_phase != ix.current_phase
    ):
        return ix.ev_target_phase

    queues = dict(ix.queue_by_phase)
    if queues:
        best_phase = max(valid_phases, key=lambda phase: queues.get(phase, 0.0))
        if best_phase != ix.current_phase:
            return best_phase

    if ix.current_phase in valid_phases:
        idx = valid_phases.index(ix.current_phase)
        return valid_phases[(idx + 1) % len(valid_phases)]
    return valid_phases[0]


def decisions_to_action(
    observation: DynamicCorridorObservation,
    decisions: Mapping[str, Decision],
    reason: str = "",
) -> DynamicCorridorAction:
    """Build a central corridor action from per-intersection keep/switch decisions."""
    phase_by_intersection = {
        ix.intersection_id: target_phase_for_decision(
            ix,
            decisions.get(ix.intersection_id, "keep"),
        )
        for ix in observation.intersections
    }
    return DynamicCorridorAction(phase_by_intersection=phase_by_intersection, reason=reason)


class FixedTimePolicy:
    """Fixed-cycle controller with independent per-intersection clocks."""

    def __init__(self, cycle_steps: int = 12, min_green_steps: int = 2):
        self.cycle_steps = cycle_steps
        self.min_green_steps = min_green_steps
        self._elapsed: dict[str, int] = {}
        self._phase: dict[str, int] = {}

    def act(self, intersection_id: str, observation: dict) -> Decision:
        elapsed = self._elapsed.get(intersection_id, int(observation.get("elapsed", 0)))
        phase = self._phase.get(intersection_id, int(observation.get("current_phase", 0)))
        n_phases = max(len(_valid_phases(observation)) or len(_phase_queues(observation)), 1)
        phase_duration = max(self.cycle_steps // n_phases, self.min_green_steps)

        self._elapsed[intersection_id] = elapsed + 1
        if elapsed >= phase_duration and elapsed >= self.min_green_steps:
            self._elapsed[intersection_id] = 0
            self._phase[intersection_id] = (phase + 1) % n_phases
            return "switch"
        return "keep"

    def reset(self, intersection_id: str) -> None:
        self._elapsed[intersection_id] = 0
        self._phase[intersection_id] = 0


class MaxPressurePolicy:
    """Switch when another phase has greater local queue pressure."""

    def __init__(self, min_green_steps: int = 2):
        self.min_green_steps = min_green_steps
        self._elapsed: dict[str, int] = {}

    def act(self, intersection_id: str, observation: dict) -> Decision:
        elapsed = self._elapsed.get(intersection_id, int(observation.get("elapsed", 0))) + 1
        self._elapsed[intersection_id] = elapsed
        if elapsed < self.min_green_steps:
            return "keep"

        queues = _phase_queues(observation)
        if not queues:
            return "keep"

        current_phase = int(observation.get("current_phase", 0))
        best_phase = max(queues, key=lambda phase: queues[phase])
        if best_phase != current_phase and queues[best_phase] > queues.get(current_phase, 0.0):
            self._elapsed[intersection_id] = 0
            return "switch"
        return "keep"

    def reset(self, intersection_id: str) -> None:
        self._elapsed[intersection_id] = 0


class ActuatedPolicy:
    """Extend green while demand exists, with a maximum hold guard."""

    def __init__(
        self,
        extension_threshold: float = 2.0,
        min_green_steps: int = 2,
        max_hold_steps: int = 15,
    ):
        self.extension_threshold = extension_threshold
        self.min_green_steps = min_green_steps
        self.max_hold_steps = max_hold_steps
        self._elapsed: dict[str, int] = {}

    def act(self, intersection_id: str, observation: dict) -> Decision:
        elapsed = self._elapsed.get(intersection_id, int(observation.get("elapsed", 0))) + 1
        self._elapsed[intersection_id] = elapsed
        if elapsed < self.min_green_steps:
            return "keep"
        if elapsed >= self.max_hold_steps:
            self._elapsed[intersection_id] = 0
            return "switch"

        queues = _phase_queues(observation)
        current_phase = int(observation.get("current_phase", 0))
        if queues.get(current_phase, 0.0) >= self.extension_threshold:
            return "keep"
        self._elapsed[intersection_id] = 0
        return "switch"

    def reset(self, intersection_id: str) -> None:
        self._elapsed[intersection_id] = 0


class EmergencyAwarePolicy:
    """Preempt and pre-stage for an approaching emergency vehicle."""

    def __init__(
        self,
        preempt_eta_threshold: int = 3,
        lookahead_eta: int = 8,
        max_hold_steps: int = 40,
        min_green_steps: int = 2,
    ):
        self.preempt_eta_threshold = preempt_eta_threshold
        self.lookahead_eta = lookahead_eta
        self.max_hold_steps = max_hold_steps
        self.min_green_steps = min_green_steps
        self._elapsed: dict[str, int] = {}
        self._hold: dict[str, bool] = {}
        self._hold_steps: dict[str, int] = {}
        self._fallback = MaxPressurePolicy(min_green_steps=min_green_steps)

    def act(self, intersection_id: str, observation: dict) -> Decision:
        elapsed = self._elapsed.get(intersection_id, int(observation.get("elapsed", 0))) + 1
        self._elapsed[intersection_id] = elapsed
        holding = self._hold.get(intersection_id, False)
        hold_steps = self._hold_steps.get(intersection_id, 0)

        ev_info = _ev_info(observation)
        current_phase = int(observation.get("current_phase", 0))
        if ev_info is None or float(ev_info.get("eta_steps", -1.0)) < 0:
            if holding:
                self._hold[intersection_id] = False
                self._hold_steps[intersection_id] = 0
                self._elapsed[intersection_id] = 0
            return self._fallback.act(intersection_id, observation)

        eta = float(ev_info["eta_steps"])
        ev_phase = int(ev_info.get("entry_phase", current_phase))
        if ev_info.get("cleared", False):
            self._hold[intersection_id] = False
            self._hold_steps[intersection_id] = 0
            return self._fallback.act(intersection_id, observation)

        if holding:
            self._hold_steps[intersection_id] = hold_steps + 1
            if hold_steps + 1 >= self.max_hold_steps:
                self._hold[intersection_id] = False
                self._hold_steps[intersection_id] = 0
                self._elapsed[intersection_id] = 0
                return "switch"

        if 0 <= eta <= self.preempt_eta_threshold:
            if current_phase != ev_phase and elapsed >= self.min_green_steps:
                self._hold[intersection_id] = True
                self._hold_steps[intersection_id] = 0
                self._elapsed[intersection_id] = 0
                return "switch"
            self._hold[intersection_id] = True
            return "keep"

        if self.preempt_eta_threshold < eta <= self.lookahead_eta:
            if current_phase != ev_phase and elapsed >= self.min_green_steps:
                self._elapsed[intersection_id] = 0
                return "switch"
            return "keep"

        return self._fallback.act(intersection_id, observation)

    def reset(self, intersection_id: str) -> None:
        self._elapsed[intersection_id] = 0
        self._hold[intersection_id] = False
        self._hold_steps[intersection_id] = 0
        self._fallback.reset(intersection_id)


class GreenWavePolicy:
    """Coordinate a rolling emergency green wave across corridor intersections."""

    def __init__(
        self,
        link_travel_steps: int = 4,
        wave_window: int = 3,
        min_green_steps: int = 2,
        max_hold_steps: int = 30,
    ):
        self.link_travel_steps = link_travel_steps
        self.wave_window = wave_window
        self.min_green_steps = min_green_steps
        self.max_hold_steps = max_hold_steps
        self._hops: dict[str, int] = {}
        self._elapsed: dict[str, int] = {}
        self._hold: dict[str, bool] = {}
        self._hold_steps: dict[str, int] = {}
        self._fallback = MaxPressurePolicy(min_green_steps=min_green_steps)

    def register_intersection(self, intersection_id: str, hops_from_lead: int) -> None:
        self._hops[intersection_id] = hops_from_lead
        self._elapsed[intersection_id] = 0
        self._hold[intersection_id] = False
        self._hold_steps[intersection_id] = 0

    def act(self, intersection_id: str, observation: dict, lead_ev_eta: float = -1.0) -> Decision:
        elapsed = max(
            self._elapsed.get(intersection_id, 0),
            int(observation.get("elapsed", 0)),
        ) + 1
        self._elapsed[intersection_id] = elapsed
        holding = self._hold.get(intersection_id, False)
        hold_steps = self._hold_steps.get(intersection_id, 0)
        hops = self._hops.get(intersection_id, 0)

        if holding:
            self._hold_steps[intersection_id] = hold_steps + 1
            if hold_steps + 1 >= self.max_hold_steps:
                self._hold[intersection_id] = False
                self._hold_steps[intersection_id] = 0
                self._elapsed[intersection_id] = 0
                return "switch"

        ev_info = _ev_info(observation)
        if lead_ev_eta < 0 and ev_info is None:
            if holding:
                self._hold[intersection_id] = False
                self._hold_steps[intersection_id] = 0
            return self._fallback.act(intersection_id, observation)

        eta_here = lead_ev_eta + hops * self.link_travel_steps if lead_ev_eta >= 0 else -1.0
        if ev_info and float(ev_info.get("eta_steps", -1.0)) >= 0:
            eta_here = float(ev_info["eta_steps"])

        current_phase = int(observation.get("current_phase", 0))
        ev_phase = int(ev_info["entry_phase"]) if ev_info else None
        if ev_phase is not None and 0 <= eta_here <= self.wave_window:
            if current_phase != ev_phase and elapsed >= self.min_green_steps:
                self._hold[intersection_id] = True
                self._hold_steps[intersection_id] = 0
                self._elapsed[intersection_id] = 0
                return "switch"
            self._hold[intersection_id] = True
            return "keep"

        return self._fallback.act(intersection_id, observation)

    def reset(self, intersection_id: str) -> None:
        self._elapsed[intersection_id] = 0
        self._hold[intersection_id] = False
        self._hold_steps[intersection_id] = 0
        self._fallback.reset(intersection_id)


__all__ = [
    "ActuatedPolicy",
    "EmergencyAwarePolicy",
    "FixedTimePolicy",
    "GreenWavePolicy",
    "MaxPressurePolicy",
    "decisions_to_action",
    "observation_for_policy",
    "target_phase_for_decision",
]
