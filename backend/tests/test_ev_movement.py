"""Tests for EV movement — CRITICAL: EV must wait at red signals."""

import pytest

from backend.app.models.corridor import Corridor, CorridorLink
from backend.app.models.ev import EVStatus, EmergencyVehicle
from backend.app.models.events import EventType
from backend.app.simulation.ev_movement import (
    bpr_congestion_factor,
    compute_ev_progress,
    compute_link_travel_time,
    dispatch_ev,
    ev_arrive_at_intersection,
    ev_depart_origin,
    ev_enter_intersection,
    ev_signal_turned_green,
)


@pytest.fixture
def simple_corridor():
    return Corridor(
        corridor_id="CORR_TEST",
        name="Test Corridor",
        intersection_ids=["INT_01", "INT_02", "INT_03"],
        links=[
            CorridorLink(
                from_intersection="INT_01", to_intersection="INT_02",
                length_meters=500, free_flow_speed_kmph=40,
                num_lanes=2, capacity_vph=3600,
                ev_approach_movement="SBT",
            ),
            CorridorLink(
                from_intersection="INT_02", to_intersection="INT_03",
                length_meters=400, free_flow_speed_kmph=40,
                num_lanes=2, capacity_vph=3600,
                ev_approach_movement="SBT",
            ),
        ],
    )


@pytest.fixture
def ev():
    return EmergencyVehicle(
        ev_id="AMB_01", vehicle_type="ambulance",
        corridor_id="CORR_TEST", max_speed_kmph=60,
    )


class TestBPRFormula:
    def test_free_flow(self):
        factor = bpr_congestion_factor(0, 3600)
        assert abs(factor - 1.0) < 0.01

    def test_at_capacity(self):
        factor = bpr_congestion_factor(3600, 3600)
        assert factor < 1.0
        assert factor > 0.5  # ~0.87

    def test_over_capacity(self):
        factor = bpr_congestion_factor(7200, 3600)
        assert factor < 0.5


class TestLinkTravelTime:
    def test_free_flow_travel_time(self, simple_corridor):
        link = simple_corridor.links[0]
        # EV at 60 km/h, link at 40 km/h free flow — EV capped at link speed
        tt = compute_link_travel_time(link, 60, 0)
        # 500m at 40 km/h = 500/(40*1000/3600) = 45s
        assert abs(tt - 45.0) < 0.5

    def test_congested_travel_time(self, simple_corridor):
        link = simple_corridor.links[0]
        tt_free = compute_link_travel_time(link, 60, 0)
        tt_congested = compute_link_travel_time(link, 60, 5000)
        assert tt_congested > tt_free


class TestEVDispatch:
    def test_dispatch_sets_status(self, ev, simple_corridor):
        events = dispatch_ev(ev, simple_corridor, 100.0)
        assert ev.status == EVStatus.DISPATCHED
        assert ev.dispatch_time == 100.0
        assert len(ev.route) == 3
        assert len(events) == 1
        assert events[0].event_type == EventType.EV_DEPART_ORIGIN


class TestEVWaitsAtRed:
    """CRITICAL: EV must wait at red signal."""

    def test_ev_waits_at_red(self, ev, simple_corridor):
        """EV arriving at a RED signal must wait — no events produced."""
        ev.status = EVStatus.EN_ROUTE
        ev.current_link_index = 0
        events = ev_arrive_at_intersection(
            ev, "INT_02", link_index=0, is_green=False, sim_time=145.0
        )
        assert ev.status == EVStatus.WAITING_AT_SIGNAL
        assert ev.waiting_at_intersection == "INT_02"
        assert ev.intersections_waited == 1
        assert len(events) == 0  # NO events — EV waits

    def test_ev_proceeds_on_green(self, ev, simple_corridor):
        """EV arriving at a GREEN signal proceeds after startup delay."""
        ev.status = EVStatus.EN_ROUTE
        ev.current_link_index = 0
        events = ev_arrive_at_intersection(
            ev, "INT_02", link_index=0, is_green=True, sim_time=145.0
        )
        assert ev.status == EVStatus.TRAVERSING_INTERSECTION
        assert ev.intersections_cleared == 1
        assert len(events) == 1
        assert events[0].event_type == EventType.EV_ENTER_INTERSECTION
        # Startup delay
        assert events[0].scheduled_time == 145.0 + 1.5

    def test_ev_resumes_when_signal_turns_green(self, ev):
        """Waiting EV gets EV_ENTER_INTERSECTION when signal turns green."""
        ev.status = EVStatus.WAITING_AT_SIGNAL
        ev.waiting_at_intersection = "INT_02"
        ev.current_link_index = 0
        events = ev_signal_turned_green(ev, "INT_02", 155.0)
        assert ev.status == EVStatus.TRAVERSING_INTERSECTION
        assert ev.waiting_at_intersection is None
        assert len(events) == 1
        assert events[0].event_type == EventType.EV_ENTER_INTERSECTION

    def test_ev_wait_time_recorded(self, ev, simple_corridor):
        """EV delay at signals is tracked."""
        ev.status = EVStatus.EN_ROUTE
        ev.current_link_index = 0
        ev_arrive_at_intersection(ev, "INT_02", 0, False, 100.0)
        assert ev.intersections_waited == 1


class TestEVJourney:
    def test_ev_reaches_destination(self, ev, simple_corridor):
        ev.status = EVStatus.EN_ROUTE
        ev.current_link_index = 1  # last link
        events = ev_enter_intersection(ev, simple_corridor, "INT_03", 200.0)
        assert ev.status == EVStatus.ARRIVED
        assert ev.arrival_time == 200.0
        assert len(events) == 1
        assert events[0].event_type == EventType.EV_REACH_DESTINATION

    def test_ev_continues_to_next_link(self, ev, simple_corridor):
        ev.status = EVStatus.EN_ROUTE
        ev.current_link_index = 0
        events = ev_enter_intersection(ev, simple_corridor, "INT_02", 150.0)
        assert ev.status == EVStatus.EN_ROUTE
        assert ev.current_link_index == 1
        assert len(events) == 1
        assert events[0].event_type == EventType.EV_ARRIVE_INTERSECTION


class TestEVProgress:
    def test_idle_progress(self, ev, simple_corridor):
        assert compute_ev_progress(ev, simple_corridor) == 0.0

    def test_arrived_progress(self, ev, simple_corridor):
        ev.status = EVStatus.ARRIVED
        assert compute_ev_progress(ev, simple_corridor) == 100.0

    def test_midway_progress(self, ev, simple_corridor):
        ev.status = EVStatus.EN_ROUTE
        ev.current_link_index = 1
        ev.position_on_link = 0.5
        progress = compute_ev_progress(ev, simple_corridor)
        # (1 + 0.5) / 2 links = 75%
        assert abs(progress - 75.0) < 0.1
