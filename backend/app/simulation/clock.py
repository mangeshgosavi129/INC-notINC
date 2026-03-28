import time


class SimulationClock:
    """Manages simulation time with speed control and pause/resume."""

    def __init__(self, speed: float = 1.0):
        self.sim_time: float = 0.0
        self.speed: float = speed
        self.paused: bool = False
        self._wall_start: float = time.monotonic()
        self._pause_start: float | None = None
        self._total_paused: float = 0.0

    def set_speed(self, speed: float) -> None:
        if speed <= 0:
            raise ValueError("Speed must be positive")
        self.speed = speed

    def pause(self) -> None:
        if not self.paused:
            self.paused = True
            self._pause_start = time.monotonic()

    def resume(self) -> None:
        if self.paused and self._pause_start is not None:
            self._total_paused += time.monotonic() - self._pause_start
            self._pause_start = None
            self.paused = False

    def advance_to(self, sim_time: float) -> None:
        self.sim_time = sim_time

    def wall_clock_elapsed(self) -> float:
        elapsed = time.monotonic() - self._wall_start
        if self.paused and self._pause_start is not None:
            elapsed -= (time.monotonic() - self._pause_start)
        return elapsed - self._total_paused

    def wall_delay_for_sim_delta(self, sim_delta: float) -> float:
        """How long to sleep (wall-clock) for a sim_delta at current speed."""
        if self.speed <= 0 or self.paused:
            return 0.0
        return sim_delta / self.speed

    def reset(self) -> None:
        self.sim_time = 0.0
        self.speed = 1.0
        self.paused = False
        self._wall_start = time.monotonic()
        self._pause_start = None
        self._total_paused = 0.0
