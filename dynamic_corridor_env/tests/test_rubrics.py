from __future__ import annotations

import pytest

pytest.importorskip("openenv")

from dynamic_corridor_env.models import DynamicCorridorAction, DynamicCorridorObservation, EVObservation
from dynamic_corridor_env.rubrics import (
    TerminalEVCorridorRubric,
    TrajectoryEVArrivalRubric,
    resolve_rubric_from_env,
)
from dynamic_corridor_env.server.dynamic_corridor_environment import DynamicCorridorEnvironment


def test_resolve_rubric_none():
    assert resolve_rubric_from_env("none", 900) is None
    assert resolve_rubric_from_env("", 900) is None


def test_resolve_unknown_raises():
    with pytest.raises(ValueError, match="Unknown rubric"):
        resolve_rubric_from_env("not_a_rubric", 900)


def test_terminal_ev_rubric_scores_speed():
    r = TerminalEVCorridorRubric(max_sim_time_s=100.0)
    obs = DynamicCorridorObservation(
        done=True,
        ev=EVObservation(arrived=True, travel_time=30.0),
    )
    assert r(DynamicCorridorAction(), obs) == pytest.approx(0.7)
    assert r.last_score == pytest.approx(0.7)


def test_terminal_ev_rubric_timeout_zero():
    r = TerminalEVCorridorRubric(max_sim_time_s=100.0)
    obs = DynamicCorridorObservation(
        done=True,
        ev=EVObservation(arrived=False, travel_time=100.0),
    )
    assert r(DynamicCorridorAction(), obs) == 0.0


def test_terminal_ev_not_done_zero():
    r = TerminalEVCorridorRubric(max_sim_time_s=100.0)
    obs = DynamicCorridorObservation(
        done=False,
        ev=EVObservation(arrived=False, travel_time=10.0),
    )
    assert r(DynamicCorridorAction(), obs) == 0.0


def test_trajectory_rubric_scores_on_done_only():
    r = TrajectoryEVArrivalRubric(max_sim_time_s=100.0)
    r(DynamicCorridorAction(), DynamicCorridorObservation(done=False, ev=EVObservation()))
    assert r.last_score == 0.0
    r(
        DynamicCorridorAction(),
        DynamicCorridorObservation(done=True, ev=EVObservation(arrived=True, travel_time=0.0)),
    )
    assert r.last_score == pytest.approx(1.0)
    step_rewards = r.compute_step_rewards()
    assert step_rewards == [0.0, 1.0]


def test_env_unknown_rubric_env_var(monkeypatch):
    monkeypatch.setenv("DYNAMIC_CORRIDOR_RUBRIC", "bogus_name")
    with pytest.raises(ValueError, match="Unknown rubric"):
        DynamicCorridorEnvironment()


def test_env_accepts_explicit_rubric():
    rub = TerminalEVCorridorRubric(200.0)
    env = DynamicCorridorEnvironment(rubric=rub)
    assert env.rubric is rub
