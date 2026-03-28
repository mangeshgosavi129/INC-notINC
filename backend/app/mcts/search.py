"""MCTS search loop: select → expand → rollout → backpropagate.

Rolling Horizon: decisions are made for each intersection sequentially,
over multiple horizon steps.

Tree depth = num_intersections × horizon_steps
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from backend.app.mcts.actions import Action, ActionType, get_all_actions_for_intersection
from backend.app.mcts.fast_forward import FFState
from backend.app.mcts.reward import RewardWeights, compute_reward
from backend.app.mcts.rollout_policy import rollout_action
from backend.app.mcts.state import MCTSState
from backend.app.mcts.tree import MCTSNode


@dataclass
class MCTSConfig:
    iterations: int = 1000
    horizon_length_s: float = 60.0
    horizon_step_s: float = 15.0
    exploration_constant: float = 1.41
    reward_weights: RewardWeights = None

    def __post_init__(self):
        if self.reward_weights is None:
            self.reward_weights = RewardWeights()

    @property
    def horizon_steps(self) -> int:
        return max(1, int(self.horizon_length_s / self.horizon_step_s))


class MCTSSearch:
    """Full MCTS search implementation."""

    def __init__(self, config: MCTSConfig, intersection_configs: list[dict],
                 intersection_ids: list[str],
                 ev_phases: dict[str, int] | None = None):
        """
        Args:
            config: MCTS hyperparameters
            intersection_configs: list of intersection config dicts (for fast-forward)
            intersection_ids: ordered list of intersection IDs in corridor
            ev_phases: mapping intersection_id -> phase that serves EV approach
        """
        self.config = config
        self.intersection_configs = intersection_configs
        self.intersection_ids = intersection_ids
        self.ev_phases = ev_phases or {}
        self.num_intersections = len(intersection_ids)

    def search(self, root_state: MCTSState) -> MCTSSearchResult:
        """Run MCTS from root_state. Returns best actions for first horizon step."""
        start_time = time.monotonic()

        root = MCTSNode()
        # Set up untried actions for the first intersection at first horizon step
        first_iid = self.intersection_ids[0] if self.intersection_ids else None
        if first_iid:
            ev_phase = self.ev_phases.get(first_iid)
            root.untried_actions = get_all_actions_for_intersection(
                first_iid, ev_phase
            )

        for iteration in range(self.config.iterations):
            # 1. Selection — traverse tree using UCB1
            node = self._select(root)

            # 2. Expansion — add a new child for an untried action
            if not node.is_fully_expanded():
                node = self._expand(node)

            # 3. Rollout — simulate to horizon using heuristic policy
            reward = self._rollout(root_state, node)

            # 4. Backpropagation — update statistics up the tree
            node.backpropagate(reward)

        # Extract best actions for first horizon step
        best_actions = self._extract_best_actions(root)
        elapsed_ms = (time.monotonic() - start_time) * 1000

        return MCTSSearchResult(
            actions=best_actions,
            reward=root.average_reward,
            iterations=self.config.iterations,
            tree_depth=root.tree_depth(),
            computation_ms=elapsed_ms,
            exploration_constant=self.config.exploration_constant,
        )

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select a leaf node using UCB1."""
        while not node.is_leaf() and node.is_fully_expanded():
            node = node.best_child(self.config.exploration_constant)
        return node

    def _expand(self, node: MCTSNode) -> MCTSNode:
        """Expand by adding a child for one untried action."""
        if not node.untried_actions:
            return node

        action = node.untried_actions.pop()

        # Determine next level's intersection/horizon
        int_idx = node.intersection_index
        h_step = node.horizon_step

        next_int_idx = int_idx + 1
        next_h_step = h_step

        if next_int_idx >= self.num_intersections:
            next_int_idx = 0
            next_h_step = h_step + 1

        child = node.add_child(action, next_int_idx, next_h_step)

        # Set up untried actions for the child
        if next_h_step < self.config.horizon_steps:
            next_iid = self.intersection_ids[next_int_idx]
            ev_phase = self.ev_phases.get(next_iid)
            child.untried_actions = get_all_actions_for_intersection(
                next_iid, ev_phase
            )

        return child

    def _rollout(self, root_state: MCTSState, leaf_node: MCTSNode) -> float:
        """Simulate from leaf to horizon using heuristic rollout policy."""
        # Collect actions from root to leaf
        actions_path = self._collect_actions_to_node(leaf_node)

        # Build fast-forward state with EV phase knowledge
        ff_state = FFState.from_mcts_state(
            root_state, self.intersection_configs, self.ev_phases
        )

        # Apply actions from path (grouped by horizon step)
        step_actions: list[Action] = []
        current_step = 0

        for action, int_idx, h_step in actions_path:
            if h_step != current_step:
                # Apply accumulated actions for previous step
                if step_actions:
                    ff_state.apply_actions(step_actions, self.config.horizon_step_s)
                step_actions = []
                current_step = h_step
            step_actions.append(action)

        # Apply remaining actions
        if step_actions:
            ff_state.apply_actions(step_actions, self.config.horizon_step_s)
            current_step += 1

        # Continue rollout with heuristic policy
        for h_step in range(current_step, self.config.horizon_steps):
            rollout_actions = []
            for i, iid in enumerate(self.intersection_ids):
                if i < len(ff_state.intersections):
                    ff_int = ff_state.intersections[i]
                    ev_phase = self.ev_phases.get(iid)
                    action = rollout_action(
                        ff_int, ff_state.ev_active,
                        ff_state.ev_link_index, i, ev_phase
                    )
                    rollout_actions.append(action)
            ff_state.apply_actions(rollout_actions, self.config.horizon_step_s)

        return compute_reward(ff_state, self.config.reward_weights)

    def _collect_actions_to_node(self, node: MCTSNode) -> list[tuple[Action, int, int]]:
        """Collect (action, intersection_index, horizon_step) from root to node."""
        path = []
        current = node
        while current.parent is not None:
            if current.action is not None:
                path.append((
                    current.action,
                    current.parent.intersection_index,
                    current.parent.horizon_step,
                ))
            current = current.parent
        path.reverse()
        return path

    def _extract_best_actions(self, root: MCTSNode) -> dict[str, Action]:
        """Extract best action per intersection for the first horizon step."""
        best_actions: dict[str, Action] = {}

        if not root.children:
            return best_actions

        # Best child at root = best action for first intersection
        node = root.best_action_child()
        if node.action:
            best_actions[node.action.intersection_id] = node.action

        # Follow best children for remaining intersections in first horizon step
        for i in range(1, self.num_intersections):
            if not node.children:
                break
            node = node.best_action_child()
            if node.action and node.horizon_step == 0:
                best_actions[node.action.intersection_id] = node.action

        return best_actions


@dataclass
class MCTSSearchResult:
    actions: dict[str, Action]  # intersection_id -> Action
    reward: float
    iterations: int
    tree_depth: int
    computation_ms: float
    exploration_constant: float

    def to_dict(self) -> dict:
        return {
            "actions": {
                iid: {"action_type": a.action_type.value,
                      "target_phase": a.target_phase}
                for iid, a in self.actions.items()
            },
            "reward": round(self.reward, 4),
            "iterations": self.iterations,
            "tree_depth": self.tree_depth,
            "computation_ms": round(self.computation_ms, 2),
            "exploration_constant": self.exploration_constant,
        }
