"""Standalone Colab runner/trainer for the hosted Smart Traffic API.

This file intentionally does not import anything from the local repository.
It only calls the hosted API endpoints:

  - POST /reset
  - POST /step
  - GET /state

Examples:

  # Copy-paste this whole file into Colab and run the cell.
  # By default it trains a small PPO signal policy from remote API rewards.

  # Upload the output folder to Hugging Face Hub.
  HF_TOKEN=... python remote_ppo_colab.py --mode ppo --episodes 20 \
    --hf-repo-id USER/smart-traffic-runs --upload-to-hf
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://mangesh29-smart-traffic.hf.space"
DEFAULT_TASK_ID = "grid_4x4_default"
DEFAULT_MODE = "ppo"
DEFAULT_EPISODES = 20
DEFAULT_MAX_STEPS = 180
DEFAULT_OUTPUT_DIR = "artifacts/standalone_remote_run"
OBS_DIM = 14
MAX_QUEUE = 60.0
MAX_ELAPSED = 20.0
MAX_DISTANCE_M = 500.0
MAX_VEHICLES = 120.0
MAX_SPEED = 20.0


@dataclass
class TrainConfig:
    gamma: float = 0.98
    gae_lambda: float = 0.95
    clip_ratio: float = 0.20
    value_clip: float = 0.20
    learning_rate: float = 3e-4
    entropy_coef: float = 0.01
    value_coef: float = 0.50
    ppo_epochs: int = 4
    batch_size: int = 64
    max_grad_norm: float = 0.50


@dataclass
class RewardConfig:
    w_queue: float = 0.40
    w_ev_waiting: float = 5.00
    w_ev_imminent: float = 2.00
    w_switch: float = 0.05
    w_throughput: float = 0.30
    w_global: float = 0.01


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        try:
            import requests
        except Exception as exc:
            raise RuntimeError("This script requires requests. In Colab run: pip install requests") from exc

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.call_rows: list[dict[str, Any]] = []

    def reset(self, task_id: str, episode: int) -> dict[str, Any]:
        return self._request(
            "reset",
            "POST",
            "/reset",
            episode=episode,
            step=0,
            json_payload={"task_id": task_id},
        )

    def step(self, action: dict[str, Any], episode: int, step: int) -> dict[str, Any]:
        return self._request(
            "step",
            "POST",
            "/step",
            episode=episode,
            step=step,
            json_payload={"action": action},
        )

    def state(self, episode: int, step: int) -> dict[str, Any]:
        return self._request("state", "GET", "/state", episode=episode, step=step)

    def _request(
        self,
        call: str,
        method: str,
        path: str,
        episode: int,
        step: int,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        success = False
        error = ""
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                json=json_payload,
                timeout=self.timeout,
            )
            try:
                response.raise_for_status()
            except Exception as exc:
                detail = response.text[:1000]
                raise RuntimeError(
                    f"{method} {path} failed with HTTP {response.status_code}: {detail}"
                ) from exc
            payload = response.json()
            success = True
            return payload
        except Exception as exc:
            error = str(exc)[:500]
            raise
        finally:
            self.call_rows.append(
                {
                    "call": call,
                    "method": method,
                    "path": path,
                    "episode": episode,
                    "step": step,
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
                    "success": int(success),
                    "error": error,
                }
            )


def observation_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    observation = payload.get("observation", payload)
    if not isinstance(observation, dict):
        raise TypeError(f"Expected dict observation, got {type(observation)!r}")
    if "reward" in payload:
        observation["reward"] = payload["reward"]
    if "done" in payload:
        observation["done"] = payload["done"]
    return observation


def state_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("state", payload)
    if not isinstance(state, dict):
        raise TypeError(f"Expected dict state, got {type(state)!r}")
    return state


def _phase_slot(ix: dict[str, Any]) -> tuple[list[int], int]:
    phases = list(ix.get("valid_phases") or sorted((ix.get("queue_by_phase") or {}).keys()))
    phases = [int(phase) for phase in phases]
    if not phases:
        phases = [int(ix.get("current_phase", 0))]
    current_phase = int(ix.get("current_phase", 0))
    try:
        current_slot = phases.index(current_phase)
    except ValueError:
        current_slot = 0
    return phases[:4], current_slot


def encode_intersection(ix: dict[str, Any], ev_active: bool) -> list[float]:
    phases, current_slot = _phase_slot(ix)
    queues_by_phase = {int(k): float(v) for k, v in (ix.get("queue_by_phase") or {}).items()}
    queues = [queues_by_phase.get(phase, 0.0) / MAX_QUEUE for phase in phases]
    queues.extend([0.0] * (4 - len(queues)))

    current_phase = int(ix.get("current_phase", 0))
    elapsed = float(ix.get("elapsed_phase_time", 0))
    ev_target_phase = ix.get("ev_target_phase")
    ev_eta_steps = float(ix.get("ev_eta_steps", -1.0))
    ev_distance_m = float(ix.get("ev_distance_m", -1.0))
    ev_target_active = ev_target_phase is not None and ev_eta_steps >= 0
    ev_on_current = ev_target_active and int(ev_target_phase) == current_phase
    eta_urgency = 0.0 if ev_eta_steps < 0 else 1.0 / (1.0 + ev_eta_steps)
    dist_proximity = 0.0 if ev_distance_m < 0 else 1.0 - min(ev_distance_m / MAX_DISTANCE_M, 1.0)
    current_pressure = queues_by_phase.get(current_phase, 0.0)
    best_pressure = max(queues_by_phase.values(), default=0.0)
    pressure_delta = (best_pressure - current_pressure) / MAX_QUEUE

    return [
        *queues[:4],
        current_slot / max(1, len(phases) - 1),
        min(elapsed / MAX_ELAPSED, 1.0),
        1.0 if ev_active else 0.0,
        1.0 if ev_on_current else 0.0,
        eta_urgency,
        dist_proximity,
        min(float(ix.get("queue_length", 0.0)) / (MAX_QUEUE * max(1, len(phases))), 1.0),
        min(float(ix.get("vehicle_count", 0)) / MAX_VEHICLES, 1.0),
        min(float(ix.get("mean_speed", 0.0)) / MAX_SPEED, 1.0),
        pressure_delta,
    ]


def target_phase_for_decision(ix: dict[str, Any], decision: str) -> int:
    current_phase = int(ix.get("current_phase", 0))
    if decision != "switch":
        return current_phase

    valid_phases = [int(phase) for phase in ix.get("valid_phases", [])]
    if not valid_phases:
        return current_phase

    ev_target_phase = ix.get("ev_target_phase")
    if ev_target_phase is not None and int(ev_target_phase) in valid_phases and int(ev_target_phase) != current_phase:
        return int(ev_target_phase)

    queues = {int(k): float(v) for k, v in (ix.get("queue_by_phase") or {}).items()}
    if queues:
        best_phase = max(valid_phases, key=lambda phase: queues.get(phase, 0.0))
        if best_phase != current_phase:
            return best_phase

    if current_phase in valid_phases:
        return valid_phases[(valid_phases.index(current_phase) + 1) % len(valid_phases)]
    return valid_phases[0]


def action_from_decisions(observation: dict[str, Any], decisions: dict[str, str], reason: str) -> dict[str, Any]:
    phase_by_intersection = {}
    for ix in observation.get("intersections", []):
        intersection_id = str(ix.get("intersection_id", ""))
        if intersection_id:
            phase_by_intersection[intersection_id] = target_phase_for_decision(
                ix,
                decisions.get(intersection_id, "keep"),
            )
    return {
        "phase_by_intersection": phase_by_intersection,
        "next_edge_id": None,
        "reason": reason,
    }


def compute_shaped_reward(
    ix: dict[str, Any],
    next_ix: dict[str, Any],
    action_target_phase: int,
    global_reward: float,
    cfg: RewardConfig,
) -> float:
    queue_now = float(ix.get("queue_length", 0.0))
    queue_next = float(next_ix.get("queue_length", 0.0))
    current_phase = int(ix.get("current_phase", 0))
    ev_eta_steps = float(ix.get("ev_eta_steps", -1.0))
    ev_target_phase = ix.get("ev_target_phase")

    reward = -cfg.w_queue * (queue_now / MAX_QUEUE)
    reward += cfg.w_throughput * (max(0.0, queue_now - queue_next) / MAX_QUEUE)
    if ev_eta_steps == 0 and ev_target_phase != current_phase:
        reward -= cfg.w_ev_waiting
    elif 0 < ev_eta_steps <= 3 and ev_target_phase != current_phase:
        reward -= cfg.w_ev_imminent * (1.0 / (1.0 + ev_eta_steps))
    if action_target_phase != current_phase:
        reward -= cfg.w_switch
    reward += cfg.w_global * global_reward
    return float(reward)


def torch_modules():
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:
        raise RuntimeError("PPO mode requires torch. In Colab run: pip install torch requests") from exc
    return torch, nn


def build_policy():
    torch, nn = torch_modules()

    class PolicyValueNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(OBS_DIM, 64),
                nn.Tanh(),
                nn.Linear(64, 64),
                nn.Tanh(),
            )
            self.actor = nn.Linear(64, 2)
            self.critic = nn.Linear(64, 1)

            for layer in self.backbone:
                if isinstance(layer, nn.Linear):
                    nn.init.orthogonal_(layer.weight, gain=2 ** 0.5)
                    nn.init.zeros_(layer.bias)
            nn.init.orthogonal_(self.actor.weight, gain=0.01)
            nn.init.orthogonal_(self.critic.weight, gain=1.0)
            nn.init.zeros_(self.actor.bias)
            nn.init.zeros_(self.critic.bias)

        def forward(self, x):
            features = self.backbone(x)
            return self.actor(features), self.critic(features).squeeze(-1)

    return PolicyValueNet()


class RolloutBuffer:
    def __init__(self):
        self.rows: list[dict[str, Any]] = []

    def push(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)

    def clear(self) -> None:
        self.rows.clear()

    def __len__(self) -> int:
        return len(self.rows)

    def compute_gae(self, gamma: float, gae_lambda: float) -> tuple[list[float], list[float]]:
        advantages = [0.0] * len(self.rows)
        returns = [0.0] * len(self.rows)
        by_agent: dict[str, list[int]] = {}
        for idx, row in enumerate(self.rows):
            by_agent.setdefault(row["agent_id"], []).append(idx)

        for indices in by_agent.values():
            gae = 0.0
            for pos in reversed(range(len(indices))):
                idx = indices[pos]
                row = self.rows[idx]
                value = row["value"].item()
                next_value = 0.0 if pos == len(indices) - 1 else self.rows[indices[pos + 1]]["value"].item()
                not_done = 0.0 if row["done"] else 1.0
                delta = row["reward"] + gamma * next_value * not_done - value
                gae = delta + gamma * gae_lambda * not_done * gae
                advantages[idx] = gae
                returns[idx] = gae + value
        return advantages, returns


def update_policy(model, optimizer, buffer: RolloutBuffer, cfg: TrainConfig) -> dict[str, float]:
    torch, _ = torch_modules()
    if len(buffer) == 0:
        return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0}

    model.train()
    advantages, returns = buffer.compute_gae(cfg.gamma, cfg.gae_lambda)
    indices = list(range(len(buffer.rows)))
    total_policy_loss = 0.0
    total_value_loss = 0.0
    total_entropy = 0.0
    updates = 0

    for _ in range(cfg.ppo_epochs):
        random.shuffle(indices)
        for start in range(0, len(indices), cfg.batch_size):
            batch_indices = indices[start:start + cfg.batch_size]
            obs = torch.stack([buffer.rows[i]["obs"] for i in batch_indices])
            actions = torch.tensor([buffer.rows[i]["action"] for i in batch_indices], dtype=torch.long)
            old_log_probs = torch.stack([buffer.rows[i]["log_prob"] for i in batch_indices]).detach()
            old_values = torch.stack([buffer.rows[i]["value"] for i in batch_indices]).detach()
            adv = torch.tensor([advantages[i] for i in batch_indices], dtype=torch.float32)
            ret = torch.tensor([returns[i] for i in batch_indices], dtype=torch.float32)
            if len(batch_indices) > 1:
                adv = (adv - adv.mean()) / (adv.std() + 1e-8)

            logits, values = model(obs)
            dist = torch.distributions.Categorical(logits=logits)
            new_log_probs = dist.log_prob(actions)
            entropy = dist.entropy().mean()
            ratio = torch.exp(new_log_probs - old_log_probs)
            policy_loss = -torch.min(
                ratio * adv,
                torch.clamp(ratio, 1 - cfg.clip_ratio, 1 + cfg.clip_ratio) * adv,
            ).mean()
            clipped_values = old_values + torch.clamp(values - old_values, -cfg.value_clip, cfg.value_clip)
            value_loss = 0.5 * torch.max((values - ret).pow(2), (clipped_values - ret).pow(2)).mean()
            loss = policy_loss + cfg.value_coef * value_loss - cfg.entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm)
            optimizer.step()

            total_policy_loss += float(policy_loss.item())
            total_value_loss += float(value_loss.item())
            total_entropy += float(entropy.item())
            updates += 1

    updates = max(1, updates)
    return {
        "policy_loss": total_policy_loss / updates,
        "value_loss": total_value_loss / updates,
        "entropy": total_entropy / updates,
    }


def write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_traffic_r1_episode(
    api: ApiClient,
    task_id: str,
    episode: int,
    max_steps: int,
    step_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    observation = observation_from_payload(api.reset(task_id, episode))
    total_reward = 0.0
    step = 0

    while not observation.get("done", False) and step < max_steps:
        step += 1
        payload = api.step(
            {"phase_by_intersection": {}, "next_edge_id": None, "reason": "hosted Traffic-R1 action"},
            episode,
            step,
        )
        observation = observation_from_payload(payload)
        reward = float(observation.get("reward", 0.0))
        total_reward += reward
        state = state_from_payload(api.state(episode, step))
        append_step_row(step_rows, episode, step, observation, reward, 0.0, state)

    final_state = state_from_payload(api.state(episode, step))
    return episode_summary(episode, step, total_reward, 0.0, observation, final_state, {})


def run_ppo_episode(
    api: ApiClient,
    task_id: str,
    episode: int,
    max_steps: int,
    model,
    buffer: RolloutBuffer,
    reward_cfg: RewardConfig,
    step_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    torch, _ = torch_modules()
    buffer.clear()
    model.eval()
    observation = observation_from_payload(api.reset(task_id, episode))
    total_reward = 0.0
    total_shaped_reward = 0.0
    step = 0

    while not observation.get("done", False) and step < max_steps:
        step += 1
        ev = observation.get("ev", {})
        ev_active = not ev.get("arrived", False) and bool(ev.get("next_intersection") or ev.get("current_edge"))
        decisions: dict[str, str] = {}
        records: dict[str, tuple[Any, int, Any, Any, dict[str, Any]]] = {}

        for ix in observation.get("intersections", []):
            obs_t = torch.tensor(encode_intersection(ix, ev_active), dtype=torch.float32)
            with torch.no_grad():
                logits, value = model(obs_t.unsqueeze(0))
            logits = logits.squeeze(0)
            value = value.squeeze(0)
            dist = torch.distributions.Categorical(logits=logits)
            action_idx = int(dist.sample().item())
            log_prob = dist.log_prob(torch.tensor(action_idx))
            intersection_id = str(ix.get("intersection_id"))
            decisions[intersection_id] = "switch" if action_idx == 1 else "keep"
            records[intersection_id] = (obs_t, action_idx, log_prob, value, ix)

        action = action_from_decisions(observation, decisions, "standalone remote PPO sampled keep/switch")
        next_observation = observation_from_payload(api.step(action, episode, step))
        next_by_id = {str(ix.get("intersection_id")): ix for ix in next_observation.get("intersections", [])}
        step_reward = float(next_observation.get("reward", 0.0))
        step_shaped_reward = 0.0

        for agent_id, (obs_t, action_idx, log_prob, value, ix) in records.items():
            next_ix = next_by_id.get(agent_id, ix)
            target_phase = int(action["phase_by_intersection"].get(agent_id, ix.get("current_phase", 0)))
            shaped_reward = compute_shaped_reward(ix, next_ix, target_phase, step_reward, reward_cfg)
            step_shaped_reward += shaped_reward
            buffer.push(
                agent_id=agent_id,
                obs=obs_t,
                action=action_idx,
                log_prob=log_prob,
                reward=shaped_reward,
                value=value,
                done=bool(next_observation.get("done", False)),
            )

        total_reward += step_reward
        total_shaped_reward += step_shaped_reward
        state = state_from_payload(api.state(episode, step))
        append_step_row(step_rows, episode, step, next_observation, step_reward, step_shaped_reward, state)
        observation = next_observation

    final_state = state_from_payload(api.state(episode, step))
    return episode_summary(episode, step, total_reward, total_shaped_reward, observation, final_state, {})


def append_step_row(
    rows: list[dict[str, Any]],
    episode: int,
    step: int,
    observation: dict[str, Any],
    reward: float,
    shaped_reward: float,
    state: dict[str, Any],
) -> None:
    ev = observation.get("ev", {})
    metrics = observation.get("global_metrics", {})
    rows.append(
        {
            "episode": episode,
            "step": step,
            "reward": round(reward, 6),
            "shaped_reward_total": round(shaped_reward, 6),
            "ev_progress": round(float(ev.get("progress", 0.0)), 6),
            "ev_waiting_time": round(float(ev.get("waiting_time", state.get("ev_waiting_time", 0.0))), 6),
            "ev_travel_time": round(float(ev.get("travel_time", state.get("ev_travel_time", 0.0))), 6),
            "total_queue": round(float(metrics.get("total_queue", state.get("total_queue", 0.0))), 6),
            "max_queue": round(float(metrics.get("max_queue", state.get("max_queue", 0.0))), 6),
            "phase_changes": int(metrics.get("phase_changes", state.get("phase_changes", 0))),
            "done": int(bool(observation.get("done", state.get("done", False)))),
        }
    )


def episode_summary(
    episode: int,
    steps: int,
    total_reward: float,
    total_shaped_reward: float,
    observation: dict[str, Any],
    state: dict[str, Any],
    update_stats: dict[str, float],
) -> dict[str, Any]:
    ev = observation.get("ev", {})
    metrics = observation.get("global_metrics", {})
    return {
        "episode": episode,
        "steps": steps,
        "total_reward": round(total_reward, 6),
        "mean_reward": round(total_reward / max(steps, 1), 6),
        "total_shaped_reward": round(total_shaped_reward, 6),
        "mean_shaped_reward": round(total_shaped_reward / max(steps, 1), 6),
        "ev_arrived": int(bool(ev.get("arrived", state.get("ev_arrived", False)))),
        "ev_travel_time": round(float(ev.get("travel_time", state.get("ev_travel_time", 0.0))), 6),
        "ev_waiting_time": round(float(ev.get("waiting_time", state.get("ev_waiting_time", 0.0))), 6),
        "final_ev_progress": round(float(ev.get("progress", 0.0)), 6),
        "final_total_queue": round(float(metrics.get("total_queue", state.get("total_queue", 0.0))), 6),
        "final_max_queue": round(float(metrics.get("max_queue", state.get("max_queue", 0.0))), 6),
        "phase_changes": int(metrics.get("phase_changes", state.get("phase_changes", 0))),
        "policy_loss": update_stats.get("policy_loss", 0.0),
        "value_loss": update_stats.get("value_loss", 0.0),
        "entropy": update_stats.get("entropy", 0.0),
    }


def save_checkpoint(model, optimizer, output_dir: Path, task_id: str, episodes_trained: int) -> None:
    torch, _ = torch_modules()
    torch.save(
        {
            "task_id": task_id,
            "episodes_trained": episodes_trained,
            "obs_dim": OBS_DIM,
            "action_space": ["keep", "switch"],
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
        },
        output_dir / f"ppo_{task_id}.pt",
    )


def upload_to_hf(output_dir: Path, repo_id: str, repo_type: str, path_in_repo: str | None) -> None:
    token = os.getenv("HF_TOKEN")
    if not token:
        print("skipped Hugging Face upload: HF_TOKEN is not configured")
        return
    try:
        from huggingface_hub import HfApi
    except Exception as exc:
        print(f"skipped Hugging Face upload: install huggingface_hub first ({exc})")
        return

    api = HfApi(token=token)
    info = api.upload_folder(
        folder_path=str(output_dir),
        repo_id=repo_id,
        repo_type=repo_type,
        path_in_repo=path_in_repo,
        token=token,
        commit_message="Upload standalone remote PPO/Traffic-R1 run",
    )
    print(f"uploaded {output_dir} to {repo_id}: {info}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Standalone hosted Smart Traffic simulator/PPO trainer")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--task-id", default=DEFAULT_TASK_ID)
    parser.add_argument("--mode", choices=["traffic-r1", "ppo"], default=DEFAULT_MODE)
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)

    parser.add_argument("--gamma", type=float, default=TrainConfig.gamma)
    parser.add_argument("--gae-lambda", type=float, default=TrainConfig.gae_lambda)
    parser.add_argument("--clip-ratio", type=float, default=TrainConfig.clip_ratio)
    parser.add_argument("--value-clip", type=float, default=TrainConfig.value_clip)
    parser.add_argument("--lr", type=float, default=TrainConfig.learning_rate)
    parser.add_argument("--entropy-coef", type=float, default=TrainConfig.entropy_coef)
    parser.add_argument("--value-coef", type=float, default=TrainConfig.value_coef)
    parser.add_argument("--ppo-epochs", type=int, default=TrainConfig.ppo_epochs)
    parser.add_argument("--batch-size", type=int, default=TrainConfig.batch_size)
    parser.add_argument("--max-grad-norm", type=float, default=TrainConfig.max_grad_norm)

    parser.add_argument("--w-queue", type=float, default=RewardConfig.w_queue)
    parser.add_argument("--w-ev-waiting", type=float, default=RewardConfig.w_ev_waiting)
    parser.add_argument("--w-ev-imminent", type=float, default=RewardConfig.w_ev_imminent)
    parser.add_argument("--w-switch", type=float, default=RewardConfig.w_switch)
    parser.add_argument("--w-throughput", type=float, default=RewardConfig.w_throughput)
    parser.add_argument("--w-global", type=float, default=RewardConfig.w_global)

    parser.add_argument("--upload-to-hf", action="store_true")
    parser.add_argument("--hf-repo-id", default="")
    parser.add_argument("--hf-repo-type", default="dataset", choices=["dataset", "model", "space"])
    parser.add_argument("--hf-path-in-repo", default=None)
    args, unknown_args = parser.parse_known_args(argv)
    if unknown_args:
        print(f"ignored notebook/kernel arguments: {' '.join(unknown_args)}")
    print(
        f"starting standalone remote run: mode={args.mode} "
        f"episodes={args.episodes} base_url={args.base_url}"
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    api = ApiClient(args.base_url, timeout=args.timeout)
    step_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    train_cfg = TrainConfig(
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
        clip_ratio=args.clip_ratio,
        value_clip=args.value_clip,
        learning_rate=args.lr,
        entropy_coef=args.entropy_coef,
        value_coef=args.value_coef,
        ppo_epochs=args.ppo_epochs,
        batch_size=args.batch_size,
        max_grad_norm=args.max_grad_norm,
    )
    reward_cfg = RewardConfig(
        w_queue=args.w_queue,
        w_ev_waiting=args.w_ev_waiting,
        w_ev_imminent=args.w_ev_imminent,
        w_switch=args.w_switch,
        w_throughput=args.w_throughput,
        w_global=args.w_global,
    )
    (output_dir / "run_config.json").write_text(
        json.dumps(
            {
                "base_url": args.base_url,
                "task_id": args.task_id,
                "mode": args.mode,
                "episodes": args.episodes,
                "max_steps": args.max_steps,
                "train_config": asdict(train_cfg),
                "reward_config": asdict(reward_cfg),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    model = None
    optimizer = None
    buffer = None
    if args.mode == "ppo":
        torch, _ = torch_modules()
        model = build_policy()
        optimizer = torch.optim.Adam(model.parameters(), lr=train_cfg.learning_rate, eps=1e-5)
        buffer = RolloutBuffer()

    for episode in range(1, args.episodes + 1):
        if args.mode == "traffic-r1":
            summary = run_traffic_r1_episode(api, args.task_id, episode, args.max_steps, step_rows)
            update_stats = {}
        else:
            assert model is not None and optimizer is not None and buffer is not None
            summary = run_ppo_episode(api, args.task_id, episode, args.max_steps, model, buffer, reward_cfg, step_rows)
            update_stats = update_policy(model, optimizer, buffer, train_cfg)
            summary.update(update_stats)
            save_checkpoint(model, optimizer, output_dir, args.task_id, episode)

        episode_rows.append(summary)
        write_csv(api.call_rows, output_dir / "api_calls.csv", [
            "call", "method", "path", "episode", "step", "duration_ms", "success", "error",
        ])
        write_csv(step_rows, output_dir / "steps.csv", [
            "episode", "step", "reward", "shaped_reward_total", "ev_progress", "ev_waiting_time",
            "ev_travel_time", "total_queue", "max_queue", "phase_changes", "done",
        ])
        write_csv(episode_rows, output_dir / "episodes.csv", [
            "episode", "steps", "total_reward", "mean_reward", "total_shaped_reward",
            "mean_shaped_reward", "ev_arrived", "ev_travel_time", "ev_waiting_time",
            "final_ev_progress", "final_total_queue", "final_max_queue", "phase_changes",
            "policy_loss", "value_loss", "entropy",
        ])
        print(
            f"episode={episode}/{args.episodes} mode={args.mode} "
            f"reward={summary['total_reward']:.3f} steps={summary['steps']} "
            f"arrived={summary['ev_arrived']} policy_loss={summary.get('policy_loss', 0.0):.4f}"
        )

    if args.upload_to_hf or args.hf_repo_id:
        if not args.hf_repo_id:
            print("skipped Hugging Face upload: --hf-repo-id is required")
        else:
            upload_to_hf(output_dir, args.hf_repo_id, args.hf_repo_type, args.hf_path_in_repo)

    print(f"wrote logs under {output_dir}")


if __name__ == "__main__":
    main()
