"""MCTS Action space.

Per intersection, per decision step:
- HOLD: keep current phase running
- TERMINATE: end current phase (respecting min_green + amber + all_red)
- SKIP_TO_EV_PHASE: preempt to EV's approach phase
- EXTEND_5/10/15: extend current green by 5/10/15s

Branching factor per intersection: 6
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class ActionType(str, Enum):
    HOLD = "HOLD"
    TERMINATE = "TERMINATE"
    SKIP_TO_EV_PHASE = "SKIP_TO_EV_PHASE"
    EXTEND_5 = "EXTEND_5"
    EXTEND_10 = "EXTEND_10"
    EXTEND_15 = "EXTEND_15"


@dataclass(frozen=True)
class Action:
    intersection_id: str
    action_type: ActionType
    target_phase: int | None = None  # for SKIP_TO_EV_PHASE


# All possible action types (constant)
ALL_ACTION_TYPES = list(ActionType)


def get_valid_actions(intersection_id: str, phase_state: str,
                      phase_elapsed: float, min_green: float,
                      ev_phase: int | None = None) -> list[Action]:
    """Generate valid actions for an intersection given its current state.

    Args:
        intersection_id: ID of the intersection
        phase_state: Current state ("GREEN", "AMBER", "ALL_RED")
        phase_elapsed: Time elapsed in current state
        min_green: Minimum green time for current phase
        ev_phase: Phase that serves the EV approach (None if no EV)
    """
    actions = []

    if phase_state != "GREEN":
        # During amber/all_red, only HOLD is valid
        actions.append(Action(intersection_id, ActionType.HOLD))
        return actions

    # HOLD is always valid
    actions.append(Action(intersection_id, ActionType.HOLD))

    # TERMINATE only if min_green has elapsed
    if phase_elapsed >= min_green:
        actions.append(Action(intersection_id, ActionType.TERMINATE))

    # EXTEND options (always valid during green)
    actions.append(Action(intersection_id, ActionType.EXTEND_5))
    actions.append(Action(intersection_id, ActionType.EXTEND_10))
    actions.append(Action(intersection_id, ActionType.EXTEND_15))

    # SKIP_TO_EV_PHASE if EV is active and there's a target phase
    if ev_phase is not None:
        actions.append(Action(
            intersection_id, ActionType.SKIP_TO_EV_PHASE,
            target_phase=ev_phase,
        ))

    return actions


def get_all_actions_for_intersection(intersection_id: str,
                                     ev_phase: int | None = None) -> list[Action]:
    """Get all possible actions (for tree expansion, ignoring constraints).

    Constraints are checked during rollout/fast-forward instead.
    """
    actions = [
        Action(intersection_id, ActionType.HOLD),
        Action(intersection_id, ActionType.TERMINATE),
        Action(intersection_id, ActionType.EXTEND_5),
        Action(intersection_id, ActionType.EXTEND_10),
        Action(intersection_id, ActionType.EXTEND_15),
    ]
    if ev_phase is not None:
        actions.append(Action(
            intersection_id, ActionType.SKIP_TO_EV_PHASE,
            target_phase=ev_phase,
        ))
    return actions
