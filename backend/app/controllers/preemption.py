"""Emergency preemption logic.

When an EV enters the corridor, preemption modifies MCTS behavior:
1. W_EV weight activated in reward function
2. Replan interval shortened (10s → 5s)
3. Rollout policy biases toward EV-clearing
4. Can also do direct preemption for nearest intersection
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.models.events import SimEvent
from backend.app.simulation.signal_fsm import SignalFSM

if TYPE_CHECKING:
    from backend.app.simulation.engine import SimulationState


def preempt_for_ev(state: SimulationState, sim_time: float) -> list[SimEvent]:
    """Direct preemption: switch the next intersection to EV's approach phase.

    This is used as an immediate fallback when MCTS hasn't had time to
    replan. MCTS will take over at the next replan cycle.
    """
    events: list[SimEvent] = []

    if state.ev is None:
        return events

    ev = state.ev
    corridor = state.ev_corridor or state.corridor

    if ev.current_link_index >= len(corridor.links):
        return events

    # Get the next intersection EV will reach
    link = corridor.links[ev.current_link_index]
    target_iid = link.to_intersection
    target_movement = link.ev_approach_movement

    # Find which phase serves this movement
    ix = state.intersections.get(target_iid)
    if ix is None:
        return events

    target_phase = ix.get_phase_for_movement(target_movement)
    if target_phase is None:
        return events

    # Request phase change
    fsm = state.signal_fsms.get(target_iid)
    if fsm is None:
        return events

    # Only preempt if not already on the right phase
    if fsm.state.current_phase != target_phase.phase_id:
        new_events = fsm.request_phase_change(
            target_phase.phase_id, sim_time, source="preemption"
        )
        events.extend(new_events)

    return events


def should_activate_preemption(state: SimulationState) -> bool:
    """Check if EV preemption should be active."""
    if state.ev is None:
        return False
    return state.ev.status.value in ("dispatched", "en_route",
                                      "waiting_at_signal",
                                      "traversing_intersection")


def get_ev_lookahead_intersections(state: SimulationState,
                                   lookahead: int = 2) -> list[str]:
    """Get the next N intersections the EV will encounter."""
    if state.ev is None:
        return []

    corridor = state.ev_corridor or state.corridor
    start_idx = state.ev.current_link_index
    result = []

    for i in range(start_idx, min(start_idx + lookahead, len(corridor.links))):
        result.append(corridor.links[i].to_intersection)

    return result
