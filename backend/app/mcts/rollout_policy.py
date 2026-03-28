"""Heuristic rollout policy for MCTS (NOT random).

- If EV active: SKIP_TO_EV_PHASE for intersection EV approaches next, HOLD for others
- If no EV: Longest-Queue-First (LQF) — terminate if another approach has higher queue
"""

from __future__ import annotations

from backend.app.mcts.actions import Action, ActionType
from backend.app.mcts.fast_forward import FFIntersection


def rollout_action(ff_int: FFIntersection, ev_active: bool,
                   ev_link_index: int, int_index: int,
                   ev_phase: int | None = None) -> Action:
    """Choose a heuristic action for one intersection during rollout.

    Args:
        ff_int: Fast-forward intersection state
        ev_active: Whether EV is active on corridor
        ev_link_index: Which link the EV is currently on
        int_index: Index of this intersection in the corridor
        ev_phase: Phase that serves the EV approach at this intersection
    """
    iid = ff_int.intersection_id

    # During amber/all_red, only HOLD is possible
    if ff_int.phase_state != "GREEN":
        return Action(iid, ActionType.HOLD)

    # EV-priority heuristic: when EV is active, aggressively clear its path
    if ev_active and ev_phase is not None:
        # Clear path for ALL intersections ahead of EV (proactive clearance)
        if int_index >= ev_link_index - 1:
            if ff_int.current_phase == ev_phase:
                # Already on EV's phase — HOLD it
                return Action(iid, ActionType.HOLD)
            else:
                # Need to switch to EV's phase — do it ASAP
                if ff_int.phase_elapsed >= ff_int.min_green:
                    return Action(iid, ActionType.SKIP_TO_EV_PHASE,
                                  target_phase=ev_phase)
                else:
                    # Can't switch yet — HOLD until min_green
                    return Action(iid, ActionType.HOLD)

    # LQF (Longest Queue First) heuristic
    return _lqf_action(ff_int)


def _lqf_action(ff_int: FFIntersection) -> Action:
    """Longest-Queue-First: terminate if a non-green approach has longer queue."""
    iid = ff_int.intersection_id
    green_movements = ff_int.get_green_movements()

    if not green_movements or not ff_int.queue_lengths:
        return Action(iid, ActionType.HOLD)

    # Sum queues for green vs non-green approaches
    green_queue = 0.0
    red_queue = 0.0
    for i, mid in enumerate(ff_int.movement_ids):
        if i >= len(ff_int.queue_lengths):
            continue
        if mid in green_movements:
            green_queue += ff_int.queue_lengths[i]
        else:
            red_queue += ff_int.queue_lengths[i]

    # If red approaches have significantly more queue, terminate
    if red_queue > green_queue * 1.2 and ff_int.phase_elapsed >= ff_int.min_green:
        return Action(iid, ActionType.TERMINATE)

    return Action(iid, ActionType.HOLD)
