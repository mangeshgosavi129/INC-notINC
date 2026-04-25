from __future__ import annotations

import pytest

pytest.importorskip("openenv")

from dynamic_corridor_env.decentralized import AgentConfig, AgentRuntime, PeerNetwork
from dynamic_corridor_env.models import DynamicCorridorObservation, EVObservation, IntersectionObservation


def _ix(
    intersection_id: str,
    current_phase: int = 0,
    ev_target_phase: int | None = None,
    ev_eta_steps: float = -1.0,
) -> IntersectionObservation:
    return IntersectionObservation(
        intersection_id=intersection_id,
        current_phase=current_phase,
        valid_phases=[0, 1],
        queue_by_phase={0: 1.0, 1: 4.0},
        elapsed_phase_time=4,
        queue_length=5.0,
        vehicle_count=5,
        mean_speed=2.0,
        ev_target_phase=ev_target_phase,
        ev_eta_steps=ev_eta_steps,
        ev_distance_m=25.0 if ev_eta_steps >= 0 else -1.0,
    )


def _observation(next_intersection: str = "INT_1_1") -> DynamicCorridorObservation:
    return DynamicCorridorObservation(
        intersections=[
            _ix("INT_1_1", current_phase=0, ev_target_phase=1, ev_eta_steps=1),
            _ix("INT_1_2", current_phase=0, ev_target_phase=1, ev_eta_steps=3),
            _ix("INT_2_1", current_phase=0, ev_target_phase=1, ev_eta_steps=4),
            _ix("INT_2_2", current_phase=0, ev_target_phase=1, ev_eta_steps=6),
        ],
        ev=EVObservation(
            ev_id="ambulance_0",
            current_edge="NW_OUT_TO_INT_1_1",
            route_index=0,
            next_intersection=next_intersection,
        ),
    )


def test_peer_network_uses_grid_neighbors_only():
    network = PeerNetwork(["INT_1_1", "INT_1_2", "INT_2_1", "INT_2_2"])

    assert set(network.neighbors("INT_1_1")) == {"INT_1_2", "INT_2_1"}


def test_nearest_agent_comes_from_ev_next_intersection():
    runtime = AgentRuntime(["INT_1_1", "INT_1_2"])

    assert runtime.nearest_agent_id(_observation("INT_1_2")) == "INT_1_2"


def test_step_invokes_nearest_and_message_receiving_agents_only():
    runtime = AgentRuntime(
        ["INT_1_1", "INT_1_2", "INT_2_1", "INT_2_2"],
        cfg=AgentConfig(message_ttl=1),
    )

    action = runtime.step(_observation("INT_1_1"))

    touched = runtime.state()["last_touched_agent_ids"]
    assert touched[0] == "INT_1_1"
    assert set(touched) == {"INT_1_1", "INT_1_2", "INT_2_1"}
    assert "INT_2_2" not in touched
    assert set(action.phase_by_intersection) == set(touched)
    assert runtime.agents["INT_2_2"].invocation_count == 0


def test_runtime_state_is_read_only_snapshot():
    runtime = AgentRuntime(["INT_1_1", "INT_1_2"])
    runtime.step(_observation("INT_1_1"))

    before = runtime.state()
    after = runtime.state()

    assert after == before
    assert after["active_agent_id"] == "INT_1_1"
    assert after["last_decisions_by_agent"]
