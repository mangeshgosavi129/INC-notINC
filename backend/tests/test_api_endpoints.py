"""Tests for API endpoints."""

import pytest

from backend.app.main import app

# Use httpx test client if available, otherwise build simple test
try:
    from httpx import AsyncClient, ASGITransport
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from fastapi.testclient import TestClient
    HAS_TESTCLIENT = True
except ImportError:
    HAS_TESTCLIENT = False


@pytest.fixture
def client():
    if HAS_TESTCLIENT:
        return TestClient(app)
    pytest.skip("TestClient not available")


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestConfigEndpoints:
    def test_get_config(self, client):
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "intersections" in data
        assert "corridor" in data

    def test_list_intersections(self, client):
        response = client.get("/api/intersections")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_list_corridors(self, client):
        response = client.get("/api/corridors")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["corridor_id"] == "CORR_01"

    def test_reset_config(self, client):
        response = client.post("/api/config/reset")
        assert response.status_code == 200


class TestSimulationLifecycle:
    def test_init_simulation(self, client):
        response = client.post("/api/simulation/init", json={
            "name": "Test Run",
            "controller_type": "fixed_time",
            "duration_s": 60.0,
        })
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "initialized"
        return data["run_id"]

    def test_full_lifecycle(self, client):
        # Init
        resp = client.post("/api/simulation/init", json={
            "name": "Lifecycle Test",
            "controller_type": "fixed_time",
            "duration_s": 30.0,
        })
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        # Get state
        resp = client.get(f"/api/simulation/state/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == run_id

        # Step
        resp = client.post(f"/api/simulation/step/{run_id}")
        assert resp.status_code == 200

        # Run to completion
        resp = client.post(f"/api/simulation/run/{run_id}")
        assert resp.status_code == 200

        # Get metrics
        resp = client.get(f"/api/simulation/metrics/{run_id}")
        assert resp.status_code == 200
        assert len(resp.json()) > 0

        # Get history
        resp = client.get(f"/api/simulation/history/{run_id}")
        assert resp.status_code == 200

    def test_list_simulations(self, client):
        # Init a run first
        client.post("/api/simulation/init", json={
            "name": "List Test", "controller_type": "fixed_time", "duration_s": 10.0,
        })
        resp = client.get("/api/simulation/list")
        assert resp.status_code == 200
        assert len(resp.json()) > 0


class TestEVEndpoints:
    def test_dispatch_ev(self, client):
        resp = client.post("/api/simulation/init", json={
            "name": "EV Test", "controller_type": "fixed_time", "duration_s": 300.0,
        })
        run_id = resp.json()["run_id"]

        # Step a few times first
        for _ in range(10):
            client.post(f"/api/simulation/step/{run_id}")

        resp = client.post(f"/api/ev/dispatch/{run_id}", json={
            "ev_id": "AMB_01", "vehicle_type": "ambulance",
            "corridor_id": "CORR_01", "max_speed_kmph": 60.0,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "dispatched"

        # Check status
        resp = client.get(f"/api/ev/status/{run_id}")
        assert resp.status_code == 200

        # Check ETA
        resp = client.get(f"/api/ev/eta/{run_id}")
        assert resp.status_code == 200


class TestDriverEndpoints:
    def test_driver_status(self, client):
        resp = client.post("/api/simulation/init", json={
            "name": "Driver Test", "controller_type": "fixed_time", "duration_s": 300.0,
        })
        run_id = resp.json()["run_id"]

        resp = client.get(f"/api/driver/status/{run_id}")
        assert resp.status_code == 200

    def test_driver_route(self, client):
        resp = client.post("/api/simulation/init", json={
            "name": "Route Test", "controller_type": "fixed_time", "duration_s": 60.0,
        })
        run_id = resp.json()["run_id"]

        resp = client.get(f"/api/driver/route/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "route" in data
        assert len(data["route"]) == 4  # 4 links


class TestAnalyticsEndpoints:
    def test_analytics_after_run(self, client):
        resp = client.post("/api/simulation/init", json={
            "name": "Analytics Test", "controller_type": "fixed_time", "duration_s": 30.0,
        })
        run_id = resp.json()["run_id"]
        client.post(f"/api/simulation/run/{run_id}")

        resp = client.get(f"/api/analytics/queue/{run_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/analytics/plots/{run_id}")
        assert resp.status_code == 200


class TestAdminEndpoints:
    def test_control_room(self, client):
        resp = client.post("/api/simulation/init", json={
            "name": "Admin Test", "controller_type": "fixed_time", "duration_s": 60.0,
        })
        run_id = resp.json()["run_id"]

        resp = client.get(f"/api/admin/control-room/{run_id}")
        assert resp.status_code == 200

    def test_alerts(self, client):
        resp = client.post("/api/simulation/init", json={
            "name": "Alert Test", "controller_type": "fixed_time", "duration_s": 60.0,
        })
        run_id = resp.json()["run_id"]

        resp = client.get(f"/api/admin/alerts/{run_id}")
        assert resp.status_code == 200
