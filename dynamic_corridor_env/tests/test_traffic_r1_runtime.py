from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("openenv")

from dynamic_corridor_env.meta_agents import TrafficR1AgentRuntime
from dynamic_corridor_env.models import DynamicCorridorAction, DynamicCorridorObservation, EVObservation, IntersectionObservation
from dynamic_corridor_env.server.dynamic_corridor_environment import DynamicCorridorEnvironment


class FakeChatClient:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = []

    def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                )
            ]
        )


def _observation() -> DynamicCorridorObservation:
    return DynamicCorridorObservation(
        intersections=[
            IntersectionObservation(
                intersection_id="INT_1_1",
                current_phase=0,
                valid_phases=[0, 1],
                queue_by_phase={0: 1.0, 1: 4.0},
                elapsed_phase_time=4,
                ev_target_phase=1,
                ev_eta_steps=1,
                ev_distance_m=25.0,
            )
        ],
        ev=EVObservation(
            current_edge="NW_OUT_TO_INT_1_1",
            next_intersection="INT_1_1",
            progress=0.1,
        ),
    )


def test_traffic_r1_runtime_parses_strict_json_action(caplog):
    payload = {
        "phase_by_intersection": {"INT_1_1": 1},
        "next_edge_id": "NW_OUT_TO_INT_1_1",
        "reason": "clear ambulance route",
    }
    client = FakeChatClient([json.dumps(payload)])
    runtime = TrafficR1AgentRuntime(["INT_1_1"], token="test-token", client=client)

    with caplog.at_level(logging.INFO, logger="dynamic_corridor_env.meta_agents"):
        action = runtime.step(_observation())

    assert action.phase_by_intersection == {"INT_1_1": 1}
    assert action.next_edge_id == "NW_OUT_TO_INT_1_1"
    assert runtime.state()["parse_success"] is True
    assert runtime.state()["fallback"] is False
    assert runtime.state()["last_llm_call_metadata"]["parse_success"] is True
    assert runtime.state()["last_llm_call_metadata"]["model_id"] == "Season998/Traffic-R1"
    assert runtime.state()["last_llm_call_metadata"]["transport"] == "chat_completion"
    assert client.calls[0]["model"] == "Season998/Traffic-R1"
    assert client.calls[0]["response_format"]["type"] == "json_schema"
    records = [record for record in caplog.records if "traffic_r1_llm_call" in record.message]
    assert records
    assert "test-token" not in records[-1].message
    assert '"candidate_edge_count"' in records[-1].message


def test_traffic_r1_runtime_retries_invalid_json_then_falls_back(caplog):
    client = FakeChatClient(["not-json", '{"phase_by_intersection": "bad"}'])
    runtime = TrafficR1AgentRuntime(["INT_1_1"], token="test-token", client=client, max_retries=1)

    with caplog.at_level(logging.INFO, logger="dynamic_corridor_env.meta_agents"):
        action = runtime.step(_observation())

    assert isinstance(action, DynamicCorridorAction)
    assert runtime.state()["parse_success"] is False
    assert runtime.state()["fallback"] is True
    assert "Traffic-R1 fallback" in action.reason
    assert len(client.calls) == 2
    records = [record for record in caplog.records if "traffic_r1_llm_call" in record.message]
    assert len(records) == 2
    assert '"fallback": true' in records[-1].message


def test_traffic_r1_runtime_missing_token_uses_fallback(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    runtime = TrafficR1AgentRuntime(["INT_1_1"], token="", client=None)

    action = runtime.step(_observation())

    assert isinstance(action, DynamicCorridorAction)
    assert runtime.state()["fallback"] is True
    assert runtime.state()["fallback_reason"] == "HF_TOKEN is not configured"


def test_traffic_r1_runtime_uses_text_generation_for_non_chat_models():
    class NonChatClient(FakeChatClient):
        def __init__(self):
            super().__init__([])
            self.text_calls = []

        def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("model_not_supported: not a chat model")

        def text_generation(self, **kwargs):
            self.text_calls.append(kwargs)
            return json.dumps(
                {
                    "phase_by_intersection": {"INT_1_1": 1},
                    "next_edge_id": None,
                    "reason": "text generation strict json",
                }
            )

    client = NonChatClient()
    runtime = TrafficR1AgentRuntime(["INT_1_1"], token="test-token", client=client)

    action = runtime.step(_observation())

    assert action.phase_by_intersection == {"INT_1_1": 1}
    assert runtime.state()["parse_success"] is True
    assert client.text_calls
    assert client.text_calls[0]["grammar"]["type"] == "json"


def test_client_supplied_action_is_not_overwritten_by_runtime(monkeypatch):
    env = DynamicCorridorEnvironment(seed=42)
    client_action = DynamicCorridorAction(
        phase_by_intersection={"INT_1_1": 1},
        next_edge_id="NW_OUT_TO_INT_1_1",
        reason="client action",
    )

    def fail_if_called(_observation):
        raise AssertionError("runtime should not be called for non-empty client actions")

    monkeypatch.setattr(env._agent_runtime, "step", fail_if_called)

    resolved = env._resolve_step_action(_observation(), client_action)

    assert resolved is client_action


def test_disaster_incidents_are_seeded_and_exposed_without_sumo():
    env_a = DynamicCorridorEnvironment(seed=123)
    env_b = DynamicCorridorEnvironment(seed=123)
    env_c = DynamicCorridorEnvironment(seed=124)

    env_a._source_id = "NW_OUT"
    env_a._destination_id = "SE_OUT"
    env_a._episode_index = 1
    env_b._source_id = "NW_OUT"
    env_b._destination_id = "SE_OUT"
    env_b._episode_index = 1
    env_c._source_id = "NW_OUT"
    env_c._destination_id = "SE_OUT"
    env_c._episode_index = 1

    env_a._disaster_incidents = env_a._generate_disaster_incidents(env_a.seed, env_a._episode_index)
    env_b._disaster_incidents = env_b._generate_disaster_incidents(env_b.seed, env_b._episode_index)
    env_c._disaster_incidents = env_c._generate_disaster_incidents(env_c.seed, env_c._episode_index)

    assert [incident.as_dict(0) for incident in env_a._disaster_incidents] == [
        incident.as_dict(0) for incident in env_b._disaster_incidents
    ]
    assert [incident.as_dict(0) for incident in env_a._disaster_incidents] != [
        incident.as_dict(0) for incident in env_c._disaster_incidents
    ]
    context = env_a._disaster_context()
    assert context["enabled"] is True
    assert context["incidents"]
    assert "hospital_deadline_step" in context
