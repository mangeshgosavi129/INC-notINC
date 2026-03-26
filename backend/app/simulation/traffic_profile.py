"""Time-of-day traffic profile with piecewise-linear interpolation.

Rates are specified as (time_of_day_string, rate_vph) pairs.
Between breakpoints, rates are linearly interpolated.
"""

from __future__ import annotations

from backend.app.models.events import EventType, SimEvent
from backend.app.utils.helpers import gen_id, time_str_to_seconds


class TrafficProfile:
    """Piecewise-linear arrival rate profile."""

    def __init__(self, breakpoints: list[dict]):
        """breakpoints: list of {"time": "HH:MM", "rate_vph": float}"""
        self.breakpoints: list[tuple[float, float]] = []
        for bp in breakpoints:
            t = time_str_to_seconds(bp["time"])
            r = bp["rate_vph"]
            self.breakpoints.append((t, r))
        self.breakpoints.sort(key=lambda x: x[0])

    def get_rate_vph(self, time_of_day_s: float) -> float:
        """Get interpolated arrival rate at given time of day (seconds from midnight)."""
        if not self.breakpoints:
            return 0.0

        # Wrap to 24h
        time_of_day_s = time_of_day_s % 86400.0

        # Find surrounding breakpoints
        for i in range(len(self.breakpoints)):
            if self.breakpoints[i][0] > time_of_day_s:
                if i == 0:
                    # Before first breakpoint — use last→first interpolation
                    t0, r0 = self.breakpoints[-1]
                    t1, r1 = self.breakpoints[0]
                    t0 -= 86400.0  # wrap previous day
                else:
                    t0, r0 = self.breakpoints[i - 1]
                    t1, r1 = self.breakpoints[i]

                dt = t1 - t0
                if dt <= 0:
                    return r0
                frac = (time_of_day_s - t0) / dt
                return r0 + frac * (r1 - r0)

        # After last breakpoint — interpolate last→first (next day)
        t0, r0 = self.breakpoints[-1]
        t1, r1 = self.breakpoints[0]
        t1 += 86400.0
        dt = t1 - t0
        if dt <= 0:
            return r0
        frac = (time_of_day_s - t0) / dt
        return r0 + frac * (r1 - r0)

    def get_rate_vps(self, time_of_day_s: float) -> float:
        """Get rate in vehicles per second."""
        return self.get_rate_vph(time_of_day_s) / 3600.0

    def generate_shift_events(self, sim_start_time_of_day_s: float,
                              sim_duration_s: float) -> list[SimEvent]:
        """Generate TRAFFIC_PROFILE_SHIFT events at each breakpoint during sim."""
        events = []
        for t_bp, rate in self.breakpoints:
            # Calculate sim_time for this breakpoint
            offset = t_bp - sim_start_time_of_day_s
            if offset < 0:
                offset += 86400.0  # next day

            if offset < sim_duration_s:
                events.append(SimEvent(
                    event_id=gen_id("evt"),
                    event_type=EventType.TRAFFIC_PROFILE_SHIFT,
                    scheduled_time=offset,
                    payload={
                        "time_of_day_s": t_bp,
                        "rate_vph": rate,
                    },
                    source="simulation",
                ))
        return events
