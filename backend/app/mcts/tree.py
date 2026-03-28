"""MCTS tree structure.

Each node represents a state after applying actions for one intersection
at one horizon step.

Tree depth = num_intersections × horizon_steps
Each level: up to 6 children (one per action)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.app.mcts.actions import Action


@dataclass
class MCTSNode:
    action: Action | None = None    # action that led to this node
    parent: MCTSNode | None = None
    children: list[MCTSNode] = field(default_factory=list)
    visit_count: int = 0
    total_reward: float = 0.0
    untried_actions: list[Action] = field(default_factory=list)

    # Tree navigation context
    intersection_index: int = 0     # which intersection this level decides for
    horizon_step: int = 0           # which horizon step

    @property
    def average_reward(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.total_reward / self.visit_count

    def ucb1(self, exploration_constant: float = 1.41) -> float:
        """UCB1 score for node selection."""
        if self.visit_count == 0:
            return float('inf')
        if self.parent is None or self.parent.visit_count == 0:
            return self.average_reward
        exploitation = self.average_reward
        exploration = exploration_constant * math.sqrt(
            math.log(self.parent.visit_count) / self.visit_count
        )
        return exploitation + exploration

    def is_fully_expanded(self) -> bool:
        return len(self.untried_actions) == 0

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def best_child(self, exploration_constant: float = 1.41) -> MCTSNode:
        """Select child with highest UCB1 score."""
        return max(self.children, key=lambda c: c.ucb1(exploration_constant))

    def best_action_child(self) -> MCTSNode:
        """Select child with highest average reward (for final selection)."""
        return max(self.children, key=lambda c: c.average_reward)

    def add_child(self, action: Action, intersection_index: int,
                  horizon_step: int) -> MCTSNode:
        """Add a child node for the given action."""
        child = MCTSNode(
            action=action,
            parent=self,
            intersection_index=intersection_index,
            horizon_step=horizon_step,
        )
        self.children.append(child)
        return child

    def backpropagate(self, reward: float) -> None:
        """Update visit count and total reward up to root."""
        node: MCTSNode | None = self
        while node is not None:
            node.visit_count += 1
            node.total_reward += reward
            node = node.parent

    def tree_depth(self) -> int:
        """Compute depth of the tree rooted at this node."""
        if not self.children:
            return 0
        return 1 + max(c.tree_depth() for c in self.children)
