"""PPO training and inference adapter for the dynamic corridor environment."""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from .models import DynamicCorridorAction, DynamicCorridorObservation, IntersectionObservation
from .policies import decisions_to_action

OBS_DIM = 14
MAX_QUEUE = 60.0
MAX_ELAPSED = 20.0
MAX_DISTANCE_M = 500.0
MAX_VEHICLES = 120.0
MAX_SPEED = 20.0


def _torch():
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyTorch is required for PPO. Install with `pip install torch`.") from exc
    return torch, nn


def _phase_slot(ix: IntersectionObservation) -> tuple[list[int], int]:
    phases = list(ix.valid_phases) or sorted(ix.queue_by_phase)
    if not phases:
        phases = [ix.current_phase]
    try:
        current_slot = phases.index(ix.current_phase)
    except ValueError:
        current_slot = 0
    return phases[:4], current_slot


def _eta_feature(eta_steps: float) -> float:
    if eta_steps < 0:
        return 0.0
    return 1.0 / (1.0 + eta_steps)


def encode_intersection_observation(
    ix: IntersectionObservation,
    ev_active: bool,
) -> list[float]:
    """Encode one corridor intersection into the 14-dim PPO feature vector."""
    phases, current_slot = _phase_slot(ix)
    queues = [ix.queue_by_phase.get(phase, 0.0) / MAX_QUEUE for phase in phases]
    queues.extend([0.0] * (4 - len(queues)))

    current_phase_norm = current_slot / max(1, len(phases) - 1)
    elapsed_norm = min(ix.elapsed_phase_time / MAX_ELAPSED, 1.0)
    ev_target_active = ix.ev_target_phase is not None and ix.ev_eta_steps >= 0
    ev_on_current = ev_target_active and ix.ev_target_phase == ix.current_phase
    eta_urgency = _eta_feature(ix.ev_eta_steps)
    dist_proximity = 0.0
    if ix.ev_distance_m >= 0:
        dist_proximity = 1.0 - min(ix.ev_distance_m / MAX_DISTANCE_M, 1.0)

    current_pressure = ix.queue_by_phase.get(ix.current_phase, 0.0)
    best_pressure = max(ix.queue_by_phase.values(), default=0.0)
    pressure_delta = (best_pressure - current_pressure) / MAX_QUEUE

    return [
        *queues[:4],
        current_phase_norm,
        elapsed_norm,
        1.0 if ev_active else 0.0,
        1.0 if ev_on_current else 0.0,
        eta_urgency,
        dist_proximity,
        min(ix.queue_length / (MAX_QUEUE * max(1, len(phases))), 1.0),
        min(ix.vehicle_count / MAX_VEHICLES, 1.0),
        min(ix.mean_speed / MAX_SPEED, 1.0),
        pressure_delta,
    ]


@dataclass
class RewardConfig:
    w_queue: float = 0.40
    w_ev_waiting: float = 5.00
    w_ev_imminent: float = 2.00
    w_switch: float = 0.05
    w_throughput: float = 0.30
    w_global: float = 0.01


def compute_agent_reward(
    ix: IntersectionObservation,
    next_ix: IntersectionObservation,
    action_target_phase: int,
    global_reward: float,
    cfg: RewardConfig = RewardConfig(),
) -> float:
    """Per-intersection shaped reward based on local queue and EV deltas."""
    queue_now = ix.queue_length
    queue_next = next_ix.queue_length
    reward = -cfg.w_queue * (queue_now / MAX_QUEUE)
    reward += cfg.w_throughput * (max(0.0, queue_now - queue_next) / MAX_QUEUE)

    if ix.ev_eta_steps == 0 and ix.ev_target_phase != ix.current_phase:
        reward -= cfg.w_ev_waiting
    elif 0 < ix.ev_eta_steps <= 3 and ix.ev_target_phase != ix.current_phase:
        reward -= cfg.w_ev_imminent * _eta_feature(ix.ev_eta_steps)

    if action_target_phase != ix.current_phase:
        reward -= cfg.w_switch

    reward += cfg.w_global * global_reward
    return float(reward)


def _build_policy():
    torch, nn = _torch()

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
            logits = self.actor(features)
            value = self.critic(features).squeeze(-1)
            return logits, value

    return PolicyValueNet()


class Transition(NamedTuple):
    agent_id: str
    obs: object
    action: int
    log_prob: object
    reward: float
    value: object
    done: bool


