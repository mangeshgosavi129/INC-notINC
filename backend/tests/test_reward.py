"""Tests for reward function."""

import pytest

from backend.app.mcts.fast_forward import FFIntersection, FFState
from backend.app.mcts.reward import RewardWeights, compute_reward, compute_reward_from_deltas


@pytest.fixture
def base_ff_state():
    """A baseline fast-forward state."""
    ff_ints = []
    for i in range(3):
        ff_ints.append(FFIntersection(
            intersection_id=f"INT_0{i+1}",
            current_phase=1,
            phase_state="GREEN",
            phase_elapsed=10.0,
            queue_lengths=[5.0, 3.0, 8.0, 4.0],
            arrival_rates=[0.2, 0.2, 0.3, 0.2],
            movement_ids=["NBT", "SBT", "EBT", "WBT"],
            green_phase_movements={1: {"NBT", "SBT"}, 2: {"EBT", "WBT"}},
            min_green=10.0, max_green=45.0, amber=3.0, all_red=2.0,
            phase_sequence=[1, 2],
            total_discharged=50.0,
            phase_changes=2,
        ))

    return FFState(
        time=100.0,
        intersections=ff_ints,
        ev_link_index=1,
        ev_position=0.5,
        ev_speed_kmph=60.0,
        ev_active=True,
        ev_delay=5.0,
        total_phase_changes=2,
    )


class TestRewardComputation:
    def test_reward_penalizes_queue(self, base_ff_state):
        w1 = RewardWeights(w_queue=1.0, w_ev=0, w_throughput=0, w_stability=0, w_max_queue=0)
        w2 = RewardWeights(w_queue=2.0, w_ev=0, w_throughput=0, w_stability=0, w_max_queue=0)
        r1 = compute_reward(base_ff_state, w1)
        r2 = compute_reward(base_ff_state, w2)
        # Higher queue weight → more negative reward
        assert r2 < r1

    def test_reward_increases_with_throughput(self, base_ff_state):
        w = RewardWeights(w_throughput=1.0, w_queue=0, w_ev=0, w_stability=0, w_max_queue=0)
        r1 = compute_reward(base_ff_state, w)
        # Increase throughput
        for ff in base_ff_state.intersections:
            ff.total_discharged = 200.0
        r2 = compute_reward(base_ff_state, w)
        assert r2 > r1

    def test_reward_penalizes_ev_delay_when_active(self, base_ff_state):
        w = RewardWeights(w_ev=10.0, w_queue=0, w_throughput=0, w_stability=0, w_max_queue=0)
        base_ff_state.ev_active = True
        base_ff_state.ev_delay = 5.0
        r1 = compute_reward(base_ff_state, w)

        base_ff_state.ev_delay = 20.0
        r2 = compute_reward(base_ff_state, w)
        assert r2 < r1

    def test_reward_ignores_ev_delay_when_inactive(self, base_ff_state):
        w = RewardWeights(w_ev=10.0, w_queue=0, w_throughput=0, w_stability=0, w_max_queue=0)
        base_ff_state.ev_active = False
        base_ff_state.ev_delay = 0.0
        r1 = compute_reward(base_ff_state, w)

        base_ff_state.ev_delay = 100.0
        r2 = compute_reward(base_ff_state, w)
        assert r1 == r2  # No penalty when EV inactive

    def test_reward_penalizes_phase_changes(self, base_ff_state):
        w = RewardWeights(w_stability=1.0, w_queue=0, w_ev=0, w_throughput=0, w_max_queue=0)
        base_ff_state.total_phase_changes = 2
        r1 = compute_reward(base_ff_state, w)

        base_ff_state.total_phase_changes = 10
        r2 = compute_reward(base_ff_state, w)
        assert r2 < r1

    def test_reward_penalizes_queue_overflow(self, base_ff_state):
        w = RewardWeights(w_max_queue=2.0, max_queue_threshold=6.0,
                          w_queue=0, w_ev=0, w_throughput=0, w_stability=0)
        r1 = compute_reward(base_ff_state, w)
        # Max queue is 8.0, threshold is 6.0 → overflow = 2.0

        # Set higher queues
        for ff in base_ff_state.intersections:
            ff.queue_lengths = [20.0, 15.0, 25.0, 18.0]
        r2 = compute_reward(base_ff_state, w)
        assert r2 < r1

    def test_weight_changes_affect_reward(self, base_ff_state):
        w_default = RewardWeights()
        w_ev_heavy = RewardWeights(w_ev=100.0)
        base_ff_state.ev_active = True
        base_ff_state.ev_delay = 10.0
        r1 = compute_reward(base_ff_state, w_default)
        r2 = compute_reward(base_ff_state, w_ev_heavy)
        assert r2 < r1  # Heavier EV penalty


class TestRewardFromDeltas:
    def test_basic_delta_reward(self):
        w = RewardWeights()
        r = compute_reward_from_deltas(
            initial_queue=50.0,
            final_queue=30.0,
            discharged=100.0,
            ev_delay=0.0,
            phase_changes=3,
            max_queue=35.0,
            ev_active=False,
            weights=w,
        )
        # Should be somewhat positive (throughput reward, reduced queue)
        # Exact value depends on weights
        assert isinstance(r, float)
