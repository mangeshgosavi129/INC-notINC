"""Tests for Signal FSM — the critical realism component.

Tests verify:
- Phase transitions respect min_green
- Amber is exactly 3s, all_red is exactly 2s
- Cannot interrupt amber or all_red
- Phase change request during min_green is deferred
- Correct phase cycling through ring
"""

from backend.app.models.events import EventType
from backend.app.models.signal_controller import SignalPhaseState


class TestSignalFSMInit:
    def test_start_initial_phase(self, signal_fsm):
        events = signal_fsm.start_initial_phase(0.0)
        assert signal_fsm.state.current_phase == 1
        assert signal_fsm.state.current_state == SignalPhaseState.GREEN

        types = [e.event_type for e in events]
        assert EventType.SIGNAL_PHASE_START in types
        assert EventType.SIGNAL_MIN_GREEN_EXPIRE in types
        assert EventType.SIGNAL_MAX_GREEN_EXPIRE in types

    def test_min_green_expire_time(self, signal_fsm):
        events = signal_fsm.start_initial_phase(0.0)
        min_green_evt = [e for e in events if e.event_type == EventType.SIGNAL_MIN_GREEN_EXPIRE][0]
        assert min_green_evt.scheduled_time == 10.0  # min_green = 10

    def test_max_green_expire_time(self, signal_fsm):
        events = signal_fsm.start_initial_phase(0.0)
        max_green_evt = [e for e in events if e.event_type == EventType.SIGNAL_MAX_GREEN_EXPIRE][0]
        assert max_green_evt.scheduled_time == 45.0  # max_green = 45

    def test_green_movements_on_phase1(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        gm = signal_fsm.green_movements()
        assert gm == {"NBT", "SBT"}


class TestMinGreenConstraint:
    def test_cannot_terminate_before_min_green(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        # Try to terminate at t=5 (before min_green=10)
        events = signal_fsm.request_terminate(5.0)
        # Should NOT produce amber events — request is deferred
        assert len(events) == 0
        assert signal_fsm.state.current_state == SignalPhaseState.GREEN

    def test_deferred_request_executes_after_min_green(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        # Request terminate at t=5
        signal_fsm.request_terminate(5.0)
        # Now min_green expires at t=10
        events = signal_fsm.handle_min_green_expire(10.0)
        # Should now produce amber events
        assert len(events) > 0
        assert signal_fsm.state.current_state == SignalPhaseState.AMBER

    def test_can_terminate_after_min_green(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)
        events = signal_fsm.request_terminate(12.0)
        assert len(events) > 0
        assert signal_fsm.state.current_state == SignalPhaseState.AMBER


class TestAmberAllRedTiming:
    def test_amber_is_3_seconds(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)
        events = signal_fsm.request_terminate(12.0)

        amber_start = [e for e in events if e.event_type == EventType.SIGNAL_AMBER_START]
        amber_end = [e for e in events if e.event_type == EventType.SIGNAL_AMBER_END]
        assert len(amber_start) == 1
        assert len(amber_end) == 1
        assert amber_end[0].scheduled_time - amber_start[0].scheduled_time == 3.0

    def test_all_red_is_2_seconds(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)
        signal_fsm.request_terminate(12.0)
        events = signal_fsm.handle_amber_end(15.0)  # 12 + 3

        all_red_start = [e for e in events if e.event_type == EventType.SIGNAL_ALL_RED_START]
        all_red_end = [e for e in events if e.event_type == EventType.SIGNAL_ALL_RED_END]
        assert len(all_red_start) == 1
        assert len(all_red_end) == 1
        assert all_red_end[0].scheduled_time - all_red_start[0].scheduled_time == 2.0


class TestNonInterruptible:
    def test_cannot_interrupt_amber(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)
        signal_fsm.request_terminate(12.0)
        # Now in AMBER — try another phase change
        events = signal_fsm.request_phase_change(1, 13.0)
        assert len(events) == 0  # Cannot interrupt amber
        assert signal_fsm.state.current_state == SignalPhaseState.AMBER

    def test_cannot_interrupt_all_red(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)
        signal_fsm.request_terminate(12.0)
        signal_fsm.handle_amber_end(15.0)
        # Now in ALL_RED
        assert signal_fsm.state.current_state == SignalPhaseState.ALL_RED
        events = signal_fsm.request_phase_change(1, 16.0)
        assert len(events) == 0  # Cannot interrupt all_red


class TestPhaseCycling:
    def test_full_cycle_phase1_to_phase2(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        assert signal_fsm.state.current_phase == 1

        signal_fsm.handle_min_green_expire(10.0)
        signal_fsm.request_terminate(12.0)
        signal_fsm.handle_amber_end(15.0)
        events = signal_fsm.handle_all_red_end(17.0)

        assert signal_fsm.state.current_phase == 2
        assert signal_fsm.state.current_state == SignalPhaseState.GREEN
        gm = signal_fsm.green_movements()
        assert gm == {"EBT", "WBT"}

    def test_full_cycle_wraps_around(self, signal_fsm):
        # Phase 1 → Phase 2 → Phase 1
        signal_fsm.start_initial_phase(0.0)

        # Terminate phase 1
        signal_fsm.handle_min_green_expire(10.0)
        signal_fsm.request_terminate(12.0)
        signal_fsm.handle_amber_end(15.0)
        signal_fsm.handle_all_red_end(17.0)
        assert signal_fsm.state.current_phase == 2

        # Terminate phase 2
        signal_fsm.handle_min_green_expire(27.0)
        signal_fsm.request_terminate(29.0)
        signal_fsm.handle_amber_end(32.0)
        signal_fsm.handle_all_red_end(34.0)
        assert signal_fsm.state.current_phase == 1
        assert signal_fsm.green_movements() == {"NBT", "SBT"}


class TestPreemption:
    def test_skip_to_specific_phase(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)

        # Request phase 2 directly (EV preemption)
        events = signal_fsm.request_phase_change(2, 12.0, source="mcts")
        assert signal_fsm.state.current_state == SignalPhaseState.AMBER

        # Complete transition
        signal_fsm.handle_amber_end(15.0)
        signal_fsm.handle_all_red_end(17.0)
        assert signal_fsm.state.current_phase == 2

    def test_worst_case_transition_time(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        # At t=0, min_green=10, amber=3, all_red=2
        wc = signal_fsm.worst_case_transition_time(0.0)
        assert wc == 15.0  # 10 + 3 + 2

        # At t=5, remaining min_green=5
        wc = signal_fsm.worst_case_transition_time(5.0)
        assert wc == 10.0  # 5 + 3 + 2

        # After min_green, at t=12
        signal_fsm.handle_min_green_expire(10.0)
        signal_fsm.request_terminate(12.0)
        # Now in AMBER at t=12
        wc = signal_fsm.worst_case_transition_time(12.0)
        assert wc == 5.0  # 3 + 2

    def test_max_green_forces_termination(self, signal_fsm):
        signal_fsm.start_initial_phase(0.0)
        signal_fsm.handle_min_green_expire(10.0)
        # Don't request terminate — let max_green expire
        events = signal_fsm.handle_max_green_expire(45.0)
        assert signal_fsm.state.current_state == SignalPhaseState.AMBER
        assert len(events) > 0
