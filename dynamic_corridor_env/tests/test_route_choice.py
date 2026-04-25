from __future__ import annotations

import pytest

pytest.importorskip("openenv")

from dynamic_corridor_env.models import DynamicCorridorAction, DynamicCorridorObservation, EVObservation
from dynamic_corridor_env.server.dynamic_corridor_environment import DynamicCorridorEnvironment


def make_env(seed: int = 42) -> DynamicCorridorEnvironment:
    return DynamicCorridorEnvironment(seed=seed)


def configure_without_sumo(env: DynamicCorridorEnvironment, source: str = "NW_OUT", dest: str = "SE_OUT") -> None:
    env._source_id = source
    env._destination_id = dest
    env._episode_index = 1
    env._road_weights = env._generate_road_weights(env.seed, env._episode_index)
    env._active_route_edges = env._shortest_path_edges(source, dest) or []


def test_road_weights_are_seeded_and_seed_sensitive():
    env_a = make_env(seed=123)
    env_b = make_env(seed=123)
    env_c = make_env(seed=124)
    configure_without_sumo(env_a)
    configure_without_sumo(env_b)
    configure_without_sumo(env_c)

    assert env_a._road_weights == env_b._road_weights
    assert env_a._road_weights != env_c._road_weights
    assert all(0.0 <= weight <= 1.0 for weight in env_a._road_weights.values())


def test_graph_candidates_from_default_source_reach_destination():
    env = make_env()
    configure_without_sumo(env)

    obs = env._route_choice_observation()

    assert obs.source_id == "NW_OUT"
    assert obs.destination_id == "SE_OUT"
    assert obs.current_node == "NW_OUT"
    assert [candidate.edge_id for candidate in obs.candidates] == ["NW_OUT_TO_INT_1_1"]
    assert obs.candidates[0].destination_reachable is True


def test_reverse_edge_is_marked_as_backtrack_and_penalized():
    env = make_env()
    configure_without_sumo(env)

    candidates = env._route_candidates("INT_1_1", "NW_OUT_TO_INT_1_1")
    reverse = next(candidate for candidate in candidates if candidate.edge_id == "INT_1_1_TO_NW_OUT")

    assert reverse.is_backtrack is True
    reward, feedback = env._compute_reward(
        previous={**env._empty_metrics(), "ev_progress": 0.2},
        current={**env._empty_metrics(), "ev_progress": 0.2},
        invalid_actions=0,
        route_feedback={
            "selected_edge": reverse.edge_id,
            "invalid": False,
            "road_weight": reverse.road_weight,
            "estimated_queue": reverse.estimated_queue,
            "moves_closer": reverse.moves_closer,
            "is_backtrack": reverse.is_backtrack,
            "destination_distance_delta": reverse.destination_distance_delta,
        },
    )
    assert reward < -75.0
    assert "route_backtrack=1" in feedback


def test_reward_normalization_clamps_to_api_range():
    env = make_env()

    assert env._normalize_reward(-500.0) == -10.0
    assert env._normalize_reward(500.0) == 10.0
    assert env._normalize_reward(4.25) == 4.25


def test_configurable_endpoint_route_defaults_without_starting_sumo():
    env = make_env()
    configure_without_sumo(env, "SE_OUT", "NW_OUT")

    obs = env._route_choice_observation()

    assert obs.source_id == "SE_OUT"
    assert obs.destination_id == "NW_OUT"
    assert obs.active_route_edges[0] == "SE_OUT_TO_INT_4_4"


def test_ev_approach_edge_prefers_active_route():
    env = make_env()
    configure_without_sumo(env)

    assert env._ev_approach_edge_for("INT_2_4") == "INT_1_4_TO_INT_2_4"


def test_next_edge_action_updates_pending_route_when_vehicle_not_active():
    env = make_env()
    configure_without_sumo(env)

    feedback = env._apply_route_choice(DynamicCorridorAction(next_edge_id="NW_OUT_TO_INT_1_1"))

    assert feedback["invalid"] is False
    assert feedback["reason"] == "accepted"
    assert env._pending_ev_route_edges
    assert env._pending_ev_route_edges[0] == "NW_OUT_TO_INT_1_1"
    assert env._active_route_edges[0] == "NW_OUT_TO_INT_1_1"


def test_destination_node_has_no_route_candidates_or_u_turn():
    env = make_env()
    configure_without_sumo(env)

    candidates = env._route_candidates("SE_OUT", "INT_4_4_TO_SE_OUT")
    feedback = env._apply_route_choice(DynamicCorridorAction(next_edge_id="SE_OUT_TO_INT_4_4"))

    assert candidates == []
    assert feedback["invalid"] is True
    assert feedback["reason"] == "not_candidate"


def test_sumo_label_is_refreshed_before_start(monkeypatch):
    env = make_env()
    configure_without_sumo(env)
    old_label = env._label

    class FakeTraci:
        def start(self, cmd, label):
            self.started_label = label

        def getConnection(self, label):
            return object()

    fake_traci = FakeTraci()

    def fake_import(name, *args, **kwargs):
        if name == "traci":
            return fake_traci
        return real_import(name, *args, **kwargs)

    real_import = __import__
    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(env, "_sumo_binary", lambda binary: binary)

    env._start_sumo()

    assert env._label != old_label
    assert fake_traci.started_label == env._label


def test_route_ppo_policy_returns_next_edge_action(tmp_path):
    torch = pytest.importorskip("torch")
    from dynamic_corridor_env.route_ppo import RoutePpoPolicy, _build_route_policy

    env = make_env()
    configure_without_sumo(env)
    observation = DynamicCorridorObservation(
        ev=EVObservation(progress=0.0),
        route_choice=env._route_choice_observation(),
    )
    checkpoint = tmp_path / "route_ppo_test.pt"
    model = _build_route_policy()
    torch.save({"model_state": model.state_dict()}, checkpoint)

    action = RoutePpoPolicy(checkpoint).act(observation)

    assert isinstance(action, DynamicCorridorAction)
    assert action.next_edge_id == "NW_OUT_TO_INT_1_1"
