"""EV service — dispatch, routing, tracking."""

from __future__ import annotations

from backend.app.services.simulation_service import simulation_service


class EVService:
    def dispatch(self, run_id: str, ev_id: str, vehicle_type: str = "ambulance",
                 corridor_id: str = "CORR_01", max_speed_kmph: float = 60.0) -> dict:
        simulation_service.dispatch_ev(
            run_id, ev_id, vehicle_type, corridor_id, max_speed_kmph
        )
        return {"ev_id": ev_id, "status": "dispatched", "corridor_id": corridor_id}

    def get_status(self, run_id: str) -> dict | None:
        return simulation_service.get_ev_status(run_id)

    def get_clearance_log(self, run_id: str) -> list[dict]:
        state = simulation_service._states.get(run_id)
        if state is None:
            return []
        ev_events = [
            e for e in state.event_log
            if e["event_type"].startswith("ev_")
        ]
        return ev_events


ev_service = EVService()
