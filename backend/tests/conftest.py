import json
from pathlib import Path

import pytest

from backend.app.models.corridor import Corridor
from backend.app.models.intersection import Intersection
from backend.app.models.signal_controller import SignalControllerState
from backend.app.simulation.signal_fsm import SignalFSM
from backend.app.simulation.queue_model import IntersectionQueues
from backend.app.simulation.traffic_profile import TrafficProfile


DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def sample_intersection() -> Intersection:
    return Intersection(
        intersection_id="INT_01",
        name="Test Intersection",
        approaches=["N", "S", "E", "W"],
        movements=[
            {"movement_id": "NBT", "from_approach": "N", "to_approach": "S",
             "movement_type": "through", "lanes": 2, "saturation_flow_vph": 1800},
            {"movement_id": "SBT", "from_approach": "S", "to_approach": "N",
             "movement_type": "through", "lanes": 2, "saturation_flow_vph": 1800},
            {"movement_id": "EBT", "from_approach": "E", "to_approach": "W",
             "movement_type": "through", "lanes": 2, "saturation_flow_vph": 1800},
            {"movement_id": "WBT", "from_approach": "W", "to_approach": "E",
             "movement_type": "through", "lanes": 2, "saturation_flow_vph": 1800},
        ],
        phases=[
            {"phase_id": 1, "served_movements": ["NBT", "SBT"],
             "min_green": 10, "max_green": 45, "amber": 3.0, "all_red": 2.0},
            {"phase_id": 2, "served_movements": ["EBT", "WBT"],
             "min_green": 10, "max_green": 45, "amber": 3.0, "all_red": 2.0},
        ],
        rings=[{"ring_id": 1, "phase_sequence": [1, 2]}],
    )


@pytest.fixture
def sample_corridor() -> Corridor:
    with open(DATA_DIR / "pune_default_corridor.json") as f:
        data = json.load(f)
    return Corridor(**data["corridor"])


@pytest.fixture
def sample_intersections() -> list[Intersection]:
    with open(DATA_DIR / "pune_default_intersections.json") as f:
        data = json.load(f)
    return [Intersection(**ix) for ix in data["intersections"]]


@pytest.fixture
def sample_profile() -> TrafficProfile:
    with open(DATA_DIR / "pune_traffic_profiles.json") as f:
        data = json.load(f)
    return TrafficProfile(data["profiles"]["default"])


@pytest.fixture
def signal_fsm(sample_intersection) -> SignalFSM:
    ctrl = SignalControllerState(intersection_id="INT_01")
    return SignalFSM(sample_intersection, ctrl)
