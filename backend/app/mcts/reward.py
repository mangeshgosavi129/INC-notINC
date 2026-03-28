"""Weighted reward function for MCTS.

reward = (
    -W_EV × ev_delay              # EV delay penalty (only when EV active)
    - W_QUEUE × total_queue        # Total queue penalty
    + W_THROUGHPUT × discharged    # Throughput reward
    - W_STABILITY × phase_changes  # Discourage rapid switching
    - W_MAX_QUEUE × max(0, max_q - threshold)  # Prevent overflow
)

All weights configurable.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.mcts.fast_forward import FFState


@dataclass
class RewardWeights:
    w_ev: float = 100.0
    w_queue: float = 1.0
    w_throughput: float = 0.5
    w_stability: float = 0.1
    w_max_queue: float = 2.0
    max_queue_threshold: float = 50.0
    w_ev_progress: float = 20.0  # bonus for EV progress

    @staticmethod
    def from_config(config: dict) -> RewardWeights:
        rw = config.get("reward_weights", {})
        return RewardWeights(
            w_ev=rw.get("w_ev", 100.0),
            w_queue=rw.get("w_queue", 1.0),
            w_throughput=rw.get("w_throughput", 0.5),
            w_stability=rw.get("w_stability", 0.1),
            w_max_queue=rw.get("w_max_queue", 2.0),
            max_queue_threshold=rw.get("max_queue_threshold", 50.0),
            w_ev_progress=rw.get("w_ev_progress", 20.0),
        )


def compute_reward(ff_state: FFState, weights: RewardWeights) -> float:
    """Compute reward from a fast-forward state after rollout."""
    total_queue = ff_state.total_queue()
    max_queue = ff_state.max_queue()
    discharged = ff_state.total_discharged()
    ev_delay = ff_state.ev_delay
    phase_changes = ff_state.total_phase_changes

    reward = 0.0

    # EV delay penalty (only when EV active)
    if ff_state.ev_active:
        reward -= weights.w_ev * ev_delay
        # Bonus for EV progress (links advanced)
        reward += weights.w_ev_progress * ff_state.ev_link_index

    # Queue penalty
    reward -= weights.w_queue * total_queue

    # Throughput reward
    reward += weights.w_throughput * discharged

    # Stability penalty
    reward -= weights.w_stability * phase_changes

    # Max queue overflow penalty
    overflow = max(0.0, max_queue - weights.max_queue_threshold)
    reward -= weights.w_max_queue * overflow

    return reward


def compute_reward_from_deltas(
    initial_queue: float,
    final_queue: float,
    discharged: float,
    ev_delay: float,
    phase_changes: int,
    max_queue: float,
    ev_active: bool,
    weights: RewardWeights,
) -> float:
    """Compute reward from before/after deltas."""
    reward = 0.0

    if ev_active:
        reward -= weights.w_ev * ev_delay

    reward -= weights.w_queue * final_queue
    reward += weights.w_throughput * discharged
    reward -= weights.w_stability * phase_changes

    overflow = max(0.0, max_queue - weights.max_queue_threshold)
    reward -= weights.w_max_queue * overflow

    return reward
