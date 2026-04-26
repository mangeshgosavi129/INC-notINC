"""Agent runtimes for the dynamic corridor environment.

The default runtime is a Hugging Face hosted Traffic-R1 LLM controller that
emits strict JSON matching DynamicCorridorAction. The legacy Meta AI Hack PPO
adapter is retained as an opt-in local mode for offline experiments.

Traffic-R1 falls back to the rule-based decentralized runtime whenever the
Hugging Face token, network, model response, or JSON validation is unavailable.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .decentralized import AgentRuntime
    from .models import DynamicCorridorAction, DynamicCorridorObservation, IntersectionObservation
except ImportError:
    from decentralized import AgentRuntime
    from models import DynamicCorridorAction, DynamicCorridorObservation, IntersectionObservation


OBS_DIM = 16
N_ACTIONS = 3
MAX_ETA = 60.0
MAX_QUEUE = 40.0
MAX_ELAPSED_STEPS = 12.0
DEFAULT_HF_MODEL = "Season998/Traffic-R1"
LOGGER = logging.getLogger(__name__)
UVICORN_LOGGER = logging.getLogger("uvicorn.error")


ACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "phase_by_intersection": {
            "type": "object",
            "additionalProperties": {"type": "integer"},
        },
        "next_edge_id": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
        },
        "reason": {"type": "string"},
    },
    "required": ["phase_by_intersection", "next_edge_id", "reason"],
    "additionalProperties": False,
}


def _model_dump_jsonable(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _env_file_value(name: str) -> str | None:
    search_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for path in search_paths:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"').strip("'")
        except OSError:
            continue
    return None


class TrafficR1AgentRuntime:
    """Hugging Face Traffic-R1 controller with strict JSON action output."""

    def __init__(
        self,
        intersection_ids: list[str] | tuple[str, ...],
        model_id: str | None = None,
        provider: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        client: Any | None = None,
    ):
        self.intersection_ids = list(intersection_ids)
        self._fallback = AgentRuntime(intersection_ids)
        self._model_id = model_id or os.getenv("HF_MODEL", DEFAULT_HF_MODEL)
        self._provider = provider or os.getenv("HF_PROVIDER", "auto")
        self._token = token if token is not None else os.getenv("HF_TOKEN") or _env_file_value("HF_TOKEN")
        self._timeout_seconds = float(timeout_seconds if timeout_seconds is not None else os.getenv("HF_TIMEOUT_SECONDS", "20"))
        self._max_retries = int(max_retries if max_retries is not None else os.getenv("HF_MAX_RETRIES", "2"))
        self._client = client
        self._active_agent_id = ""
        self._last_touched_agent_ids: list[str] = []
        self._last_decisions_by_agent: dict[str, int] = {}
        self._last_step_reason = "not started"
        self._last_parse_success = False
        self._last_retry_count = 0
        self._last_fallback = False
        self._last_fallback_reason = ""
        self._last_raw_response = ""
        self._last_llm_call_metadata: dict[str, Any] = {}
        self._last_transport = ""

    def reset(self, observation: DynamicCorridorObservation | None = None) -> None:
        self._fallback.reset(observation)
        self._active_agent_id = self._fallback.nearest_agent_id(observation) if observation else ""
        self._last_touched_agent_ids = []
        self._last_decisions_by_agent = {}
        self._last_step_reason = "reset"
        self._last_parse_success = False
        self._last_retry_count = 0
        self._last_fallback = False
        self._last_fallback_reason = ""
        self._last_raw_response = ""
        self._last_llm_call_metadata = {}
        self._last_transport = ""

    def step(self, observation: DynamicCorridorObservation) -> DynamicCorridorAction:
        self._active_agent_id = self._fallback.nearest_agent_id(observation)
        self._last_touched_agent_ids = [ix.intersection_id for ix in observation.intersections]
        self._last_decisions_by_agent = {}
        self._last_parse_success = False
        self._last_retry_count = 0
        self._last_fallback = False
        self._last_fallback_reason = ""
        self._last_raw_response = ""
        self._last_llm_call_metadata = {}
        self._last_transport = ""

        if not self._token and self._client is None:
            return self._fallback_action(observation, "HF_TOKEN is not configured")

        last_error = ""
        messages = self._messages(observation)
        call_id = uuid.uuid4().hex
        for attempt in range(self._max_retries + 1):
            started = time.perf_counter()
            content = ""
            try:
                content = self._chat_completion(messages)
                self._last_raw_response = content[:1000]
                action = self._parse_action(content)
                self._last_parse_success = True
                self._last_retry_count = attempt
                self._last_decisions_by_agent = dict(action.phase_by_intersection)
                self._last_step_reason = action.reason or "Traffic-R1 strict JSON action"
                self._log_llm_call(
                    call_id=call_id,
                    attempt=attempt,
                    messages=messages,
                    observation=observation,
                    started=started,
                    content=content,
                    parse_success=True,
                    error="",
                    fallback=False,
                )
                return action
            except Exception as exc:  # pragma: no cover - exact HF errors vary by provider
                last_error = str(exc)
                self._log_llm_call(
                    call_id=call_id,
                    attempt=attempt,
                    messages=messages,
                    observation=observation,
                    started=started,
                    content=content,
                    parse_success=False,
                    error=last_error,
                    fallback=attempt >= self._max_retries,
                )
                messages = self._messages(observation, validation_error=last_error)

        return self._fallback_action(observation, last_error or "Traffic-R1 did not return a valid action")

    def _chat_completion(self, messages: list[dict[str, str]]) -> str:
        client = self._client or self._build_client()
        try:
            self._last_transport = "chat_completion"
            response = client.chat_completion(
                model=self._model_id,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "dynamic_corridor_action",
                        "schema": ACTION_JSON_SCHEMA,
                        "strict": True,
                    },
                },
                max_tokens=512,
            )
            message = response.choices[0].message
            content = getattr(message, "content", message.get("content") if isinstance(message, dict) else "")
        except Exception as exc:
            if not self._is_non_chat_model_error(exc):
                raise
            self._last_transport = "text_generation"
            content = self._text_generation(client, messages)
        if isinstance(content, dict):
            return json.dumps(content, separators=(",", ":"))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty Traffic-R1 response")
        return content

    def _log_llm_call(
        self,
        call_id: str,
        attempt: int,
        messages: list[dict[str, str]],
        observation: DynamicCorridorObservation,
        started: float,
        content: str,
        parse_success: bool,
        error: str,
        fallback: bool,
    ) -> None:
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        metadata = {
            "event": "traffic_r1_llm_call",
            "call_id": call_id,
            "attempt": attempt,
            "max_retries": self._max_retries,
            "model_id": self._model_id,
            "provider": self._provider,
            "transport": self._last_transport or "unknown",
            "timeout_seconds": self._timeout_seconds,
            "token_configured": bool(self._token),
            "client_injected": self._client is not None,
            "response_format": "json_schema",
            "json_grammar_requested": self._last_transport == "text_generation",
            "observation_task_id": observation.task_id,
            "observation_step": observation.step,
            "observation_sim_time": observation.sim_time,
            "intersection_count": len(observation.intersections),
            "candidate_edge_count": len(observation.route_choice.candidates),
            "ev_progress": observation.ev.progress,
            "ev_waiting_time": observation.ev.waiting_time,
            "ev_current_edge": observation.ev.current_edge,
            "ev_next_intersection": observation.ev.next_intersection,
            "route_current_node": observation.route_choice.current_node,
            "route_destination": observation.route_choice.destination_id,
            "message_count": len(messages),
            "prompt_char_count": sum(len(message.get("content", "")) for message in messages),
            "response_char_count": len(content or ""),
            "parse_success": parse_success,
            "fallback": fallback,
            "error": error[:500],
            "duration_ms": duration_ms,
        }
        self._last_llm_call_metadata = metadata
        line = json.dumps(metadata, sort_keys=True)
        LOGGER.info("traffic_r1_llm_call %s", line)
        UVICORN_LOGGER.info("traffic_r1_llm_call %s", line)

    @staticmethod
    def _is_non_chat_model_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "not a chat model" in message or "model_not_supported" in message

    def _text_generation(self, client: Any, messages: list[dict[str, str]]) -> str:
        prompt = (
            f"{messages[0]['content']}\n\n"
            f"{messages[1]['content']}\n\n"
            "Strict JSON response:"
        )
        kwargs = {
            "model": self._model_id,
            "prompt": prompt,
            "max_new_tokens": 512,
            "grammar": {"type": "json", "value": ACTION_JSON_SCHEMA},
        }
        try:
            response = client.text_generation(**kwargs)
        except TypeError:
            kwargs.pop("grammar", None)
            response = client.text_generation(**kwargs)
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            return str(response.get("generated_text", ""))
        return str(response)

    def _build_client(self):
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is required for Traffic-R1 runtime") from exc

        kwargs = {
            "provider": self._provider,
            "api_key": self._token,
            "timeout": self._timeout_seconds,
        }
        try:
            return InferenceClient(**kwargs)
        except TypeError:
            kwargs.pop("timeout", None)
            return InferenceClient(**kwargs)

    def _parse_action(self, content: str) -> DynamicCorridorAction:
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("Traffic-R1 response must be a JSON object")
        action = DynamicCorridorAction(**payload)
        action.phase_by_intersection = {
            str(tls_id): int(phase)
            for tls_id, phase in action.phase_by_intersection.items()
        }
        if action.next_edge_id == "":
            action.next_edge_id = None
        return action

    def _messages(
        self,
        observation: DynamicCorridorObservation,
        validation_error: str | None = None,
    ) -> list[dict[str, str]]:
        observation_json = json.dumps(_model_dump_jsonable(observation), separators=(",", ":"), sort_keys=True)
        valid_intersections = ",".join(ix.intersection_id for ix in observation.intersections)
        valid_edges = ",".join(candidate.edge_id for candidate in observation.route_choice.candidates)
        system = (
            "You are Traffic-R1 controlling a disaster-mode emergency traffic corridor. "
            "Return only strict JSON matching this schema: "
            '{"phase_by_intersection":{"INTERSECTION_ID":PHASE_INT},"next_edge_id":"EDGE_ID_OR_NULL","reason":"short reason"}. '
            "Choose only valid green phases and candidate next edges when acting. "
            "Prioritize ambulance progress, avoid blocked disaster edges, reduce waiting time, and limit unnecessary phase churn."
        )
        user = (
            f"Valid intersections: {valid_intersections or 'none'}\n"
            f"Candidate next edges: {valid_edges or 'none'}\n"
            f"Observation JSON: {observation_json}"
        )
        if validation_error:
            user += f"\nPrevious response was invalid: {validation_error}. Return corrected strict JSON only."
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _fallback_action(self, observation: DynamicCorridorObservation, reason: str) -> DynamicCorridorAction:
        action = self._fallback.step(observation)
        fallback_state = self._fallback.state()
        self._active_agent_id = fallback_state.get("active_agent_id", "")
        self._last_touched_agent_ids = list(fallback_state.get("last_touched_agent_ids", []))
        self._last_decisions_by_agent = dict(action.phase_by_intersection)
        self._last_parse_success = False
        self._last_retry_count = self._max_retries
        self._last_fallback = True
        self._last_fallback_reason = reason
        self._last_step_reason = f"Traffic-R1 fallback: {reason}"
        action.reason = f"{self._last_step_reason} | {action.reason}"
        return action

    def state(self) -> dict[str, Any]:
        fallback_state = self._fallback.state()
        return {
            "mode": "traffic_r1",
            "model_id": self._model_id,
            "provider": self._provider,
            "parse_success": self._last_parse_success,
            "retry_count": self._last_retry_count,
            "fallback": self._last_fallback,
            "fallback_reason": self._last_fallback_reason,
            "last_llm_call_metadata": dict(self._last_llm_call_metadata),
            "active_agent_id": self._active_agent_id or fallback_state.get("active_agent_id", ""),
            "last_touched_agent_ids": list(self._last_touched_agent_ids),
            "last_message_count": fallback_state.get("last_message_count", 0),
            "pending_message_count": fallback_state.get("pending_message_count", 0),
            "last_decisions_by_agent": dict(self._last_decisions_by_agent),
            "last_step_reason": self._last_step_reason,
        }


def _torch():
    try:
        import torch
        import torch.nn as nn
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PyTorch is required for Meta AI Hack PPO agents. Install with `pip install torch`.") from exc
    return torch, nn


def default_meta_hack_checkpoint() -> Path:
    """Default read-only location of the Meta AI Hack corridor checkpoint."""
    root = Path(os.getenv("DYNAMIC_CORRIDOR_META_HACK_DIR", Path(__file__).resolve().parents[1] / "META AI HACK"))
    return root / "checkpoints" / "corridor_latest.pt"


def _phase_slot(ix: IntersectionObservation) -> tuple[list[int], int]:
    phases = list(ix.valid_phases) or sorted(ix.queue_by_phase)
    if not phases:
        phases = [ix.current_phase]
    try:
        current_slot = phases.index(ix.current_phase)
    except ValueError:
        current_slot = 0
    return phases[:4], current_slot


def _phase_norm(phase: int | None, phases: list[int]) -> float:
    if phase is None or not phases:
        return 0.0
    try:
        slot = phases.index(phase)
    except ValueError:
        slot = 0
    return slot / max(len(phases) - 1, 1)


def _upstream_features(
    ix: IntersectionObservation,
    observation: DynamicCorridorObservation,
    phases: list[int],
) -> tuple[float, float, float, float]:
    """Approximate Meta corridor upstream message features from OpenEnv state."""
    if ix.ev_eta_steps < 0:
        return 0.0, 0.0, 0.0, 0.0

    upstream = [
        other for other in observation.intersections
        if 0 <= other.ev_eta_steps < ix.ev_eta_steps
    ]
    if not upstream:
        return 0.0, 0.0, 0.0, 0.0

    nearest = min(upstream, key=lambda other: ix.ev_eta_steps - other.ev_eta_steps)
    eta = min(max(nearest.ev_eta_steps, 0.0) / MAX_ETA, 1.0)
    urgency = 1.0 / (1.0 + max(nearest.ev_eta_steps, 0.0))
    return 1.0, eta, _phase_norm(nearest.ev_target_phase, phases), urgency


def encode_meta_intersection_observation(
    ix: IntersectionObservation,
    observation: DynamicCorridorObservation,
) -> list[float]:
    """Build the Meta AI Hack 16-dim per-intersection observation."""
    phases, current_slot = _phase_slot(ix)
    queues = [min(max(ix.queue_by_phase.get(phase, 0.0) / MAX_QUEUE, 0.0), 1.0) for phase in phases]
    queues.extend([0.0] * (4 - len(queues)))

    ev_active = 0.0 if observation.ev.arrived else 1.0
    on_route = 1.0 if ix.is_on_ev_route or ix.ev_eta_steps >= 0 else 0.0
    eta_norm = 0.0
    urgency = 0.0
    if ix.ev_eta_steps >= 0:
        eta_norm = min(max(ix.ev_eta_steps, 0.0) / MAX_ETA, 1.0)
        urgency = 1.0 / (1.0 + max(ix.ev_eta_steps, 0.0))

    phase_zero_pressure = 0.0
    if phases:
        phase_zero_pressure = min(max(ix.queue_by_phase.get(phases[0], 0.0) / MAX_QUEUE, 0.0), 1.0)

    upstream_flag, upstream_eta, upstream_phase, upstream_urgency = _upstream_features(ix, observation, phases)

    values = [
        *queues[:4],
        current_slot / max(len(phases) - 1, 1),
        min(max(ix.elapsed_phase_time / MAX_ELAPSED_STEPS, 0.0), 1.0),
        ev_active,
        on_route,
        eta_norm,
        urgency,
        _phase_norm(ix.ev_target_phase, phases),
        phase_zero_pressure,
        upstream_flag,
        upstream_eta,
        upstream_phase,
        upstream_urgency,
    ]
    return [float(min(max(value, 0.0), 1.0)) for value in values]


def _next_valid_phase(ix: IntersectionObservation) -> int | None:
    phases = list(ix.valid_phases) or sorted(ix.queue_by_phase)
    if not phases:
        return None
    if ix.current_phase in phases:
        return phases[(phases.index(ix.current_phase) + 1) % len(phases)]
    return phases[0]


def target_phase_for_meta_action(ix: IntersectionObservation, action: int) -> int | None:
    """Translate Meta action id to a SUMO target phase."""
    if action == 1:
        return _next_valid_phase(ix)
    return None


def _build_actor_critic():
    torch, nn = _torch()

    class ActorCritic(nn.Module):
        def __init__(self, obs_dim: int = OBS_DIM, n_actions: int = N_ACTIONS, hidden: int = 64):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Linear(obs_dim, hidden),
                nn.Tanh(),
                nn.Linear(hidden, hidden),
                nn.Tanh(),
            )
            self.actor = nn.Linear(hidden, n_actions)
            self.critic = nn.Linear(hidden, 1)

            for layer in [*self.backbone, self.actor, self.critic]:
                if isinstance(layer, nn.Linear):
                    nn.init.orthogonal_(layer.weight, gain=math.sqrt(2))
                    nn.init.constant_(layer.bias, 0.0)
            nn.init.orthogonal_(self.actor.weight, gain=0.01)

        def forward(self, x):
            features = self.backbone(x)
            logits = self.actor(features)
            value = self.critic(features).squeeze(-1)
            return logits, value

    return ActorCritic()


@dataclass(frozen=True)
class MetaAgentStatus:
    mode: str
    checkpoint_path: str
    checkpoint_loaded: bool
    fallback_reason: str


class MetaPpoAgentRuntime:
    """Shared PPO policy runtime compatible with DynamicCorridorEnvironment."""

    def __init__(
        self,
        intersection_ids: list[str] | tuple[str, ...],
        checkpoint_path: str | Path | None = None,
        allow_untrained: bool | None = None,
        device: str = "cpu",
    ):
        self.intersection_ids = list(intersection_ids)
        self._fallback = AgentRuntime(intersection_ids)
        self._checkpoint_path = Path(checkpoint_path) if checkpoint_path else default_meta_hack_checkpoint()
        self._allow_untrained = (
            os.getenv("DYNAMIC_CORRIDOR_ALLOW_UNTRAINED_META_AGENT", "0") == "1"
            if allow_untrained is None else allow_untrained
        )
        self._device = device
        self._model = None
        self._torch = None
        self._fallback_reason = ""
        self._active_agent_id = ""
        self._last_actions_by_agent: dict[str, int] = {}
        self._last_decisions_by_agent: dict[str, int] = {}
        self._last_touched_agent_ids: list[str] = []
        self._last_step_reason = "not started"

        self._load_model()

    def _load_model(self) -> None:
        if not self._checkpoint_path.exists() and not self._allow_untrained:
            self._fallback_reason = f"checkpoint not found: {self._checkpoint_path}"
            return

        try:
            torch, _ = _torch()
            self._torch = torch
            self._model = _build_actor_critic().to(self._device)
            if self._checkpoint_path.exists():
                checkpoint = torch.load(self._checkpoint_path, map_location=self._device)
                state = checkpoint.get("model_state", checkpoint)
                self._model.load_state_dict(state)
                self._fallback_reason = ""
            else:
                self._fallback_reason = "untrained Meta PPO model enabled"
            self._model.eval()
        except Exception as exc:
            self._model = None
            self._torch = None
            self._fallback_reason = str(exc)

    @property
    def checkpoint_loaded(self) -> bool:
        return self._model is not None and self._checkpoint_path.exists()

    def reset(self, observation: DynamicCorridorObservation | None = None) -> None:
        self._fallback.reset(observation)
        self._active_agent_id = self._fallback.nearest_agent_id(observation) if observation else ""
        self._last_actions_by_agent = {}
        self._last_decisions_by_agent = {}
        self._last_touched_agent_ids = []
        self._last_step_reason = "reset"

    def step(self, observation: DynamicCorridorObservation) -> DynamicCorridorAction:
        if self._model is None or self._torch is None:
            action = self._fallback.step(observation)
            self._active_agent_id = self._fallback.state().get("active_agent_id", "")
            self._last_actions_by_agent = {}
            self._last_decisions_by_agent = dict(action.phase_by_intersection)
            self._last_touched_agent_ids = list(self._fallback.state().get("last_touched_agent_ids", []))
            self._last_step_reason = f"Meta PPO fallback: {self._fallback_reason}"
            action.reason = self._last_step_reason + " | " + action.reason
            return action

        phase_by_intersection: dict[str, int] = {}
        actions_by_agent: dict[str, int] = {}
        touched: list[str] = []
        self._active_agent_id = self._fallback.nearest_agent_id(observation)
        with self._torch.no_grad():
            for ix in observation.intersections:
                if ix.intersection_id not in self.intersection_ids:
                    continue
                vector = encode_meta_intersection_observation(ix, observation)
                tensor = self._torch.tensor(vector, dtype=self._torch.float32, device=self._device).unsqueeze(0)
                logits, _ = self._model(tensor)
                action_id = int(self._torch.argmax(logits, dim=-1).item())
                actions_by_agent[ix.intersection_id] = action_id
                touched.append(ix.intersection_id)
                target_phase = target_phase_for_meta_action(ix, action_id)
                if target_phase is not None and target_phase != ix.current_phase:
                    phase_by_intersection[ix.intersection_id] = target_phase

        self._last_actions_by_agent = actions_by_agent
        self._last_decisions_by_agent = phase_by_intersection
        self._last_touched_agent_ids = touched
        self._last_step_reason = (
            "Meta AI Hack PPO shared policy"
            if self.checkpoint_loaded else
            "Meta AI Hack PPO shared policy (untrained weights)"
        )
        return DynamicCorridorAction(
            phase_by_intersection=phase_by_intersection,
            reason=self._last_step_reason,
        )

    def state(self) -> dict[str, Any]:
        fallback_state = self._fallback.state()
        return {
            "mode": "meta_ppo" if self._model is not None else "meta_ppo_fallback",
            "checkpoint_path": str(self._checkpoint_path),
            "checkpoint_loaded": self.checkpoint_loaded,
            "fallback_reason": self._fallback_reason,
            "active_agent_id": self._active_agent_id or fallback_state.get("active_agent_id", ""),
            "last_touched_agent_ids": list(self._last_touched_agent_ids),
            "last_message_count": fallback_state.get("last_message_count", 0),
            "pending_message_count": fallback_state.get("pending_message_count", 0),
            "last_actions_by_agent": dict(self._last_actions_by_agent),
            "last_decisions_by_agent": dict(self._last_decisions_by_agent),
            "last_step_reason": self._last_step_reason,
        }


def build_agent_runtime(intersection_ids: list[str] | tuple[str, ...]):
    """Create the configured runtime without requiring PyTorch by default."""
    mode = os.getenv("DYNAMIC_CORRIDOR_AGENT_MODE", "traffic_r1").strip().lower()
    if mode in {"legacy", "heuristic", "decentralized", "peer"}:
        return AgentRuntime(intersection_ids)
    if mode in {"meta", "meta_ppo", "ppo", "nn"}:
        checkpoint_path = os.getenv("DYNAMIC_CORRIDOR_META_AGENT_CHECKPOINT")
        return MetaPpoAgentRuntime(intersection_ids, checkpoint_path=checkpoint_path)

    return TrafficR1AgentRuntime(intersection_ids)


__all__ = [
    "MAX_ELAPSED_STEPS",
    "MAX_ETA",
    "MAX_QUEUE",
    "MetaAgentStatus",
    "MetaPpoAgentRuntime",
    "N_ACTIONS",
    "OBS_DIM",
    "TrafficR1AgentRuntime",
    "build_agent_runtime",
    "default_meta_hack_checkpoint",
    "encode_meta_intersection_observation",
    "target_phase_for_meta_action",
]
