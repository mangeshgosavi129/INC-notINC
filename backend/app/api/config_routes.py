"""Config routes — /api/config/*, /api/intersections, /api/corridors"""

from fastapi import APIRouter, HTTPException

from backend.app.schemas.requests import ConfigLoadRequest
from backend.app.services.config_service import config_service

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
async def get_config():
    return config_service.get_all_config()


@router.post("/config/load")
async def load_config(req: ConfigLoadRequest):
    try:
        if req.config_type == "intersections":
            config_service.update_intersections(req.config_json)
        elif req.config_type == "corridor":
            config_service.update_corridor(req.config_json)
        elif req.config_type == "mcts":
            config_service.update_mcts_config(req.config_json)
        elif req.config_type == "simulation":
            config_service.update_simulation_config(req.config_json)
        else:
            raise HTTPException(400, f"Unknown config type: {req.config_type}")
        return {"status": "ok", "config_type": req.config_type}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/config/reset")
async def reset_config():
    config_service.reset()
    return {"status": "ok", "message": "Config reset to defaults"}


@router.get("/intersections")
async def list_intersections():
    return [ix.model_dump() for ix in config_service.intersections]


@router.get("/corridors")
async def list_corridors():
    return [config_service.corridor.model_dump()]
