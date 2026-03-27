"""EV routes — /api/ev/*"""

from fastapi import APIRouter, HTTPException

from backend.app.schemas.requests import EVDispatchRequest, EVRouteRequest
from backend.app.services.ev_service import ev_service
from backend.app.services.simulation_service import simulation_service

router = APIRouter(prefix="/api/ev", tags=["ev"])


@router.post("/dispatch/{run_id}")
async def dispatch_ev(run_id: str, req: EVDispatchRequest):
    try:
        result = ev_service.dispatch(
            run_id, req.ev_id, req.vehicle_type,
            req.corridor_id, req.max_speed_kmph,
            req.start_intersection, req.end_intersection,
        )
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/status/{run_id}")
async def get_ev_status(run_id: str):
    status = ev_service.get_status(run_id)
    if status is None:
        return {"message": "No EV active"}
    return status


@router.get("/clearance-log/{run_id}")
async def get_clearance_log(run_id: str):
    return ev_service.get_clearance_log(run_id)


@router.get("/eta/{run_id}")
async def get_eta(run_id: str):
    status = ev_service.get_status(run_id)
    if status is None:
        return {"eta_s": None}
    return {"eta_s": status.get("eta_s"), "progress_pct": status.get("progress_pct")}
