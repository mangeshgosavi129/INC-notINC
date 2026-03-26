"""Config service — load, save, validate configurations."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.config import settings
from backend.app.models.corridor import Corridor
from backend.app.models.intersection import Intersection
from backend.app.simulation.traffic_profile import TrafficProfile


class ConfigService:
    def __init__(self):
        self.data_dir = settings.data_dir
        self._intersections: list[Intersection] | None = None
        self._corridor: Corridor | None = None
        self._profile: TrafficProfile | None = None
        self._timing_plans: list[dict] | None = None
        self._mcts_config: dict | None = None

    def load_defaults(self) -> None:
        self._intersections = self._load_intersections()
        self._corridor = self._load_corridor()
        self._profile = self._load_profile()
        self._timing_plans = self._load_timing_plans()
        self._mcts_config = self._load_mcts_config()

    @property
    def intersections(self) -> list[Intersection]:
        if self._intersections is None:
            self._intersections = self._load_intersections()
        return self._intersections

    @property
    def corridor(self) -> Corridor:
        if self._corridor is None:
            self._corridor = self._load_corridor()
        return self._corridor

    @property
    def profile(self) -> TrafficProfile:
        if self._profile is None:
            self._profile = self._load_profile()
        return self._profile

    @property
    def timing_plans(self) -> list[dict]:
        if self._timing_plans is None:
            self._timing_plans = self._load_timing_plans()
        return self._timing_plans

    @property
    def mcts_config(self) -> dict:
        if self._mcts_config is None:
            self._mcts_config = self._load_mcts_config()
        return self._mcts_config

    def _load_intersections(self) -> list[Intersection]:
        with open(self.data_dir / "pune_default_intersections.json") as f:
            data = json.load(f)
        return [Intersection(**ix) for ix in data["intersections"]]

    def _load_corridor(self) -> Corridor:
        with open(self.data_dir / "pune_default_corridor.json") as f:
            data = json.load(f)
        return Corridor(**data["corridor"])

    def _load_profile(self, profile_name: str = "default") -> TrafficProfile:
        with open(self.data_dir / "pune_traffic_profiles.json") as f:
            data = json.load(f)
        return TrafficProfile(data["profiles"][profile_name])

    def _load_timing_plans(self) -> list[dict]:
        with open(self.data_dir / "pune_default_timing_plans.json") as f:
            data = json.load(f)
        return data["timing_plans"]

    def _load_mcts_config(self) -> dict:
        with open(self.data_dir / "mcts_default_config.json") as f:
            return json.load(f)

    def update_intersections(self, data: dict) -> list[Intersection]:
        self._intersections = [Intersection(**ix) for ix in data["intersections"]]
        return self._intersections

    def update_corridor(self, data: dict) -> Corridor:
        self._corridor = Corridor(**data["corridor"])
        return self._corridor

    def update_mcts_config(self, data: dict) -> dict:
        self._mcts_config = data
        return self._mcts_config

    def get_all_config(self) -> dict:
        return {
            "intersections": [ix.model_dump() for ix in self.intersections],
            "corridor": self.corridor.model_dump(),
            "timing_plans": self.timing_plans,
            "mcts": self.mcts_config,
        }

    def reset(self) -> None:
        self._intersections = None
        self._corridor = None
        self._profile = None
        self._timing_plans = None
        self._mcts_config = None


config_service = ConfigService()
