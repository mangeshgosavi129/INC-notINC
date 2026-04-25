"""Integration test: agent-placeholder vs fixed-time comparison."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestComparisonIntegration:
    def test_agent_comparison_returns_metrics(self, client):
        """Run both controllers with same config and verify comparison payload."""
        seed = 42
        params = {
            "duration_s": 200,
            "sim_speed": 10,
            "random_seed": seed,
            "start_time_of_day": "08:00",
        }

        # Init and run agent placeholder
        res = client.post("/api/simulation/init", json={
            **params, "controller_type": "agent", "name": "Agent Integration"
        })
        assert res.status_code == 200
        agent_id = res.json()["run_id"]

        # Dispatch EV before running
        res = client.post(f"/api/ev/dispatch/{agent_id}", json={
            "ev_id": "AMB_01", "vehicle_type": "ambulance"
        })
        assert res.status_code == 200

        res = client.post(f"/api/simulation/run/{agent_id}")
        assert res.status_code == 200

        # Init and run baseline
        res = client.post("/api/simulation/init", json={
            **params, "controller_type": "fixed_time", "name": "Baseline Integration"
        })
        assert res.status_code == 200
        base_id = res.json()["run_id"]

        res = client.post(f"/api/ev/dispatch/{base_id}", json={
            "ev_id": "AMB_01", "vehicle_type": "ambulance"
        })
        assert res.status_code == 200

        res = client.post(f"/api/simulation/run/{base_id}")
        assert res.status_code == 200

        # Compare
        res = client.get(
            f"/api/analytics/compare-baseline?agent_run_id={agent_id}&baseline_run_id={base_id}"
        )
        assert res.status_code == 200
        comp = res.json()

        assert "agent_ev_delay" in comp
        assert "baseline_ev_delay" in comp
        assert "ev_delay_improvement_pct" in comp

    def test_metrics_populated_after_run(self, client):
        """Verify metrics are captured during simulation run."""
        res = client.post("/api/simulation/init", json={
            "duration_s": 120, "controller_type": "agent", "name": "Metrics Test"
        })
        run_id = res.json()["run_id"]
        client.post(f"/api/simulation/run/{run_id}")

        res = client.get(f"/api/simulation/metrics/{run_id}")
        assert res.status_code == 200
        metrics = res.json()
        assert len(metrics) > 0
        assert "per_intersection" in metrics[0]

    def test_ev_waterfall_endpoint(self, client):
        """Verify EV waterfall analytics endpoint works."""
        res = client.post("/api/simulation/init", json={
            "duration_s": 200, "controller_type": "agent"
        })
        run_id = res.json()["run_id"]
        client.post(f"/api/ev/dispatch/{run_id}")
        client.post(f"/api/simulation/run/{run_id}")

        res = client.get(f"/api/analytics/ev-waterfall/{run_id}")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_simulation_list_tracks_runs(self, client):
        """Verify runs appear in simulation list."""
        res = client.post("/api/simulation/init", json={"name": "Listed Run"})
        run_id = res.json()["run_id"]

        res = client.get("/api/simulation/list")
        assert res.status_code == 200
        runs = res.json()
        assert any(r["run_id"] == run_id for r in runs)