class RolloutBuffer:
    def __init__(self):
        self._data: list[Transition] = []

    def push(self, transition: Transition) -> None:
        self._data.append(transition)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def compute_gae(self, last_values: dict[str, float], gamma: float, gae_lambda: float):
        n = len(self._data)
        advantages = [0.0] * n
        returns = [0.0] * n
        by_agent: dict[str, list[int]] = {}
        for idx, transition in enumerate(self._data):
            by_agent.setdefault(transition.agent_id, []).append(idx)

        for agent_id, indices in by_agent.items():
            gae = 0.0
            for pos in reversed(range(len(indices))):
                idx = indices[pos]
                transition = self._data[idx]
                value = transition.value.item()
                if pos == len(indices) - 1:
                    next_value = last_values.get(agent_id, 0.0)
                else:
                    next_value = self._data[indices[pos + 1]].value.item()
                not_done = 0.0 if transition.done else 1.0
                delta = transition.reward + gamma * next_value * not_done - value
                gae = delta + gamma * gae_lambda * not_done * gae
                advantages[idx] = gae
                returns[idx] = gae + value
        return advantages, returns

    def get_batches(self, advantages, returns, batch_size: int, torch):
        indices = list(range(len(self._data)))
        random.shuffle(indices)
        obs_t = torch.stack([self._data[i].obs for i in indices])
        actions_t = torch.tensor([self._data[i].action for i in indices], dtype=torch.long)
        old_lp_t = torch.stack([self._data[i].log_prob for i in indices]).detach()
        old_value_t = torch.stack([self._data[i].value for i in indices]).detach()
        adv_t = torch.tensor([advantages[i] for i in indices], dtype=torch.float32)
        ret_t = torch.tensor([returns[i] for i in indices], dtype=torch.float32)

        if len(indices) > 1:
            adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        for start in range(0, len(indices), batch_size):
            batch = slice(start, min(start + batch_size, len(indices)))
            yield obs_t[batch], actions_t[batch], old_lp_t[batch], old_value_t[batch], adv_t[batch], ret_t[batch]


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


