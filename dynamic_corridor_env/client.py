"""Client for the dynamic corridor clearing environment."""

from __future__ import annotations

from typing import Any

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from .models import DynamicCorridorAction, DynamicCorridorObservation, DynamicCorridorState


class DynamicCorridorEnv(
    EnvClient[DynamicCorridorAction, DynamicCorridorObservation, DynamicCorridorState]
):
    """OpenEnv client wrapper for dynamic emergency-corridor clearing."""

    def _step_payload(self, action: DynamicCorridorAction) -> dict[str, Any]:
        return {
            "phase_by_intersection": action.phase_by_intersection,
            "next_edge_id": action.next_edge_id,
            "reason": action.reason,
        }

    def _parse_result(self, payload: dict[str, Any]) -> StepResult[DynamicCorridorObservation]:
        observation = DynamicCorridorObservation(**payload.get("observation", {}))
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: dict[str, Any]) -> DynamicCorridorState:
        return DynamicCorridorState(**payload)
