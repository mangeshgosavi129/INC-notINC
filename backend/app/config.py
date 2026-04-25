import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


def _env(key: str, default: str) -> str:
    return os.environ.get(f"CC_{key}", default)


class Settings(BaseModel):
    # Server
    host: str = _env("HOST", "0.0.0.0")
    port: int = int(_env("PORT", "8000"))

    # Database
    db_path: str = _env("DB_PATH", str(Path(__file__).parent.parent.parent / "corridor_clearing.db"))

    # Visualization
    viz_mode: Literal["abstract", "leaflet"] = _env("VIZ_MODE", "abstract")  # type: ignore[assignment]

    # Simulation
    sim_speed: float = float(_env("SIM_SPEED", "1.0"))
    sim_duration_s: float = float(_env("SIM_DURATION_S", "3600.0"))

    # AI agent orchestration placeholder
    agent_replan_interval_s: float = float(_env("AGENT_REPLAN_INTERVAL_S", "10.0"))
    agent_replan_interval_ev_s: float = float(_env("AGENT_REPLAN_INTERVAL_EV_S", "3.0"))

    # Paths
    data_dir: Path = Path(__file__).parent.parent / "data"

    # WS throttle
    ws_max_updates_per_sec: int = int(_env("WS_MAX_UPDATES_PER_SEC", "10"))


settings = Settings()
