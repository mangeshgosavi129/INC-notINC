"""Tests for lazy queue model."""

import pytest

from backend.app.simulation.queue_model import ApproachQueue, IntersectionQueues


class TestApproachQueue:
    def test_queue_grows_during_red(self):
        q = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            arrival_rate=0.5, saturation_flow_rate=1.0,
            is_green=False, last_update_time=0.0,
        )
        # After 10s at 0.5 veh/s arrival, red → queue = 5.0
        length = q.materialize(10.0)
        assert abs(length - 5.0) < 0.01

    def test_queue_discharges_during_green(self):
        q = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            queue_length=20.0, arrival_rate=0.3,
            saturation_flow_rate=1.0, is_green=True,
            last_update_time=0.0,
        )
        # Net rate = 0.3 - 1.0 = -0.7, after 10s: 20 - 7 = 13
        length = q.materialize(10.0)
        assert abs(length - 13.0) < 0.01

    def test_queue_never_negative(self):
        q = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            queue_length=2.0, arrival_rate=0.1,
            saturation_flow_rate=1.0, is_green=True,
            last_update_time=0.0,
        )
        # Net rate = 0.1 - 1.0 = -0.9, after 10s: 2 - 9 = -7 → clamped to 0
        length = q.materialize(10.0)
        assert length == 0.0

    def test_lazy_evaluation_consistency(self):
        """Materializing in steps should give same result as single jump."""
        q1 = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            arrival_rate=0.5, saturation_flow_rate=1.0,
            is_green=False, last_update_time=0.0,
        )
        q2 = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            arrival_rate=0.5, saturation_flow_rate=1.0,
            is_green=False, last_update_time=0.0,
        )
        # q1: single jump to t=20
        len1 = q1.materialize(20.0)
        # q2: step by step
        q2.materialize(5.0)
        q2.materialize(10.0)
        q2.materialize(15.0)
        len2 = q2.materialize(20.0)
        assert abs(len1 - len2) < 0.01

    def test_set_green_materializes(self):
        q = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            arrival_rate=0.5, is_green=False, last_update_time=0.0,
        )
        q.set_green(10.0)
        assert q.is_green is True
        assert abs(q.queue_length - 5.0) < 0.01  # 10s × 0.5

    def test_discharge_tracking(self):
        q = ApproachQueue(
            intersection_id="INT_01", movement_id="NBT",
            queue_length=10.0, arrival_rate=0.0,
            saturation_flow_rate=1.0, is_green=True,
            last_update_time=0.0,
        )
        q.materialize(10.0)
        assert q.queue_length == 0.0
        assert q.total_discharged == 10.0


class TestIntersectionQueues:
    def test_add_approach(self):
        iq = IntersectionQueues(intersection_id="INT_01")
        iq.add_approach("NBT", 1800, 2)
        assert "NBT" in iq.queues
        # sat flow = 1800 * 2 / 3600 = 1.0 veh/s
        assert abs(iq.queues["NBT"].saturation_flow_rate - 1.0) < 0.01

    def test_total_queue(self):
        iq = IntersectionQueues(intersection_id="INT_01")
        iq.add_approach("NBT", 1800, 2)
        iq.add_approach("EBT", 1800, 2)
        iq.queues["NBT"].arrival_rate = 0.5
        iq.queues["EBT"].arrival_rate = 0.3
        total = iq.total_queue(10.0)
        assert abs(total - 8.0) < 0.01  # 5.0 + 3.0

    def test_update_green_phases(self):
        iq = IntersectionQueues(intersection_id="INT_01")
        iq.add_approach("NBT", 1800, 2)
        iq.add_approach("EBT", 1800, 2)
        iq.update_green_phases({"NBT"}, 0.0)
        assert iq.queues["NBT"].is_green is True
        assert iq.queues["EBT"].is_green is False
