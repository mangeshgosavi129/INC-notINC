from __future__ import annotations

import pytest

pytest.importorskip("openenv")

from dynamic_corridor_env.models import DynamicCorridorObservation, EVObservation, IntersectionObservation
from dynamic_corridor_env.policies import EmergencyAwarePolicy, FixedTimePolicy, GreenWavePolicy


def test_fixed_time_policy_tracks_intersections_independently():
    policy = FixedTimePolicy(cycle_steps=2, min_green_steps=0)
    obs = {"queues": {0: 5.0, 1: 3.0}, "current_phase": 0, "elapsed": 0, "ev": None}

    assert policy.act("INT_A", obs) == "keep"
    assert policy.act("INT_A", obs) == "switch"
    assert policy.act("INT_B", obs) == "keep"


def test_emergency_policy_preempts_before_eta_zero():
    policy = EmergencyAwarePolicy()
    obs = {
        "queues": {0: 5.0, 1: 3.0},
        "current_phase": 1,
        "elapsed": 5,
        "ev": {"entry_phase": 0, "eta_steps": 2, "distance_m": 10.0, "cleared": False},
    }

    assert policy.act("INT_A", obs) == "switch"


def test_green_wave_policy_is_available():
    policy = GreenWavePolicy()
    policy.register_intersection("INT_A", 0)
    obs = {
        "queues": {0: 0.0, 1: 4.0},
        "current_phase": 1,
        "elapsed": 5,
        "ev": {"entry_phase": 0, "eta_steps": 2, "distance_m": 25.0, "cleared": False},
    }

    assert policy.act("INT_A", obs, lead_ev_eta=2) == "switch"


def test_ppo_policy_returns_dynamic_corridor_action(tmp_path):
    torch = pytest.importorskip("torch")
    from dynamic_corridor_env.models import DynamicCorridorAction
    from dynamic_corridor_env.ppo import OBS_DIM, PpoPolicy, _build_policy

    model = _build_policy()
    checkpoint = tmp_path / "ppo_test.pt"
    torch.save(
        {
            "obs_dim": OBS_DIM,
            "model_state": model.state_dict(),
        },
        checkpoint,
    )

    policy = PpoPolicy(checkpoint)
    observation = DynamicCorridorObservation(
        intersections=[
            IntersectionObservation(
                intersection_id="INT_1_1",
                current_phase=0,
                valid_phases=[0, 1],
                queue_by_phase={0: 1.0, 1: 4.0},
                elapsed_phase_time=3,
                queue_length=5.0,
                vehicle_count=5,
                mean_speed=2.0,
                ev_target_phase=1,
                ev_eta_steps=2,
                ev_distance_m=25.0,
            )
        ],
        ev=EVObservation(current_edge="NW_OUT_TO_INT_1_1", next_intersection="INT_1_1"),
    )

    action = policy.act(observation)
    assert isinstance(action, DynamicCorridorAction)
    assert set(action.phase_by_intersection) == {"INT_1_1"}
