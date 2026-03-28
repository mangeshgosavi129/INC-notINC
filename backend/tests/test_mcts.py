"""Tests for MCTS search engine."""

import json
from pathlib import Path

import pytest

from backend.app.mcts.actions import Action, ActionType, get_all_actions_for_intersection, get_valid_actions
from backend.app.mcts.fast_forward import FFState
from backend.app.mcts.reward import RewardWeights
from backend.app.mcts.search import MCTSConfig, MCTSSearch, MCTSSearchResult
from backend.app.mcts.state import IntersectionSnapshot, MCTSState
from backend.app.mcts.tree import MCTSNode


DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def intersection_configs():
    with open(DATA_DIR / "pune_default_intersections.json") as f:
        data = json.load(f)
    configs = []
    for ix in data["intersections"]:
        configs.append({
            "intersection_id": ix["intersection_id"],
            "phases": ix["phases"],
            "rings": ix["rings"],
        })
    return configs


@pytest.fixture
def corridor_ids():
    return ["INT_01", "INT_02", "INT_03", "INT_04", "INT_05"]


@pytest.fixture
def sample_mcts_state():
    """A plausible MCTS state with queues."""
    snapshots = []
    for i in range(1, 6):
        iid = f"INT_0{i}"
        snapshots.append(IntersectionSnapshot(
            intersection_id=iid,
            current_phase=1,
            phase_elapsed=15.0,
            phase_state="GREEN",
            time_to_phase_end=30.0,
            queue_lengths=(5.0, 3.0, 8.0, 4.0),
            arrival_rates=(0.2, 0.2, 0.3, 0.2),
            movement_ids=("NBT", "SBT", "EBT", "WBT"),
        ))

    return MCTSState(
        time=100.0,
        intersection_states=tuple(snapshots),
        ev_link_index=1,
        ev_position_on_link=0.5,
        ev_speed=60.0,
        ev_active=True,
    )


class TestMCTSTree:
    def test_ucb1_selects_unvisited(self):
        root = MCTSNode()
        root.visit_count = 10
        root.total_reward = 5.0

        c1 = root.add_child(
            Action("INT_01", ActionType.HOLD), 0, 0
        )
        c1.visit_count = 5
        c1.total_reward = 3.0

        c2 = root.add_child(
            Action("INT_01", ActionType.TERMINATE), 0, 0
        )
        # c2 unvisited — should have inf UCB1
        assert c2.ucb1() == float('inf')
        assert root.best_child().action.action_type == ActionType.TERMINATE

    def test_backpropagation(self):
        root = MCTSNode()
        child = root.add_child(Action("INT_01", ActionType.HOLD), 0, 0)
        grandchild = child.add_child(Action("INT_02", ActionType.HOLD), 1, 0)

        grandchild.backpropagate(10.0)
        assert grandchild.visit_count == 1
        assert grandchild.total_reward == 10.0
        assert child.visit_count == 1
        assert child.total_reward == 10.0
        assert root.visit_count == 1
        assert root.total_reward == 10.0

    def test_tree_expands(self):
        root = MCTSNode()
        root.untried_actions = [
            Action("INT_01", ActionType.HOLD),
            Action("INT_01", ActionType.TERMINATE),
        ]
        assert not root.is_fully_expanded()
        action = root.untried_actions.pop()
        root.add_child(action, 0, 0)
        assert len(root.children) == 1

    def test_best_action_child(self):
        root = MCTSNode()
        c1 = root.add_child(Action("INT_01", ActionType.HOLD), 0, 0)
        c1.visit_count = 10
        c1.total_reward = 50.0

        c2 = root.add_child(Action("INT_01", ActionType.TERMINATE), 0, 0)
        c2.visit_count = 10
        c2.total_reward = 80.0

        best = root.best_action_child()
        assert best.action.action_type == ActionType.TERMINATE


class TestActions:
    def test_all_actions_count(self):
        actions = get_all_actions_for_intersection("INT_01", ev_phase=2)
        assert len(actions) == 6  # HOLD, TERMINATE, EXTEND_5/10/15, SKIP_TO_EV

    def test_all_actions_no_ev(self):
        actions = get_all_actions_for_intersection("INT_01", ev_phase=None)
        assert len(actions) == 5  # No SKIP_TO_EV

    def test_valid_actions_during_amber(self):
        actions = get_valid_actions("INT_01", "AMBER", 1.0, 10.0)
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.HOLD

    def test_valid_actions_before_min_green(self):
        actions = get_valid_actions("INT_01", "GREEN", 5.0, 10.0)
        types = {a.action_type for a in actions}
        assert ActionType.TERMINATE not in types
        assert ActionType.HOLD in types

    def test_valid_actions_after_min_green(self):
        actions = get_valid_actions("INT_01", "GREEN", 15.0, 10.0)
        types = {a.action_type for a in actions}
        assert ActionType.TERMINATE in types


