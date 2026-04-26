from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("openenv")
pytest.importorskip("torch")

from dynamic_corridor_env.models import DynamicCorridorObservation, EVObservation, IntersectionObservation
from dynamic_corridor_env.ppo import RewardConfig, TrainConfig
from dynamic_corridor_env.remote_ppo import RemotePpoTrainer, _build_parser


def _observation(step: int, reward: float, done: bool, queue: float = 4.0) -> DynamicCorridorObservation:
    return DynamicCorridorObservation(
        step=step,
        reward=reward,
        done=done,
        intersections=[
            IntersectionObservation(
                intersection_id="INT_1_1",
                current_phase=0,
                valid_phases=[0, 1],
                queue_by_phase={0: queue, 1: queue + 2.0},
                elapsed_phase_time=3,
                queue_length=queue,
                vehicle_count=8,
                mean_speed=5.0,
                ev_target_phase=1,
                ev_eta_steps=max(0, 3 - step),
                ev_distance_m=25.0,
            )
        ],
        ev=EVObservation(
            current_edge="NW_OUT_TO_INT_1_1",
            next_intersection="INT_1_1",
            progress=min(step / 2.0, 1.0),
            waiting_time=step * 2.0,
            travel_time=step * 5.0,
            arrived=done,
        ),
        global_metrics={
            "total_queue": queue,
            "max_queue": queue,
            "phase_changes": step,
        },
    )


class FakeRemoteEnv:
    def __init__(self):
        self.actions = []
        self._responses = [
            _observation(1, 0.4, False, queue=5.0),
            _observation(2, 0.6, True, queue=3.0),
        ]

    def reset(self, task_id: str):
        assert task_id == "grid_4x4_default"
        return SimpleNamespace(observation=_observation(0, 0.0, False), reward=0.0, done=False)

    def step(self, action):
        self.actions.append(action)
        observation = self._responses.pop(0)
        return SimpleNamespace(observation=observation, reward=observation.reward, done=observation.done)


def test_remote_ppo_tiny_run_writes_logs_checkpoint_and_actions(tmp_path):
    env = FakeRemoteEnv()
    trainer = RemotePpoTrainer(
        base_url="http://fake-space",
        output_dir=tmp_path,
        cfg=TrainConfig(ppo_epochs=1, batch_size=4),
        reward_cfg=RewardConfig(w_queue=0.25),
        max_steps=2,
        env_client=env,
    )

    checkpoint = trainer.run(episodes=1)

    assert checkpoint.exists()
    assert (tmp_path / "run_config.json").exists()
    assert (tmp_path / "api_calls.csv").exists()
    assert (tmp_path / "steps.csv").exists()
    assert (tmp_path / "episodes.csv").exists()
    assert (tmp_path / "ppo_grid_4x4_default_metrics.json").exists()

    assert len(env.actions) == 2
    assert all(action.phase_by_intersection for action in env.actions)
    assert all(action.next_edge_id is None for action in env.actions)

    with (tmp_path / "api_calls.csv").open(encoding="utf-8", newline="") as handle:
        api_rows = list(csv.DictReader(handle))
    assert [row["call"] for row in api_rows] == ["reset", "step", "step"]
    assert all(row["success"] == "1" for row in api_rows)

    with (tmp_path / "steps.csv").open(encoding="utf-8", newline="") as handle:
        step_rows = list(csv.DictReader(handle))
    assert len(step_rows) == 2
    assert step_rows[-1]["done"] == "1"

    config = json.loads((tmp_path / "run_config.json").read_text(encoding="utf-8"))
    assert config["base_url"] == "http://fake-space"
    assert config["reward_config"]["w_queue"] == 0.25


def test_remote_ppo_upload_uses_hf_api(monkeypatch, tmp_path):
    calls = []

    class FakeHfApi:
        def __init__(self, token=None):
            self.token = token

        def upload_folder(self, **kwargs):
            calls.append(kwargs)
            return {"ok": True}

    monkeypatch.setitem(
        __import__("sys").modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=FakeHfApi),
    )
    trainer = RemotePpoTrainer(output_dir=tmp_path, env_client=FakeRemoteEnv())

    result = trainer.upload_to_hub(
        repo_id="user/smart-traffic-runs",
        repo_type="dataset",
        path_in_repo="runs/test",
        token="hf_test",
    )

    assert result == {"ok": True}
    assert calls[0]["repo_id"] == "user/smart-traffic-runs"
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["path_in_repo"] == "runs/test"
    assert calls[0]["token"] == "hf_test"


def test_remote_ppo_parser_exposes_reward_weight_flags():
    args = _build_parser().parse_args(
        [
            "--w-queue",
            "0.7",
            "--w-ev-waiting",
            "4.5",
            "--hf-repo-id",
            "user/runs",
        ]
    )

    assert args.w_queue == 0.7
    assert args.w_ev_waiting == 4.5
    assert args.hf_repo_id == "user/runs"
