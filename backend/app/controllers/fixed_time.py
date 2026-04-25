"""Fixed-time baseline controller.

Cycles through phases with fixed green splits from timing plan.
No preemption — EV waits at reds like normal traffic.
Same simulation engine, just different controller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.models.events import EventType, SimEvent
from backend.app.utils.helpers import gen_id

if TYPE_CHECKING:
    from backend.app.simulation.engine import SimulationState


class FixedTimeController:
    """Baseline controller with fixed-time signal operation.

    At each replan trigger, checks if any intersection needs phase change
    based on timing plan splits. If elapsed time exceeds the green split,
    requests termination.
    """

    def __init__(self, timing_plans: dict[str, dict[int, float]]):
        """
        Args:
            timing_plans: mapping intersection_id -> {phase_id: green_duration_s}
        """
        self.timing_plans = timing_plans

    def decide(self, state: SimulationState,
               sim_time: float) -> list[SimEvent]:
        """Check each intersection and terminate phases that have exceeded their split."""
        events: list[SimEvent] = []

        for iid, fsm in state.signal_fsms.items():
            plan = self.timing_plans.get(iid, {})
            if not plan:
                continue

            # Only act during GREEN
            if fsm.state.current_state.value != "GREEN":
                continue

            current_phase = fsm.state.current_phase
            green_split = plan.get(current_phase, 30.0)
            elapsed = sim_time - fsm.state.phase_start_time

            if elapsed >= green_split:
                # Time to terminate — request through FSM
                new_events = fsm.request_terminate(sim_time, source="baseline")
                events.extend(new_events)

        return events

    @staticmethod
    def from_timing_plans_json(plans: list[dict]) -> FixedTimeController:
        """Build from timing plans JSON."""
        tp: dict[str, dict[int, float]] = {}
        for plan in plans:
            iid = plan["intersection_id"]
            splits = {int(k): v for k, v in plan["phase_splits"].items()}
            tp[iid] = splits
        return FixedTimeController(tp)
