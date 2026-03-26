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
    db_path: str = _env("DB_PATH", "corridor_clearing.db")

    # Visualization
    viz_mode: Literal["abstract", "leaflet"] = _env("VIZ_MODE", "abstract")  # type: ignore[assignment]

    # Simulation
    sim_speed: float = float(_env("SIM_SPEED", "1.0"))
    sim_duration_s: float = float(_env("SIM_DURATION_S", "3600.0"))

    # MCTS
    mcts_iterations: int = int(_env("MCTS_ITERATIONS", "1000"))
    mcts_horizon_s: float = float(_env("MCTS_HORIZON_S", "60.0"))
    mcts_replan_interval_s: float = float(_env("MCTS_REPLAN_INTERVAL_S", "10.0"))
    mcts_replan_interval_ev_s: float = float(_env("MCTS_REPLAN_INTERVAL_EV_S", "5.0"))
    mcts_horizon_step_s: float = float(_env("MCTS_HORIZON_STEP_S", "15.0"))
    mcts_exploration_constant: float = float(_env("MCTS_EXPLORATION_CONSTANT", "1.41"))

    # Reward weights
    w_ev: float = float(_env("W_EV", "10.0"))
    w_queue: float = float(_env("W_QUEUE", "1.0"))
    w_throughput: float = float(_env("W_THROUGHPUT", "0.5"))
    w_stability: float = float(_env("W_STABILITY", "0.3"))
    w_max_queue: float = float(_env("W_MAX_QUEUE", "2.0"))
    max_queue_threshold: float = float(_env("MAX_QUEUE_THRESHOLD", "50.0"))

    # Paths
    data_dir: Path = Path(__file__).parent.parent / "data"

    # WS throttle
    ws_max_updates_per_sec: int = int(_env("WS_MAX_UPDATES_PER_SEC", "10"))


settings = Settings()
