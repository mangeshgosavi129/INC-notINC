"""AI agent controller placeholder.

The future implementation will delegate corridor routing and signal decisions
to a main orchestration agent. For now this class preserves the controller
interface without applying any dynamic control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from backend.app.models.events import SimEvent

if TYPE_CHECKING:
    from backend.app.simulation.engine import SimulationState


@dataclass
class AgentDecision:
    """Serializable placeholder for a future agent decision."""

    decision_id: str
    sim_time: float
    actions: dict[str, Any] = field(default_factory=dict)
    status: str = "not_implemented"
    message: str = "AI agent routing is not implemented yet."
    computation_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "sim_time": self.sim_time,
            "actions": self.actions,
            "status": self.status,
            "message": self.message,
            "computation_ms": self.computation_ms,
        }


class AgentController:
    """Blank controller shell for future main-agent orchestration."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.decision_history: list[AgentDecision] = []

    def decide(self, state: SimulationState, sim_time: float) -> list[SimEvent]:
        """Return signal-control events for the current simulation state.

        Dynamic AI-agent routing is intentionally unimplemented. The empty
        event list leaves existing signal FSM timing untouched.
        """
        decision = AgentDecision(
            decision_id=f"agent_{len(self.decision_history)}",
            sim_time=sim_time,
        )
        self.decision_history.append(decision)
        return []

    @classmethod
    def from_config(cls, config: dict | None = None) -> "AgentController":
        return cls(config=config)
