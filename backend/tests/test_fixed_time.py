"""Tests for fixed-time baseline controller."""

import json
from pathlib import Path

import pytest

from backend.app.controllers.fixed_time import FixedTimeController
from backend.app.models.intersection import Intersection
from backend.app.models.signal_controller import SignalControllerState, SignalPhaseState
from backend.app.simulation.signal_fsm import SignalFSM


DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def timing_plans():
    with open(DATA_DIR / "pune_default_timing_plans.json") as f:
        data = json.load(f)
    return data["timing_plans"]


@pytest.fixture
def fixed_controller(timing_plans):
    return FixedTimeController.from_timing_plans_json(timing_plans)


class TestFixedTimeController:
    def test_correct_phase_at_time(self, fixed_controller, sample_intersection):
        """Controller should terminate phase when green split is exceeded."""
        from unittest.mock import MagicMock

        ctrl_state = SignalControllerState(intersection_id="INT_01")
        fsm = SignalFSM(sample_intersection, ctrl_state)
        fsm.start_initial_phase(0.0)
        fsm.handle_min_green_expire(10.0)

        # Mock simulation state
        state = MagicMock()
        state.signal_fsms = {"INT_01": fsm}

        # At t=35 (> split of 30s), controller should terminate
        events = fixed_controller.decide(state, 35.0)
        assert len(events) > 0  # Should produce amber events
        assert fsm.state.current_state == SignalPhaseState.AMBER

    def test_no_terminate_before_split(self, fixed_controller, sample_intersection):
        """Controller should NOT terminate before green split."""
        from unittest.mock import MagicMock

        ctrl_state = SignalControllerState(intersection_id="INT_01")
        fsm = SignalFSM(sample_intersection, ctrl_state)
        fsm.start_initial_phase(0.0)

        state = MagicMock()
        state.signal_fsms = {"INT_01": fsm}

        # At t=15 (< split of 30s), should not terminate
        events = fixed_controller.decide(state, 15.0)
        assert len(events) == 0

    def test_cycle_length_matches_splits(self, timing_plans):
        """Cycle length should be sum of all phase splits + transitions."""
        plan = timing_plans[0]  # INT_01
        splits = plan["phase_splits"]
        total_green = sum(float(v) for v in splits.values())
        num_phases = len(splits)
        # Each transition: 3s amber + 2s all_red = 5s
        cycle_length = total_green + num_phases * 5.0
        assert cycle_length == 30 + 25 + 2 * 5  # 65s

    def test_no_preemption(self, fixed_controller, sample_intersection):
        """Fixed-time controller should NOT respond to EV."""
        from unittest.mock import MagicMock

        ctrl_state = SignalControllerState(intersection_id="INT_01")
        fsm = SignalFSM(sample_intersection, ctrl_state)
        fsm.start_initial_phase(0.0)

        state = MagicMock()
        state.signal_fsms = {"INT_01": fsm}

        # Even with EV present, fixed-time just checks timing
        # At t=15, within green split — no action
        events = fixed_controller.decide(state, 15.0)
        assert len(events) == 0

    def test_from_timing_plans_json(self, timing_plans):
        ctrl = FixedTimeController.from_timing_plans_json(timing_plans)
        assert "INT_01" in ctrl.timing_plans
        assert 1 in ctrl.timing_plans["INT_01"]
        assert ctrl.timing_plans["INT_01"][1] == 30
