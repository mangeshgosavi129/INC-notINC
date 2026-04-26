"""Remote PPO trainer for Colab/Hugging Face Space runs."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from typing import Any

from .client import DynamicCorridorEnv
from .models import DynamicCorridorObservation
from .policies import decisions_to_action
from .ppo import (
    OBS_DIM,
    RewardConfig,
    RolloutBuffer,
    TrainConfig,
    Transition,
    _build_policy,
    _torch,
    compute_agent_reward,
    encode_intersection_observation,
)

DEFAULT_BASE_URL = "https://mangesh29-smart-traffic.hf.space"

API_CALL_FIELDS = [
    "call",
    "episode",
    "step",
    "duration_ms",
    "success",
    "error",
]

STEP_FIELDS = [
    "episode",
    "step",
    "reward",
    "shaped_reward_total",
    "ev_progress",
    "ev_waiting_time",
    "ev_travel_time",
    "total_queue",
    "max_queue",
    "phase_changes",
    "done",
]

EPISODE_FIELDS = [
    "episode",
    "steps",
    "total_reward",
    "mean_reward",
    "total_shaped_reward",
    "mean_shaped_reward",
    "ev_arrived",
    "ev_travel_time",
    "ev_waiting_time",
    "final_ev_progress",
    "final_total_queue",
    "final_max_queue",
    "phase_changes",
    "mean_queue",
    "policy_loss",
    "value_loss",
    "entropy",
]


def _round(value: float | int | None, digits: int = 6) -> float:
    return round(float(value or 0.0), digits)


def _package_version() -> str:
    try:
        return metadata.version("openenv-dynamic-corridor-env")
    except metadata.PackageNotFoundError:
        return "editable-or-uninstalled"


def _write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class RemotePpoTrainer:
    """PPO trainer that learns through a hosted Dynamic Corridor API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        task_id: str = "grid_4x4_default",
        cfg: TrainConfig = TrainConfig(),
        reward_cfg: RewardConfig = RewardConfig(),
        output_dir: str | Path = "artifacts/remote_ppo",
        max_steps: int = 180,
        resume: bool = False,
        env_client: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.task_id = task_id
        self.cfg = cfg
        self.reward_cfg = reward_cfg
        self.output_dir = Path(output_dir)
        self.max_steps = max_steps
        self.resume = resume
        self.env = env_client or DynamicCorridorEnv(base_url=self.base_url)

        self.torch, _ = _torch()
        self.model = _build_policy()
        self.optimizer = self.torch.optim.Adam(self.model.parameters(), lr=cfg.learning_rate, eps=1e-5)
        self.buffer = RolloutBuffer()
        self.api_call_log: list[dict[str, Any]] = []
        self.step_log: list[dict[str, Any]] = []
        self.episode_log: list[dict[str, Any]] = []

        checkpoint_path = self._checkpoint_path()
        if resume and checkpoint_path.exists():
            checkpoint = self.torch.load(checkpoint_path, map_location="cpu")
            self.model.load_state_dict(checkpoint["model_state"])
            if "optimizer_state" in checkpoint:
                self.optimizer.load_state_dict(checkpoint["optimizer_state"])

    def run(self, episodes: int) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_run_config(episodes)
        started = time.time()
        for episode in range(1, episodes + 1):
            try:
                metrics = self._run_episode(episode)
            except Exception:
                self._write_artifacts(episodes_trained=episode - 1)
                raise
            self.episode_log.append({"episode": episode, **metrics})
            self._write_artifacts(episodes_trained=episode)
            elapsed = time.time() - started
            print(
                f"episode={episode}/{episodes} "
                f"reward={metrics['total_reward']:.3f} "
                f"shaped={metrics['total_shaped_reward']:.3f} "
                f"policy_loss={metrics['policy_loss']:.4f} "
                f"elapsed={elapsed:.0f}s"
            )
        return self._checkpoint_path()

    def _run_episode(self, episode: int) -> dict[str, Any]:
        torch = self.torch
        self.buffer.clear()
        self.model.eval()
        observation = self._timed_call(
            "reset",
            episode,
            0,
            lambda: self.env.reset(task_id=self.task_id),
        )

        total_reward = 0.0
        total_shaped_reward = 0.0
        queue_sum = 0.0
        step_count = 0

        while not observation.done and step_count < self.max_steps:
            step_count += 1
            decisions: dict[str, str] = {}
            records: dict[str, tuple[Any, int, Any, Any, Any]] = {}
            ev_active = not observation.ev.arrived and bool(observation.ev.next_intersection or observation.ev.current_edge)

            for ix in observation.intersections:
                obs_t = torch.tensor(
                    encode_intersection_observation(ix, ev_active),
                    dtype=torch.float32,
                )
                with torch.no_grad():
                    logits, value = self.model(obs_t.unsqueeze(0))
                logits = logits.squeeze(0)
                value = value.squeeze(0)
                dist = torch.distributions.Categorical(logits=logits)
                action_idx = int(dist.sample().item())
                log_prob = dist.log_prob(torch.tensor(action_idx))
                decisions[ix.intersection_id] = "switch" if action_idx == 1 else "keep"
                records[ix.intersection_id] = (obs_t, action_idx, log_prob, value, ix)

            action = decisions_to_action(observation, decisions, reason="Remote PPO sampled keep/switch")
            next_observation = self._timed_call(
                "step",
                episode,
                step_count,
                lambda: self.env.step(action),
            )
            next_by_id = {ix.intersection_id: ix for ix in next_observation.intersections}
            step_shaped_reward = 0.0

            for agent_id, (obs_t, action_idx, log_prob, value, ix) in records.items():
                next_ix = next_by_id.get(agent_id, ix)
                target_phase = action.phase_by_intersection.get(agent_id, ix.current_phase)
                shaped_reward = compute_agent_reward(
                    ix,
                    next_ix,
                    target_phase,
                    float(next_observation.reward),
                    self.reward_cfg,
                )
                step_shaped_reward += shaped_reward
                queue_sum += ix.queue_length
                self.buffer.push(
                    Transition(
                        agent_id=agent_id,
                        obs=obs_t,
                        action=action_idx,
                        log_prob=log_prob,
                        reward=shaped_reward,
                        value=value,
                        done=next_observation.done,
                    )
                )

            total_reward += float(next_observation.reward)
            total_shaped_reward += step_shaped_reward
            self._append_step_row(episode, step_count, next_observation, step_shaped_reward)
            observation = next_observation

        update_stats = self._update(last_values={})
        final_metrics = observation.global_metrics or {}
        n_agents = max(len(observation.intersections), 1)
        return {
            "steps": step_count,
            "total_reward": _round(total_reward),
            "mean_reward": _round(total_reward / max(step_count, 1)),
            "total_shaped_reward": _round(total_shaped_reward),
            "mean_shaped_reward": _round(total_shaped_reward / max(step_count, 1)),
            "ev_arrived": int(bool(observation.ev.arrived)),
            "ev_travel_time": _round(observation.ev.travel_time),
            "ev_waiting_time": _round(observation.ev.waiting_time),
            "final_ev_progress": _round(observation.ev.progress),
            "final_total_queue": _round(float(final_metrics.get("total_queue", 0.0))),
            "final_max_queue": _round(float(final_metrics.get("max_queue", 0.0))),
            "phase_changes": int(final_metrics.get("phase_changes", 0)),
            "mean_queue": _round(queue_sum / max(step_count * n_agents, 1)),
            **update_stats,
        }

    def _timed_call(self, call_name: str, episode: int, step: int, fn) -> DynamicCorridorObservation:
        started = time.perf_counter()
        success = False
        error = ""
        try:
            result = fn()
            observation = self._unwrap_observation(result)
            success = True
            return observation
        except Exception as exc:
            error = str(exc)[:500]
            raise
        finally:
            self.api_call_log.append(
                {
                    "call": call_name,
                    "episode": episode,
                    "step": step,
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
                    "success": int(success),
                    "error": error,
                }
            )

    @staticmethod
    def _unwrap_observation(result: Any) -> DynamicCorridorObservation:
        if isinstance(result, DynamicCorridorObservation):
            return result

        observation = getattr(result, "observation", result)
        reward = getattr(result, "reward", None)
        done = getattr(result, "done", None)
        if isinstance(result, dict) and "observation" in result:
            observation = result["observation"]
            reward = result.get("reward", reward)
            done = result.get("done", done)
        if isinstance(observation, dict):
            observation = DynamicCorridorObservation(**observation)
        if not isinstance(observation, DynamicCorridorObservation):
            raise TypeError(f"Expected DynamicCorridorObservation, got {type(observation)!r}")

        if reward is not None:
            observation.reward = float(reward)
        if done is not None:
            observation.done = bool(done)
        return observation

    def _append_step_row(
        self,
        episode: int,
        step: int,
        observation: DynamicCorridorObservation,
        shaped_reward_total: float,
    ) -> None:
        gm = observation.global_metrics or {}
        self.step_log.append(
            {
                "episode": episode,
                "step": step,
                "reward": _round(observation.reward),
                "shaped_reward_total": _round(shaped_reward_total),
                "ev_progress": _round(observation.ev.progress),
                "ev_waiting_time": _round(observation.ev.waiting_time),
                "ev_travel_time": _round(observation.ev.travel_time),
                "total_queue": _round(float(gm.get("total_queue", 0.0))),
                "max_queue": _round(float(gm.get("max_queue", 0.0))),
                "phase_changes": int(gm.get("phase_changes", 0)),
                "done": int(bool(observation.done)),
            }
        )

    def _update(self, last_values: dict[str, float]) -> dict[str, float]:
        torch = self.torch
        cfg = self.cfg
        self.model.train()
        if len(self.buffer) == 0:
            return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0}

        advantages, returns = self.buffer.compute_gae(last_values, cfg.gamma, cfg.gae_lambda)
        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        updates = 0

        for _ in range(cfg.ppo_epochs):
            for obs_b, act_b, old_lp_b, old_value_b, adv_b, ret_b in self.buffer.get_batches(
                advantages,
                returns,
                cfg.batch_size,
                torch,
            ):
                logits, values = self.model(obs_b)
                dist = torch.distributions.Categorical(logits=logits)
                new_log_probs = dist.log_prob(act_b)
                entropy = dist.entropy().mean()

                ratio = torch.exp(new_log_probs - old_lp_b)
                policy_loss_1 = ratio * adv_b
                policy_loss_2 = torch.clamp(ratio, 1 - cfg.clip_ratio, 1 + cfg.clip_ratio) * adv_b
                policy_loss = -torch.min(policy_loss_1, policy_loss_2).mean()

                clipped_values = old_value_b + torch.clamp(values - old_value_b, -cfg.value_clip, cfg.value_clip)
                value_loss = 0.5 * torch.max((values - ret_b).pow(2), (clipped_values - ret_b).pow(2)).mean()

                loss = policy_loss + cfg.value_coef * value_loss - cfg.entropy_coef * entropy
                self.optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), cfg.max_grad_norm)
                self.optimizer.step()

                total_policy_loss += float(policy_loss.item())
                total_value_loss += float(value_loss.item())
                total_entropy += float(entropy.item())
                updates += 1

        updates = max(updates, 1)
        return {
            "policy_loss": total_policy_loss / updates,
            "value_loss": total_value_loss / updates,
            "entropy": total_entropy / updates,
        }

    def _checkpoint_path(self) -> Path:
        return self.output_dir / f"ppo_{self.task_id}.pt"

    def _write_run_config(self, episodes: int) -> None:
        payload = {
            "base_url": self.base_url,
            "task_id": self.task_id,
            "episodes": episodes,
            "max_steps": self.max_steps,
            "resume": self.resume,
            "train_config": asdict(self.cfg),
            "reward_config": asdict(self.reward_cfg),
            "package_version": _package_version(),
        }
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "run_config.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_artifacts(self, episodes_trained: int) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.torch.save(
            {
                "task_id": self.task_id,
                "episodes_trained": episodes_trained,
                "obs_dim": OBS_DIM,
                "action_space": ["keep", "switch"],
                "model_state": self.model.state_dict(),
                "optimizer_state": self.optimizer.state_dict(),
            },
            self._checkpoint_path(),
        )
        metrics_path = self.output_dir / f"ppo_{self.task_id}_metrics.json"
        metrics_path.write_text(json.dumps(self.episode_log, indent=2), encoding="utf-8")
        _write_csv(self.api_call_log, self.output_dir / "api_calls.csv", API_CALL_FIELDS)
        _write_csv(self.step_log, self.output_dir / "steps.csv", STEP_FIELDS)
        _write_csv(self.episode_log, self.output_dir / "episodes.csv", EPISODE_FIELDS)

    def upload_to_hub(
        self,
        repo_id: str,
        repo_type: str = "dataset",
        path_in_repo: str | None = None,
        token: str | None = None,
    ) -> Any:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        return api.upload_folder(
            folder_path=str(self.output_dir),
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type=repo_type,
            token=token,
            commit_message=f"Upload remote PPO run for {self.task_id}",
        )


