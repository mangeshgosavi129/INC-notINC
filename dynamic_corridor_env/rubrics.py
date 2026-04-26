"""OpenEnv rubrics for benchmarking dynamic corridor clearing (EV arrival, travel time)."""

from __future__ import annotations

from typing import Any

from openenv.core.rubrics import Rubric, TrajectoryRubric


class TerminalEVCorridorRubric(Rubric):
    """Per-step rubric: 0 until episode end; then score EV outcome in [0, 1].

    On terminal step: if the EV arrived, score is ``1 - travel_time / max_sim_time_s``
    (faster clearance is better). If the episode timed out without arrival, score is 0.
    """

    def __init__(self, max_sim_time_s: float = 900.0):
        super().__init__()
        self.max_sim_time_s = max(max_sim_time_s, 1.0)

    def forward(self, action: Any, observation: Any) -> float:
        obs = observation
        if not getattr(obs, "done", False):
            return 0.0
        ev = getattr(obs, "ev", None)
        if ev is None or not getattr(ev, "arrived", False):
            return 0.0
        travel = float(getattr(ev, "travel_time", self.max_sim_time_s))
        return max(0.0, min(1.0, 1.0 - travel / self.max_sim_time_s))

    def state_dict(self) -> dict[str, Any]:
        return {"max_sim_time_s": self.max_sim_time_s}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        if "max_sim_time_s" in state:
            self.max_sim_time_s = max(float(state["max_sim_time_s"]), 1.0)


class TrajectoryEVArrivalRubric(TrajectoryRubric):
    """Episode-level rubric: accumulates steps; at ``done`` returns a terminal score in [0, 1].

    Same scoring as ``TerminalEVCorridorRubric`` on the final observation.
    Intermediate steps return ``intermediate_reward`` (default 0).
    """

    def __init__(self, max_sim_time_s: float = 900.0, intermediate_reward: float = 0.0):
        super().__init__(intermediate_reward=intermediate_reward)
        self.max_sim_time_s = max(max_sim_time_s, 1.0)

    def score_trajectory(self, trajectory: list[tuple[Any, Any]]) -> float:
        if not trajectory:
            return 0.0
        _, final_obs = trajectory[-1]
        ev = getattr(final_obs, "ev", None)
        if ev is None or not getattr(ev, "arrived", False):
            return 0.0
        travel = float(getattr(ev, "travel_time", self.max_sim_time_s))
        return max(0.0, min(1.0, 1.0 - travel / self.max_sim_time_s))

    def compute_step_rewards(self) -> list[float]:
        if not self._trajectory:
            return []
        final = self.score_trajectory(self._trajectory)
        n = len(self._trajectory)
        return [0.0] * (n - 1) + [final]

    def state_dict(self) -> dict[str, Any]:
        base = super().state_dict()
        base["max_sim_time_s"] = self.max_sim_time_s
        return base

    def load_state_dict(self, state: dict[str, Any]) -> None:
        super().load_state_dict(state)
        if "max_sim_time_s" in state:
            self.max_sim_time_s = max(float(state["max_sim_time_s"]), 1.0)


def resolve_rubric_from_env(name: str | None, max_sim_time_s: float) -> Rubric | None:
    """Build a rubric from ``DYNAMIC_CORRIDOR_RUBRIC``-style names.

    - ``none`` / empty: no rubric
    - ``terminal_ev``: :class:`TerminalEVCorridorRubric`
    - ``trajectory_ev``: :class:`TrajectoryEVArrivalRubric`
    """
    key = (name or "none").strip().lower()
    if key in ("", "none"):
        return None
    if key == "terminal_ev":
        return TerminalEVCorridorRubric(max_sim_time_s=float(max_sim_time_s))
    if key == "trajectory_ev":
        return TrajectoryEVArrivalRubric(max_sim_time_s=float(max_sim_time_s))
    raise ValueError(
        f"Unknown rubric name {name!r}. Use 'none', 'terminal_ev', or 'trajectory_ev'."
    )


__all__ = [
    "TerminalEVCorridorRubric",
    "TrajectoryEVArrivalRubric",
    "resolve_rubric_from_env",
]