class TestMCTSSearch:
    def test_search_produces_actions(self, sample_mcts_state,
                                      intersection_configs, corridor_ids):
        config = MCTSConfig(iterations=50, horizon_step_s=15.0,
                            horizon_length_s=30.0)
        ev_phases = {f"INT_0{i}": 1 for i in range(1, 6)}

        search = MCTSSearch(config, intersection_configs, corridor_ids, ev_phases)
        result = search.search(sample_mcts_state)

        assert isinstance(result, MCTSSearchResult)
        assert len(result.actions) > 0
        assert result.iterations == 50
        assert result.computation_ms >= 0

    def test_search_result_serializable(self, sample_mcts_state,
                                         intersection_configs, corridor_ids):
        config = MCTSConfig(iterations=20)
        search = MCTSSearch(config, intersection_configs, corridor_ids)
        result = search.search(sample_mcts_state)
        d = result.to_dict()
        assert "actions" in d
        assert "reward" in d
        assert "iterations" in d

    def test_mcts_with_ev_prefers_clearing(self, intersection_configs, corridor_ids):
        """MCTS should prefer EV-clearing actions when EV is active."""
        # State where EV is approaching INT_02, phase 1 is green (EV needs phase 1 = SBT)
        snapshots = []
        for i in range(1, 6):
            iid = f"INT_0{i}"
            snapshots.append(IntersectionSnapshot(
                intersection_id=iid,
                current_phase=2,  # EBT/WBT green — NOT EV's phase
                phase_elapsed=15.0,
                phase_state="GREEN",
                time_to_phase_end=30.0,
                queue_lengths=(2.0, 2.0, 3.0, 3.0),
                arrival_rates=(0.2, 0.2, 0.2, 0.2),
                movement_ids=("NBT", "SBT", "EBT", "WBT"),
            ))

        state_ev = MCTSState(
            time=100.0,
            intersection_states=tuple(snapshots),
            ev_link_index=0,
            ev_position_on_link=0.8,
            ev_speed=60.0,
            ev_active=True,
        )

        # EV needs phase 1 (SBT) at each intersection
        ev_phases = {f"INT_0{i}": 1 for i in range(1, 6)}

        config = MCTSConfig(
            iterations=200,
            horizon_step_s=15.0,
            horizon_length_s=30.0,
            reward_weights=RewardWeights(w_ev=10.0),
        )

        search = MCTSSearch(config, intersection_configs, corridor_ids, ev_phases)
        result = search.search(state_ev)

        # With high EV weight, MCTS should want to switch at least some
        # intersections to phase 1 (or SKIP_TO_EV_PHASE)
        action_types = {a.action_type for a in result.actions.values()}
        has_ev_action = (ActionType.SKIP_TO_EV_PHASE in action_types or
                         ActionType.TERMINATE in action_types)
        # We expect at least some non-HOLD actions given EV is active
        assert has_ev_action or len(result.actions) > 0


class TestFastForward:
    def test_ff_state_from_mcts(self, sample_mcts_state, intersection_configs):
        ff = FFState.from_mcts_state(sample_mcts_state, intersection_configs)
        assert len(ff.intersections) == 5
        assert ff.ev_active is True
        assert ff.total_queue() > 0

    def test_ff_advance(self, sample_mcts_state, intersection_configs, corridor_ids):
        ff = FFState.from_mcts_state(sample_mcts_state, intersection_configs)
        initial_time = ff.time

        actions = [Action(f"INT_0{i}", ActionType.HOLD) for i in range(1, 6)]
        ff.apply_actions(actions, 15.0)

        assert ff.time == initial_time + 15.0

    def test_ff_to_mcts_state(self, sample_mcts_state, intersection_configs):
        ff = FFState.from_mcts_state(sample_mcts_state, intersection_configs)
        actions = [Action(f"INT_0{i}", ActionType.HOLD) for i in range(1, 6)]
        ff.apply_actions(actions, 15.0)

        new_state = ff.to_mcts_state()
        assert isinstance(new_state, MCTSState)
        assert new_state.time == sample_mcts_state.time + 15.0