class PpoTrainer:
    def __init__(
        self,
        task_id: str = "grid_4x4_default",
        cfg: TrainConfig = TrainConfig(),
        reward_cfg: RewardConfig = RewardConfig(),
        output_dir: str | Path = "artifacts/policies",
        resume: bool = False,
    ):
        self.task_id = task_id
        self.cfg = cfg
        self.reward_cfg = reward_cfg
        self.output_dir = Path(output_dir)
        self.resume = resume

        self.torch, _ = _torch()
        self.model = _build_policy()
        self.optimizer = self.torch.optim.Adam(self.model.parameters(), lr=cfg.learning_rate, eps=1e-5)
        self.buffer = RolloutBuffer()
        self.episode_log: list[dict] = []

        checkpoint_path = self.output_dir / f"ppo_{task_id}.pt"
        if resume and checkpoint_path.exists():
            checkpoint = self.torch.load(checkpoint_path, map_location="cpu")
            self.model.load_state_dict(checkpoint["model_state"])
            if "optimizer_state" in checkpoint:
                self.optimizer.load_state_dict(checkpoint["optimizer_state"])

    def run(self, n_episodes: int) -> Path:
        from .server.dynamic_corridor_environment import DynamicCorridorEnvironment

        env = DynamicCorridorEnvironment()
        started = time.time()
        try:
            for episode in range(1, n_episodes + 1):
                metrics = self._run_episode(env)
                self.episode_log.append({"episode": episode, **metrics})
                if episode == 1 or episode % 10 == 0:
                    elapsed = time.time() - started
                    print(
                        f"episode={episode}/{n_episodes} "
                        f"reward={metrics['total_reward']:.3f} "
                        f"queue={metrics['mean_queue']:.3f} "
                        f"policy_loss={metrics['policy_loss']:.4f} "
                        f"elapsed={elapsed:.0f}s"
                    )
            path = self._save(n_episodes)
            self._save_metrics()
            return path
        finally:
            env.shutdown()

    def _run_episode(self, env) -> dict:
        torch = self.torch
        self.buffer.clear()
        self.model.eval()
        observation = env.reset(self.task_id)
        total_reward = 0.0
        queue_sum = 0.0
        step_count = 0

        while not observation.done:
            step_count += 1
            decisions: dict[str, str] = {}
            records: dict[str, tuple] = {}
            ev_active = not observation.ev.arrived and bool(observation.ev.next_intersection or observation.ev.current_edge)

            for ix in observation.intersections:
                vec = encode_intersection_observation(ix, ev_active)
                obs_t = torch.tensor(vec, dtype=torch.float32)
                with torch.no_grad():
                    logits, value = self.model(obs_t.unsqueeze(0))
                logits = logits.squeeze(0)
                value = value.squeeze(0)
                dist = torch.distributions.Categorical(logits=logits)
                action_idx = int(dist.sample().item())
                log_prob = dist.log_prob(torch.tensor(action_idx))
                decision = "switch" if action_idx == 1 else "keep"
                decisions[ix.intersection_id] = decision
                records[ix.intersection_id] = (obs_t, action_idx, log_prob, value, ix)

            action = decisions_to_action(observation, decisions, reason="PPO sampled keep/switch")
            next_observation = env.step(action)
            next_by_id = {ix.intersection_id: ix for ix in next_observation.intersections}

            for agent_id, (obs_t, action_idx, log_prob, value, ix) in records.items():
                next_ix = next_by_id.get(agent_id, ix)
                target_phase = action.phase_by_intersection.get(agent_id, ix.current_phase)
                shaped_reward = compute_agent_reward(
                    ix,
                    next_ix,
                    target_phase,
                    next_observation.reward,
                    self.reward_cfg,
                )
                total_reward += shaped_reward
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

            observation = next_observation

        update_stats = self._update(last_values={})
        n_agents = max(len(observation.intersections), 1)
        return {
            "total_reward": total_reward,
            "mean_queue": queue_sum / max(step_count * n_agents, 1),
            **update_stats,
        }

    def _update(self, last_values: dict[str, float]) -> dict:
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

    def _save(self, episodes_trained: int) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"ppo_{self.task_id}.pt"
        self.torch.save(
            {
                "task_id": self.task_id,
                "episodes_trained": episodes_trained,
                "obs_dim": OBS_DIM,
                "action_space": ["keep", "switch"],
                "model_state": self.model.state_dict(),
                "optimizer_state": self.optimizer.state_dict(),
            },
            path,
        )
        return path

    def _save_metrics(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"ppo_{self.task_id}_metrics.json"
        path.write_text(json.dumps(self.episode_log, indent=2), encoding="utf-8")


class PpoPolicy:
    """Checkpoint-backed deterministic policy for DynamicCorridorObservation."""

    def __init__(self, checkpoint_path: str | Path):
        torch, _ = _torch()
        self.torch = torch
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        obs_dim = checkpoint.get("obs_dim", OBS_DIM)
        if obs_dim != OBS_DIM:
            raise ValueError(f"Checkpoint obs_dim={obs_dim} != current OBS_DIM={OBS_DIM}. Retrain the model.")
        self.model = _build_policy()
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()

    def act(self, observation: DynamicCorridorObservation) -> DynamicCorridorAction:
        torch = self.torch
        decisions: dict[str, str] = {}
        ev_active = not observation.ev.arrived and bool(observation.ev.next_intersection or observation.ev.current_edge)
        with torch.no_grad():
            for ix in observation.intersections:
                vec = encode_intersection_observation(ix, ev_active)
                tensor = torch.tensor([vec], dtype=torch.float32)
                logits, _ = self.model(tensor)
                action_idx = int(torch.argmax(logits, dim=-1).item())
                decisions[ix.intersection_id] = "switch" if action_idx == 1 else "keep"
        return decisions_to_action(observation, decisions, reason="PPO greedy keep/switch")


def train(
    task_id: str = "grid_4x4_default",
    episodes: int = 50,
    gamma: float = 0.98,
    clip_ratio: float = 0.20,
    learning_rate: float = 3e-4,
    output_dir: str | Path = "artifacts/policies",
    resume: bool = False,
) -> Path:
    cfg = TrainConfig(gamma=gamma, clip_ratio=clip_ratio, learning_rate=learning_rate)
    trainer = PpoTrainer(task_id=task_id, cfg=cfg, output_dir=output_dir, resume=resume)
    return trainer.run(n_episodes=episodes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train PPO for dynamic corridor control")
    parser.add_argument("--task-id", default="grid_4x4_default")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--output-dir", default="artifacts/policies")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    path = train(
        task_id=args.task_id,
        episodes=args.episodes,
        learning_rate=args.lr,
        output_dir=args.output_dir,
        resume=args.resume,
    )
    print(path)


__all__ = [
    "PpoPolicy",
    "PpoTrainer",
    "RewardConfig",
    "TrainConfig",
    "compute_agent_reward",
    "encode_intersection_observation",
    "train",
]


if __name__ == "__main__":
    main()
