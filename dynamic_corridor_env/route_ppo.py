"""Masked PPO policy adapter for EV route-choice actions."""

from __future__ import annotations

from pathlib import Path

from .models import DynamicCorridorAction, DynamicCorridorObservation, RouteCandidateObservation
from .ppo import _torch

OPTION_DIM = 8
MAX_CANDIDATES = 8
MAX_EDGE_LENGTH_M = 600.0
MAX_QUEUE = 60.0
MAX_DISTANCE_DELTA_M = 600.0
MAX_SPEED = 30.0


def encode_route_candidate(
    observation: DynamicCorridorObservation,
    candidate: RouteCandidateObservation,
) -> list[float]:
    """Encode one candidate next edge for route-choice policy scoring."""
    progress = float(observation.ev.progress)
    return [
        float(candidate.road_weight),
        min(float(candidate.estimated_queue) / MAX_QUEUE, 1.0),
        min(float(candidate.length_m) / MAX_EDGE_LENGTH_M, 1.0),
        min(float(candidate.speed_m_s) / MAX_SPEED, 1.0),
        max(-1.0, min(float(candidate.destination_distance_delta) / MAX_DISTANCE_DELTA_M, 1.0)),
        1.0 if candidate.moves_closer else 0.0,
        1.0 if candidate.is_backtrack else 0.0,
        progress,
    ]


def encode_route_observation(observation: DynamicCorridorObservation, torch):
    """Return padded candidate tensor and mask for variable-sized route options."""
    candidates = list(observation.route_choice.candidates)[:MAX_CANDIDATES]
    rows = [encode_route_candidate(observation, candidate) for candidate in candidates]
    rows.extend([[0.0] * OPTION_DIM for _ in range(MAX_CANDIDATES - len(rows))])
    mask = [candidate.destination_reachable for candidate in candidates]
    mask.extend([False] * (MAX_CANDIDATES - len(mask)))
    return (
        torch.tensor(rows, dtype=torch.float32),
        torch.tensor(mask, dtype=torch.bool),
    )


def _build_route_policy():
    torch, nn = _torch()

    class RoutePolicyValueNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.option_encoder = nn.Sequential(
                nn.Linear(OPTION_DIM, 64),
                nn.Tanh(),
                nn.Linear(64, 64),
                nn.Tanh(),
            )
            self.actor = nn.Linear(64, 1)
            self.critic = nn.Sequential(
                nn.Linear(64, 64),
                nn.Tanh(),
                nn.Linear(64, 1),
            )

            for module in self.modules():
                if isinstance(module, nn.Linear):
                    nn.init.orthogonal_(module.weight, gain=2 ** 0.5)
                    nn.init.zeros_(module.bias)
            nn.init.orthogonal_(self.actor.weight, gain=0.01)

        def forward(self, options, mask):
            encoded = self.option_encoder(options)
            logits = self.actor(encoded).squeeze(-1)
            logits = logits.masked_fill(~mask, -1e9)
            pooled = (encoded * mask.unsqueeze(-1).float()).sum(dim=-2)
            denom = mask.sum(dim=-1, keepdim=True).clamp(min=1).float()
            value = self.critic(pooled / denom).squeeze(-1)
            return logits, value

    return RoutePolicyValueNet()


class RoutePpoPolicy:
    """Checkpoint-backed route-choice policy returning DynamicCorridorAction(next_edge_id=...)."""

    def __init__(self, checkpoint_path: str | Path):
        torch, _ = _torch()
        self.torch = torch
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        self.model = _build_route_policy()
        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()

    def act(self, observation: DynamicCorridorObservation) -> DynamicCorridorAction:
        candidates = list(observation.route_choice.candidates)[:MAX_CANDIDATES]
        if not candidates:
            return DynamicCorridorAction(reason="Route PPO: no route candidates")

        options, mask = encode_route_observation(observation, self.torch)
        if not bool(mask.any().item()):
            return DynamicCorridorAction(reason="Route PPO: no reachable route candidates")

        with self.torch.no_grad():
            logits, _ = self.model(options.unsqueeze(0), mask.unsqueeze(0))
            action_idx = int(self.torch.argmax(logits, dim=-1).item())
        return DynamicCorridorAction(
            next_edge_id=candidates[action_idx].edge_id,
            reason="Route PPO greedy next-edge choice",
        )


__all__ = [
    "MAX_CANDIDATES",
    "OPTION_DIM",
    "RoutePpoPolicy",
    "_build_route_policy",
    "encode_route_candidate",
    "encode_route_observation",
]
