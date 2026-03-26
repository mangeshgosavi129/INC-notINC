from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Dynamic Corridor Clearing — RH-MCTS",
    description="Pune Traffic Emergency Vehicle Corridor Clearing System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "viz_mode": settings.viz_mode}


from backend.app.api.config_routes import router as config_router
from backend.app.api.simulation_routes import router as simulation_router
from backend.app.api.control_routes import router as control_router
from backend.app.api.ev_routes import router as ev_router
from backend.app.api.admin_routes import router as admin_router
from backend.app.api.driver_routes import router as driver_router
from backend.app.api.analytics_routes import router as analytics_router
from backend.app.api.ws_routes import router as ws_router

app.include_router(config_router)
app.include_router(simulation_router)
app.include_router(control_router)
app.include_router(ev_router)
app.include_router(admin_router)
app.include_router(driver_router)
app.include_router(analytics_router)
app.include_router(ws_router)
