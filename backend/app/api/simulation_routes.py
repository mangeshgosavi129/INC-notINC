"""Simulation routes — /api/simulation/*"""

from fastapi import APIRouter, HTTPException

from backend.app.schemas.requests import SimSpeedRequest, SimulationInitRequest
from backend.app.services.export_service import export_service
from backend.app.services.simulation_service import simulation_service

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


@router.post("/init")
async def init_simulation(req: SimulationInitRequest):
    try:
        run_id = simulation_service.init_simulation(
            name=req.name,
            corridor_id=req.corridor_id,
            controller_type=req.controller_type,
            duration_s=req.duration_s,
            sim_speed=req.sim_speed,
            random_seed=req.random_seed,
            traffic_profile=req.traffic_profile,
            start_time_of_day=req.start_time_of_day,
        )
        return {"run_id": run_id, "status": "initialized", "message": "Simulation ready"}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/start/{run_id}")
async def start_simulation(run_id: str):
    try:
        await simulation_service.start(run_id)
        return {"run_id": run_id, "status": "running"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/pause/{run_id}")
async def pause_simulation(run_id: str):
    try:
        simulation_service.pause(run_id)
        return {"run_id": run_id, "status": "paused"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/resume/{run_id}")
async def resume_simulation(run_id: str):
    try:
        simulation_service.resume(run_id)
        return {"run_id": run_id, "status": "running"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/reset/{run_id}")
async def reset_simulation(run_id: str):
    try:
        simulation_service.reset(run_id)
        return {"run_id": run_id, "status": "reset"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/step/{run_id}")
async def step_simulation(run_id: str):
    try:
        event = simulation_service.step(run_id)
        if event is None:
            return {"run_id": run_id, "status": "complete", "event": None}
        return {"run_id": run_id, "status": "stepped", "event": event}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/run/{run_id}")
async def run_simulation(run_id: str):
    try:
        simulation_service.start_sync(run_id)
        return {"run_id": run_id, "status": "complete"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/speed/{run_id}")
async def set_speed(run_id: str, req: SimSpeedRequest):
    try:
        simulation_service.set_speed(run_id, req.speed)
        return {"run_id": run_id, "speed": req.speed}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/state/{run_id}")
async def get_state(run_id: str):
    try:
        return simulation_service.get_state(run_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/history/{run_id}")
async def get_history(run_id: str, limit: int = 500):
    return simulation_service.get_event_history(run_id, limit)


@router.get("/metrics/{run_id}")
async def get_metrics(run_id: str):
    return simulation_service.get_metrics(run_id)


@router.get("/export/{run_id}")
async def export_run(run_id: str):
    try:
        return export_service.export_json(run_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/list")
async def list_simulations():
    return simulation_service.list_runs()
