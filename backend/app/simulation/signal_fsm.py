"""Signal phase state machine.

Each intersection controller is a finite state machine:
  GREEN (min_green → max_green)
    → AMBER (fixed 3s, NON-INTERRUPTIBLE)
      → ALL_RED (fixed 2s, NON-INTERRUPTIBLE)
        → GREEN (next phase)

CRITICAL REALISM RULES:
1. Phase change cannot happen until min_green has elapsed.
2. Amber and all-red are NON-INTERRUPTIBLE — even emergency preemption
   cannot skip them.
3. EV must physically wait at intersection until signal is GREEN for its
   approach movement.
"""

from __future__ import annotations

from backend.app.models.events import EventType, SimEvent
from backend.app.models.intersection import Intersection, Phase
from backend.app.models.signal_controller import SignalControllerState, SignalPhaseState
from backend.app.utils.helpers import gen_id


class SignalFSM:
    """Manages signal transitions for a single intersection."""

    def __init__(self, intersection: Intersection,
                 controller_state: SignalControllerState):
        self.intersection = intersection
        self.state = controller_state
        self._pending_phase_request: int | None = None

    @property
    def current_phase_config(self) -> Phase:
        return self.intersection.get_phase(self.state.current_phase)

    def green_movements(self) -> set[str]:
        """Return movement IDs that currently have green."""
        if self.state.current_state != SignalPhaseState.GREEN:
            return set()
        phase = self.current_phase_config
        return set(phase.served_movements)

    def start_initial_phase(self, sim_time: float) -> list[SimEvent]:
        """Initialize the FSM — start the first phase green."""
        self.state.current_state = SignalPhaseState.GREEN
        self.state.phase_start_time = sim_time
        self.state.min_green_elapsed = False

        phase = self.current_phase_config
        events = [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_PHASE_START,
                scheduled_time=sim_time,
                payload={
                    "intersection_id": self.state.intersection_id,
                    "phase_id": self.state.current_phase,
                },
                source="simulation",
            ),
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_MIN_GREEN_EXPIRE,
                scheduled_time=sim_time + phase.min_green,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": self.state.current_phase},
                source="simulation",
            ),
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_MAX_GREEN_EXPIRE,
                scheduled_time=sim_time + phase.max_green,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": self.state.current_phase},
                source="simulation",
            ),
        ]
        return events

    def handle_min_green_expire(self, sim_time: float) -> list[SimEvent]:
        """Called when min_green timer expires."""
        if self.state.current_state != SignalPhaseState.GREEN:
            return []
        self.state.min_green_elapsed = True

        # If a phase change was requested while min_green was active, execute it now
        if self._pending_phase_request is not None:
            target = self._pending_phase_request
            self._pending_phase_request = None
            return self.request_phase_change(target, sim_time)

        return []

    def handle_max_green_expire(self, sim_time: float) -> list[SimEvent]:
        """Called when max_green timer expires — forces phase termination."""
        if self.state.current_state != SignalPhaseState.GREEN:
            return []
        # Force terminate: go to amber
        return self._begin_termination(sim_time)

    def request_phase_change(self, target_phase: int, sim_time: float,
                             source: str = "mcts") -> list[SimEvent]:
        """Request a phase change. Respects all realism constraints.

        Returns events needed for the transition. The caller should schedule them.
        """
        # If already in amber or all_red, cannot interrupt
        if self.state.current_state in (SignalPhaseState.AMBER,
                                         SignalPhaseState.ALL_RED):
            # Store the request — it will be applied after all_red ends
            self.state.pending_next_phase = target_phase
            return []

        # If we're in green but min_green hasn't elapsed yet
        if not self.state.min_green_elapsed:
            # Defer until min_green expires
            self._pending_phase_request = target_phase
            return []

        # If requesting the current phase, nothing to do
        if target_phase == self.state.current_phase:
            return []

        # Min green elapsed and we're in GREEN — begin termination
        self.state.pending_next_phase = target_phase
        return self._begin_termination(sim_time)

    def request_terminate(self, sim_time: float,
                          source: str = "mcts") -> list[SimEvent]:
        """Request termination of current phase (advance to next in ring)."""
        next_phase = self.intersection.get_next_phase(self.state.current_phase)
        return self.request_phase_change(next_phase, sim_time, source)

    def request_extend(self, extension_s: float, sim_time: float) -> list[SimEvent]:
        """Extend current green by extension_s seconds (capped by max_green)."""
        if self.state.current_state != SignalPhaseState.GREEN:
            return []
        # We just let the max_green event handle termination naturally.
        # The MCTS action "EXTEND" means: keep HOLD for now, don't terminate.
        # So this is effectively a no-op that signals intent.
        return []

    def _begin_termination(self, sim_time: float) -> list[SimEvent]:
        """Start the amber → all_red → next_green sequence."""
        phase = self.current_phase_config
        self.state.current_state = SignalPhaseState.AMBER
        self.state.phase_start_time = sim_time

        return [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_AMBER_START,
                scheduled_time=sim_time,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": self.state.current_phase},
                source="simulation",
            ),
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_AMBER_END,
                scheduled_time=sim_time + phase.amber,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": self.state.current_phase},
                source="simulation",
            ),
        ]

    def handle_amber_end(self, sim_time: float) -> list[SimEvent]:
        """Amber period is over — start all-red clearance."""
        phase = self.current_phase_config
        self.state.current_state = SignalPhaseState.ALL_RED
        self.state.phase_start_time = sim_time

        return [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_ALL_RED_START,
                scheduled_time=sim_time,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": self.state.current_phase},
                source="simulation",
            ),
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_ALL_RED_END,
                scheduled_time=sim_time + phase.all_red,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": self.state.current_phase},
                source="simulation",
            ),
        ]

    def handle_all_red_end(self, sim_time: float) -> list[SimEvent]:
        """All-red clearance complete — activate next phase."""
        if self.state.pending_next_phase is not None:
            next_phase = self.state.pending_next_phase
            self.state.pending_next_phase = None
        else:
            next_phase = self.intersection.get_next_phase(self.state.current_phase)

        self.state.current_phase = next_phase
        self.state.current_state = SignalPhaseState.GREEN
        self.state.phase_start_time = sim_time
        self.state.min_green_elapsed = False

        phase = self.intersection.get_phase(next_phase)
        return [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_PHASE_START,
                scheduled_time=sim_time,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": next_phase},
                source="simulation",
            ),
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_MIN_GREEN_EXPIRE,
                scheduled_time=sim_time + phase.min_green,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": next_phase},
                source="simulation",
            ),
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.SIGNAL_MAX_GREEN_EXPIRE,
                scheduled_time=sim_time + phase.max_green,
                payload={"intersection_id": self.state.intersection_id,
                         "phase_id": next_phase},
                source="simulation",
            ),
        ]

    def is_green_for_movement(self, movement_id: str) -> bool:
        """Check if a given movement currently has green."""
        return movement_id in self.green_movements()

    def time_until_phase_ends(self, now: float) -> float:
        """Estimate time until current phase ends (worst case for green)."""
        phase = self.current_phase_config
        elapsed = now - self.state.phase_start_time

        if self.state.current_state == SignalPhaseState.GREEN:
            remaining_green = max(0, phase.max_green - elapsed)
            return remaining_green + phase.amber + phase.all_red
        elif self.state.current_state == SignalPhaseState.AMBER:
            remaining_amber = max(0, phase.amber - elapsed)
            return remaining_amber + phase.all_red
        else:  # ALL_RED
            return max(0, phase.all_red - elapsed)

    def worst_case_transition_time(self, now: float) -> float:
        """Worst-case time to transition to a new green phase from now."""
        phase = self.current_phase_config
        elapsed = now - self.state.phase_start_time

        if self.state.current_state == SignalPhaseState.GREEN:
            remaining_min = max(0, phase.min_green - elapsed)
            return remaining_min + phase.amber + phase.all_red
        elif self.state.current_state == SignalPhaseState.AMBER:
            remaining = max(0, phase.amber - elapsed)
            return remaining + phase.all_red
        else:  # ALL_RED
            return max(0, phase.all_red - elapsed)
