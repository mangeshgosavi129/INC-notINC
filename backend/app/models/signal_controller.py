from enum import Enum

from pydantic import BaseModel


class SignalPhaseState(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    ALL_RED = "ALL_RED"


class SignalControllerState(BaseModel):
    intersection_id: str
    mode: str = "FIXED_TIME"  # "FIXED_TIME", "MCTS", "PREEMPTION"
    current_phase: int = 1
    current_state: SignalPhaseState = SignalPhaseState.GREEN
    phase_start_time: float = 0.0
    min_green_elapsed: bool = False
    pending_next_phase: int | None = None

    def is_interruptible(self) -> bool:
        return self.current_state == SignalPhaseState.GREEN and self.min_green_elapsed

    def time_in_phase(self, now: float) -> float:
        return now - self.phase_start_time


class TimingPlan(BaseModel):
    plan_id: str
    intersection_id: str
    phase_splits: dict[int, float]  # phase_id -> green duration in seconds
    offset_s: float = 0.0           # coordination offset
