"""Tests for the event-driven simulation engine."""

from backend.app.models.events import EventType
from backend.app.simulation.engine import (
    EventDrivenSimulator,
    SimulationState,
    load_default_config,
)


class TestEngineInit:
    def test_load_default_config(self):
        intersections, corridor, profile = load_default_config()
        assert len(intersections) > 0
        assert corridor.corridor_id == "CORR_01"
        assert len(corridor.links) > 0

    def test_simulator_initialize(self):
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=100.0)
        sim.initialize()
        assert sim.event_count > 0

    def test_events_processed_in_order(self):
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=100.0)
        sim.initialize()

        prev_time = -1.0
        for _ in range(50):
            event = sim.step()
            if event is None:
                break
            assert event.scheduled_time >= prev_time
            prev_time = event.scheduled_time

    def test_deterministic_with_same_init(self):
        """Two sims with same config produce same event sequence."""
        intersections, corridor, profile = load_default_config()

        state1 = SimulationState(intersections, corridor, profile)
        sim1 = EventDrivenSimulator(state1, end_time=50.0)
        sim1.initialize()

        state2 = SimulationState(intersections, corridor, profile)
        sim2 = EventDrivenSimulator(state2, end_time=50.0)
        sim2.initialize()

        for _ in range(30):
            e1 = sim1.step()
            e2 = sim2.step()
            if e1 is None or e2 is None:
                break
            assert e1.event_type == e2.event_type
            assert abs(e1.scheduled_time - e2.scheduled_time) < 0.001


class TestEngineExecution:
    def test_run_to_completion(self):
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=60.0)
        sim.initialize()
        sim.run_to_completion()
        assert sim.processed_events > 0
        assert sim.sim_time <= 60.0

    def test_signal_phases_cycle(self):
        """After running, signal should have cycled through phases."""
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=120.0)
        sim.initialize()
        sim.run_to_completion()

        # Check event log for phase starts
        phase_starts = [
            e for e in state.event_log
            if e["event_type"] == "signal_phase_start"
            and e["payload"].get("intersection_id") == "INT_01"
        ]
        # Should have multiple phase changes in 120s
        assert len(phase_starts) >= 3

    def test_metrics_captured(self):
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=30.0)
        sim.initialize()
        sim.run_to_completion()
        assert len(state.metrics_history) > 0


class TestEVInEngine:
    def test_dispatch_ev_in_engine(self):
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=3600.0)
        sim.initialize()

        # Run a bit first
        for _ in range(20):
            sim.step()

        # Dispatch EV
        sim.dispatch_ev("AMB_01", "ambulance", "CORR_01", 60.0, sim.sim_time)
        assert state.ev is not None
        assert state.ev.ev_id == "AMB_01"

        # Run to completion
        sim.run_to_completion()

        # EV should have reached destination or be somewhere on corridor
        ev_events = [
            e for e in state.event_log
            if e["event_type"].startswith("ev_")
        ]
        assert len(ev_events) > 0

    def test_ev_completes_journey(self):
        """EV should reach destination within reasonable time."""
        intersections, corridor, profile = load_default_config()
        state = SimulationState(intersections, corridor, profile)
        sim = EventDrivenSimulator(state, end_time=3600.0)
        sim.initialize()

        sim.dispatch_ev("AMB_01", "ambulance", "CORR_01", 60.0, 0.0)
        sim.run_to_completion()

        # Check if EV reached destination
        dest_events = [
            e for e in state.event_log
            if e["event_type"] == "ev_reach_destination"
        ]
        assert len(dest_events) == 1, "EV should reach destination"
        assert state.ev.arrival_time is not None
