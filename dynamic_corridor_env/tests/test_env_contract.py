from __future__ import annotations

import inspect
import shutil

import pytest

pytest.importorskip("openenv")

from dynamic_corridor_env.server.dynamic_corridor_environment import DynamicCorridorEnvironment


def test_reset_signature_matches_openenv_contract():
    sig = inspect.signature(DynamicCorridorEnvironment.reset)
    params = set(sig.parameters)
    assert "seed" in params
    assert "episode_id" in params
    kwargs = sig.parameters.get("kwargs")
    assert kwargs is not None


def test_unsupported_task_id_raises_before_sumo():
    env = DynamicCorridorEnvironment()
    with pytest.raises(ValueError, match="Unsupported task_id"):
        env._reset_unlocked("pune_5_default", "NW_OUT", "SE_OUT")


def test_invalid_reward_mode_env_constructor():
    with pytest.raises(ValueError, match="Invalid"):
        DynamicCorridorEnvironment(reward_mode="not_a_mode")


def test_clearing_reward_penalizes_backtrack_in_route_feedback():
    env = DynamicCorridorEnvironment()
    assert env._reward_mode == "clearing"
    prev = {**env._empty_metrics(), "ev_progress": 0.2, "total_queue": 0.0, "max_queue": 0.0}
    curr = {**env._empty_metrics(), "ev_progress": 0.2, "total_queue": 0.0, "max_queue": 0.0}
    feedback = {
        "selected_edge": "INT_1_1_TO_NW_OUT",
        "invalid": False,
        "road_weight": 0.0,
        "estimated_queue": 0.0,
        "moves_closer": False,
        "is_backtrack": True,
        "destination_distance_delta": 0.0,
    }
    reward, fb = env._compute_reward(prev, curr, 0, feedback)
    assert reward <= -75.0
    assert "route_backtrack=1" in fb


def test_corridor_eval_metrics_shape():
    env = DynamicCorridorEnvironment()
    env._invalid_actions_episode = 2
    env._done = False
    m = env._empty_metrics()
    m["total_queue"] = 32.0
    m["ev_travel_time"] = 100.0
    m["ev_arrived"] = False
    block = env._corridor_eval_metrics(m)
    assert block["reward_mode"] == "clearing"
    assert block["invalid_action_count_episode"] == 2
    assert block["mean_corridor_queue"] == pytest.approx(32.0 / 16.0, rel=1e-3)
    assert block["ev_travel_time_s"] == 100.0
    assert block["ev_clearing_success"] is False
    assert block["episode_timeout"] is False
    assert block["n_signalized_intersections"] == 16


@pytest.mark.skipif(not shutil.which("sumo"), reason="SUMO binary not on PATH")
def test_reset_runs_one_episode_smoke_when_sumo_available():
    env = DynamicCorridorEnvironment()
    try:
        obs = env.reset(seed=1, episode_id="smoke-ep", task_id="grid_4x4_default")
        assert obs.task_id == "grid_4x4_default"
        assert obs.step == 0
        assert obs.global_metrics.get("reward_mode") == "clearing"
        assert env.state.episode_id == "smoke-ep"
        assert env.state.episode_seed == 1
    finally:
        env.shutdown()
