"""Peer-to-peer intersection-agent runtime for emergency corridor control."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

try:
    from .models import DynamicCorridorAction, DynamicCorridorObservation, EVObservation, IntersectionObservation
except ImportError:
    from models import DynamicCorridorAction, DynamicCorridorObservation, EVObservation, IntersectionObservation


@dataclass(frozen=True)
class PeerMessage:
    """Compact emergency-vehicle intent exchanged by neighboring agents."""

    sender_id: str
    ev_id: str
    eta_steps: float
    target_phase: int | None
    route_index: int
    status: str
    ttl: int
    confidence: float


@dataclass
class AgentDecision:
    target_phase: int | None = None
    messages: list[PeerMessage] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class AgentConfig:
    message_ttl: int = 2
    prestage_window_steps: int = 8
    preempt_window_steps: int = 3
    min_green_steps: int = 2
    max_hold_steps: int = 30


class PeerNetwork:
    """One-hop neighbor lookup for grid-style intersection IDs."""

    def __init__(self, intersection_ids: list[str] | tuple[str, ...]):
        self._ids = set(intersection_ids)
        self._neighbors = {
            intersection_id: self._derive_neighbors(intersection_id)
            for intersection_id in intersection_ids
        }

    def neighbors(self, intersection_id: str) -> list[str]:
        return list(self._neighbors.get(intersection_id, []))

    def _derive_neighbors(self, intersection_id: str) -> list[str]:
        coord = self._grid_coord(intersection_id)
        if coord is None:
            return []
        row, col = coord
        candidates = [
            f"INT_{row - 1}_{col}",
            f"INT_{row + 1}_{col}",
            f"INT_{row}_{col - 1}",
            f"INT_{row}_{col + 1}",
        ]
        return [candidate for candidate in candidates if candidate in self._ids]

    @staticmethod
    def _grid_coord(intersection_id: str) -> tuple[int, int] | None:
        parts = intersection_id.split("_")
        if len(parts) != 3 or parts[0] != "INT":
            return None
        try:
            return int(parts[1]), int(parts[2])
        except ValueError:
            return None


class IntersectionAgent:
    """Local signal-control policy for one intersection."""

    def __init__(self, intersection_id: str, cfg: AgentConfig = AgentConfig()):
        self.intersection_id = intersection_id
        self.cfg = cfg
        self.invocation_count = 0
        self._holding_ev_phase = False
        self._hold_steps = 0
        self._last_decision: int | None = None
        self._last_reason = ""

    def reset(self) -> None:
        self.invocation_count = 0
        self._holding_ev_phase = False
        self._hold_steps = 0
        self._last_decision = None
        self._last_reason = ""

    @property
    def last_decision(self) -> int | None:
        return self._last_decision

    @property
    def last_reason(self) -> str:
        return self._last_reason

    def decide(
        self,
        observation: IntersectionObservation,
        ev: EVObservation,
        messages: list[PeerMessage],
        is_entry_agent: bool = False,
    ) -> AgentDecision:
        self.invocation_count += 1
        self._last_decision = None
        self._last_reason = ""

        target_phase = self._target_phase(observation, messages, is_entry_agent)
        outgoing = self._outgoing_messages(observation, ev, messages)
        decision_phase = self._phase_decision(observation, target_phase)

        reason = self._last_reason or self._message_reason(messages, is_entry_agent)
        return AgentDecision(target_phase=decision_phase, messages=outgoing, reason=reason)

    def _target_phase(
        self,
        observation: IntersectionObservation,
        messages: list[PeerMessage],
        is_entry_agent: bool,
    ) -> int | None:
        if observation.ev_target_phase is None:
            return None

        if 0 <= observation.ev_eta_steps <= self.cfg.prestage_window_steps:
            return observation.ev_target_phase

        if is_entry_agent and observation.ev_eta_steps >= 0:
            return observation.ev_target_phase

        useful_messages = [
            message for message in messages
            if message.status in {"approaching", "prestage", "preempt"} and message.confidence > 0.0
        ]
        if not useful_messages:
            return None
        best = max(useful_messages, key=lambda message: (message.confidence, -max(message.eta_steps, 0.0)))
        if best.eta_steps < 0 or best.eta_steps <= self.cfg.prestage_window_steps:
            return observation.ev_target_phase
        return None

    def _phase_decision(self, observation: IntersectionObservation, target_phase: int | None) -> int | None:
        if target_phase is None:
            if self._holding_ev_phase:
                self._holding_ev_phase = False
                self._hold_steps = 0
            return None

        if target_phase not in observation.valid_phases:
            self._last_reason = "ev target phase is not controllable"
            return None

        if self._holding_ev_phase:
            self._hold_steps += 1
            if self._hold_steps >= self.cfg.max_hold_steps:
                self._holding_ev_phase = False
                self._hold_steps = 0
                fallback = self._max_pressure_phase(observation)
                self._last_reason = "released EV hold after max hold"
                if fallback != observation.current_phase and observation.elapsed_phase_time >= self.cfg.min_green_steps:
                    self._last_decision = fallback
                    return fallback
                return None

        if observation.current_phase != target_phase and observation.elapsed_phase_time < self.cfg.min_green_steps:
            self._last_reason = "waiting for min green before EV phase"
            return None

        self._holding_ev_phase = True
        self._hold_steps = 0 if observation.current_phase != target_phase else self._hold_steps
        self._last_decision = target_phase
        self._last_reason = "aligned to EV target phase"
        return target_phase

    def _outgoing_messages(
        self,
        observation: IntersectionObservation,
        ev: EVObservation,
        messages: list[PeerMessage],
    ) -> list[PeerMessage]:
        ttl = max((message.ttl for message in messages), default=self.cfg.message_ttl)
        confidence = 1.0
        status = "approaching"
        eta = observation.ev_eta_steps
        target_phase = observation.ev_target_phase

        if target_phase is None or eta < 0:
            if not messages:
                return []
            best = max(messages, key=lambda message: (message.ttl, message.confidence))
            if best.ttl <= 0:
                return []
            ttl = best.ttl
            confidence = max(0.0, best.confidence * 0.75)
            status = best.status
            eta = best.eta_steps
            target_phase = best.target_phase

        if ttl <= 0:
            return []

        if 0 <= eta <= self.cfg.preempt_window_steps:
            status = "preempt"
        elif 0 <= eta <= self.cfg.prestage_window_steps:
            status = "prestage"

        return [
            PeerMessage(
                sender_id=self.intersection_id,
                ev_id=ev.ev_id,
                eta_steps=eta,
                target_phase=target_phase,
                route_index=ev.route_index,
                status=status,
                ttl=ttl,
                confidence=confidence,
            )
        ]

    def _max_pressure_phase(self, observation: IntersectionObservation) -> int:
        if not observation.queue_by_phase:
            return observation.current_phase
        phases = observation.valid_phases or list(observation.queue_by_phase)
        return max(phases, key=lambda phase: observation.queue_by_phase.get(phase, 0.0))

    @staticmethod
    def _message_reason(messages: list[PeerMessage], is_entry_agent: bool) -> str:
        if is_entry_agent:
            return "nearest EV agent invoked"
        if messages:
            return "peer EV intent received"
        return "no EV intent"


class AgentRuntime:
    """Routes peer messages and packages touched-agent decisions."""

    def __init__(self, intersection_ids: list[str] | tuple[str, ...], cfg: AgentConfig = AgentConfig()):
        self.cfg = cfg
        self.network = PeerNetwork(intersection_ids)
        self.agents = {
            intersection_id: IntersectionAgent(intersection_id, cfg)
            for intersection_id in intersection_ids
        }
        self._active_agent_id = ""
        self._last_touched_agent_ids: list[str] = []
        self._last_message_count = 0
        self._pending_message_count = 0
        self._last_decisions_by_agent: dict[str, int] = {}
        self._last_step_reason = "not started"

    def reset(self, observation: DynamicCorridorObservation | None = None) -> None:
        for agent in self.agents.values():
            agent.reset()
        self._active_agent_id = self.nearest_agent_id(observation) if observation else ""
        self._last_touched_agent_ids = []
        self._last_message_count = 0
        self._pending_message_count = 0
        self._last_decisions_by_agent = {}
        self._last_step_reason = "reset"

    def nearest_agent_id(self, observation: DynamicCorridorObservation | None) -> str:
        if observation is None:
            return ""
        if observation.ev.next_intersection in self.agents:
            return observation.ev.next_intersection
        candidates = [
            ix for ix in observation.intersections
            if ix.intersection_id in self.agents and ix.ev_eta_steps >= 0
        ]
        if not candidates:
            return ""
        return min(candidates, key=lambda ix: ix.ev_eta_steps).intersection_id

    def step(self, observation: DynamicCorridorObservation) -> DynamicCorridorAction:
        by_id = {ix.intersection_id: ix for ix in observation.intersections}
        active_agent_id = self.nearest_agent_id(observation)
        self._active_agent_id = active_agent_id
        self._last_touched_agent_ids = []
        self._last_message_count = 0
        self._pending_message_count = 0
        self._last_decisions_by_agent = {}

        if not active_agent_id:
            self._last_step_reason = "no nearest EV agent"
            return DynamicCorridorAction(reason=self._last_step_reason)

        queue: list[tuple[str, PeerMessage | None]] = [(active_agent_id, None)]
        processed: set[str] = set()
        reasons: list[str] = []

        while queue:
            agent_id, incoming = queue.pop(0)
            if agent_id in processed or agent_id not in self.agents or agent_id not in by_id:
                continue

            processed.add(agent_id)
            messages = [] if incoming is None else [incoming]
            decision = self.agents[agent_id].decide(
                by_id[agent_id],
                observation.ev,
                messages,
                is_entry_agent=agent_id == active_agent_id,
            )
            self._last_touched_agent_ids.append(agent_id)
            if decision.target_phase is not None:
                self._last_decisions_by_agent[agent_id] = decision.target_phase
            if decision.reason:
                reasons.append(f"{agent_id}:{decision.reason}")

            for message in decision.messages:
                for neighbor_id in self.network.neighbors(agent_id):
                    if neighbor_id in processed:
                        continue
                    delivered = replace(message, ttl=message.ttl - 1)
                    if delivered.ttl < 0:
                        continue
                    self._last_message_count += 1
                    queue.append((neighbor_id, delivered))

        self._pending_message_count = len(queue)
        self._last_step_reason = "; ".join(reasons) or "no agent decisions"
        return DynamicCorridorAction(
            phase_by_intersection=dict(self._last_decisions_by_agent),
            reason=self._last_step_reason,
        )

    def state(self) -> dict:
        return {
            "active_agent_id": self._active_agent_id,
            "last_touched_agent_ids": list(self._last_touched_agent_ids),
            "last_message_count": self._last_message_count,
            "pending_message_count": self._pending_message_count,
            "last_decisions_by_agent": dict(self._last_decisions_by_agent),
            "last_step_reason": self._last_step_reason,
        }


__all__ = [
    "AgentConfig",
    "AgentRuntime",
    "IntersectionAgent",
    "PeerMessage",
    "PeerNetwork",
]