def train(
    base_url: str = DEFAULT_BASE_URL,
    task_id: str = "grid_4x4_default",
    episodes: int = 50,
    output_dir: str | Path = "artifacts/remote_ppo",
    max_steps: int = 180,
    cfg: TrainConfig = TrainConfig(),
    reward_cfg: RewardConfig = RewardConfig(),
    resume: bool = False,
) -> Path:
    trainer = RemotePpoTrainer(
        base_url=base_url,
        task_id=task_id,
        cfg=cfg,
        reward_cfg=reward_cfg,
        output_dir=output_dir,
        max_steps=max_steps,
        resume=resume,
    )
    return trainer.run(episodes)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train PPO against a hosted Dynamic Corridor Space")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--task-id", default="grid_4x4_default")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--max-steps", type=int, default=180)
    parser.add_argument("--output-dir", default="artifacts/remote_ppo")
    parser.add_argument("--resume", action="store_true")

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

    parser.add_argument("--upload-to-hf", action="store_true", help="Upload output-dir to Hugging Face Hub")
    parser.add_argument("--hf-repo-id", default="", help="Destination Hub repo, e.g. USER/smart-traffic-runs")
    parser.add_argument("--hf-repo-type", default="dataset", choices=["dataset", "model", "space"])
    parser.add_argument("--hf-path-in-repo", default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    cfg = TrainConfig(
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
    trainer = RemotePpoTrainer(
        base_url=args.base_url,
        task_id=args.task_id,
        cfg=cfg,
        reward_cfg=reward_cfg,
        output_dir=args.output_dir,
        max_steps=args.max_steps,
        resume=args.resume,
    )
    checkpoint_path = trainer.run(args.episodes)
    print(f"wrote {checkpoint_path}")
    print(f"wrote logs under {Path(args.output_dir)}")

    upload_requested = args.upload_to_hf or bool(args.hf_repo_id)
    if upload_requested:
        token = os.getenv("HF_TOKEN")
        if not args.hf_repo_id:
            print("skipped Hugging Face upload: --hf-repo-id is required")
        elif not token:
            print("skipped Hugging Face upload: HF_TOKEN is not configured")
        else:
            try:
                info = trainer.upload_to_hub(
                    repo_id=args.hf_repo_id,
                    repo_type=args.hf_repo_type,
                    path_in_repo=args.hf_path_in_repo,
                    token=token,
                )
                print(f"uploaded remote PPO run to {args.hf_repo_id}: {info}")
            except Exception as exc:
                print(f"failed to upload remote PPO run to Hugging Face: {exc}")


__all__ = [
    "DEFAULT_BASE_URL",
    "RemotePpoTrainer",
    "train",
]


if __name__ == "__main__":
    main()
