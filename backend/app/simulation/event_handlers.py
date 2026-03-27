"""Event handlers — one per EventType.

Each handler:
1. Mutates simulation state
2. Returns list of new events to schedule
3. Optionally marks event for WebSocket broadcast
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.app.models.events import EventType, SimEvent
from backend.app.simulation.ev_movement import (
    ev_arrive_at_intersection,
    ev_depart_origin,
    ev_enter_intersection,
    ev_signal_turned_green,
)
from backend.app.utils.helpers import gen_id

if TYPE_CHECKING:
    from backend.app.simulation.engine import SimulationState


def handle_signal_phase_start(state: SimulationState,
                              event: SimEvent) -> list[SimEvent]:
    """New green phase activated."""
    iid = event.payload["intersection_id"]
    phase_id = event.payload["phase_id"]

    # Update queue model — set green/red for movements
    fsm = state.signal_fsms[iid]
    green_movements = fsm.green_movements()
    if iid in state.intersection_queues:
        state.intersection_queues[iid].update_green_phases(
            green_movements, event.scheduled_time
        )

    # Check if any EV is waiting at this intersection for this phase
    new_events: list[SimEvent] = []
    if state.ev is not None and state.ev.waiting_at_intersection == iid:
        # Check if EV's approach movement is now green
        corridor = state.ev_corridor or state.corridor
        if state.ev.current_link_index < len(corridor.links):
            link = corridor.links[state.ev.current_link_index]
            if link.ev_approach_movement in green_movements:
                wait_duration = event.scheduled_time - state.ev_wait_start_time
                state.ev.total_delay_at_signals += wait_duration
                new_events.extend(
                    ev_signal_turned_green(state.ev, iid, event.scheduled_time)
                )

    # Mark for broadcast
    event.payload["broadcast"] = True
    event.payload["green_movements"] = list(green_movements)
    return new_events


def handle_signal_min_green_expire(state: SimulationState,
                                   event: SimEvent) -> list[SimEvent]:
    """Min green timer expired — phase can now be terminated."""
    iid = event.payload["intersection_id"]
    fsm = state.signal_fsms[iid]
    return fsm.handle_min_green_expire(event.scheduled_time)


def handle_signal_max_green_expire(state: SimulationState,
                                   event: SimEvent) -> list[SimEvent]:
    """Max green expired — force phase termination."""
    iid = event.payload["intersection_id"]
    fsm = state.signal_fsms[iid]
    # Only handle if still in GREEN for this phase
    if (fsm.state.current_phase == event.payload.get("phase_id") and
            fsm.state.current_state.value == "GREEN"):
        return fsm.handle_max_green_expire(event.scheduled_time)
    return []


def handle_signal_amber_start(state: SimulationState,
                              event: SimEvent) -> list[SimEvent]:
    """Amber period started — update queue model (all red for this intersection)."""
    iid = event.payload["intersection_id"]
    if iid in state.intersection_queues:
        state.intersection_queues[iid].update_green_phases(
            set(), event.scheduled_time
        )
    event.payload["broadcast"] = True
    return []


def handle_signal_amber_end(state: SimulationState,
                            event: SimEvent) -> list[SimEvent]:
    """Amber over — transition to all-red."""
    iid = event.payload["intersection_id"]
    fsm = state.signal_fsms[iid]
    return fsm.handle_amber_end(event.scheduled_time)


def handle_signal_all_red_start(state: SimulationState,
                                event: SimEvent) -> list[SimEvent]:
    """All-red clearance started."""
    return []


def handle_signal_all_red_end(state: SimulationState,
                              event: SimEvent) -> list[SimEvent]:
    """All-red over — activate next phase."""
    iid = event.payload["intersection_id"]
    fsm = state.signal_fsms[iid]
    return fsm.handle_all_red_end(event.scheduled_time)


def handle_ev_depart_origin(state: SimulationState,
                            event: SimEvent) -> list[SimEvent]:
    """EV dispatched — begin traveling to first intersection."""
    if state.ev is None:
        return []
    corridor = state.ev_corridor or state.corridor
    return ev_depart_origin(state.ev, corridor, event.scheduled_time)


def handle_ev_arrive_intersection(state: SimulationState,
                                  event: SimEvent) -> list[SimEvent]:
    """EV arrived at intersection stop-bar."""
    if state.ev is None:
        return []

    iid = event.payload["intersection_id"]
    link_index = event.payload["link_index"]
    movement_id = event.payload["movement_id"]

    # Check signal state
    fsm = state.signal_fsms.get(iid)
    is_green = False
    if fsm is not None:
        is_green = fsm.is_green_for_movement(movement_id)

    if not is_green:
        state.ev_wait_start_time = event.scheduled_time

    event.payload["broadcast"] = True
    event.payload["is_green"] = is_green

    return ev_arrive_at_intersection(
        state.ev, iid, link_index, is_green, event.scheduled_time
    )


def handle_ev_enter_intersection(state: SimulationState,
                                 event: SimEvent) -> list[SimEvent]:
    """EV proceeds through intersection — schedule next link travel."""
    if state.ev is None:
        return []

    iid = event.payload["intersection_id"]
    event.payload["broadcast"] = True

    corridor = state.ev_corridor or state.corridor
    return ev_enter_intersection(
        state.ev, corridor, iid, event.scheduled_time
    )


def handle_ev_reach_destination(state: SimulationState,
                                event: SimEvent) -> list[SimEvent]:
    """EV has arrived at destination."""
    if state.ev is not None:
        state.ev.arrival_time = event.scheduled_time
    event.payload["broadcast"] = True
    return []


def handle_mcts_replan_trigger(state: SimulationState,
                               event: SimEvent) -> list[SimEvent]:
    """Trigger MCTS to compute new signal plan."""
    # This will be implemented in Phase 3 when MCTS controller is built
    # For now, schedule next replan
    new_events: list[SimEvent] = []

    if state.controller is not None:
        actions = state.controller.decide(state, event.scheduled_time)
        new_events.extend(actions)

    # Schedule next replan
    interval = state.replan_interval_s
    if state.ev is not None and state.ev.status.value not in ("idle", "arrived"):
        interval = state.replan_interval_ev_s

    new_events.append(SimEvent(
        event_id=gen_id("evt"),
        event_type=EventType.MCTS_REPLAN_TRIGGER,
        scheduled_time=event.scheduled_time + interval,
        payload={},
        source="simulation",
    ))

    return new_events


def handle_congestion_snapshot(state: SimulationState,
                               event: SimEvent) -> list[SimEvent]:
    """Periodic metrics capture."""
    state.capture_metrics(event.scheduled_time)
    event.payload["broadcast"] = True

    # Schedule next snapshot
    return [
        SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.CONGESTION_SNAPSHOT,
            scheduled_time=event.scheduled_time + state.snapshot_interval_s,
            payload={},
            source="simulation",
        ),
    ]


def handle_traffic_profile_shift(state: SimulationState,
                                 event: SimEvent) -> list[SimEvent]:
    """Update arrival rates based on time-of-day profile."""
    rate_vph = event.payload["rate_vph"]
    rate_vps = rate_vph / 3600.0

    # Update all approach queues
    for iq in state.intersection_queues.values():
        for q in iq.queues.values():
            q.set_arrival_rate(rate_vps / max(1, len(iq.queues)),
                               event.scheduled_time)

    return []


def handle_blockage_start(state: SimulationState,
                          event: SimEvent) -> list[SimEvent]:
    """Road blockage — reduce link capacity."""
    from_id = event.payload["from_intersection"]
    to_id = event.payload["to_intersection"]
    reduction = event.payload.get("capacity_reduction_pct", 50.0)

    link = state.corridor.get_link(from_id, to_id)
    if link is not None:
        state.blockage_factors[(from_id, to_id)] = 1.0 - (reduction / 100.0)

    event.payload["broadcast"] = True
    return []


def handle_blockage_end(state: SimulationState,
                        event: SimEvent) -> list[SimEvent]:
    """Road blockage cleared."""
    from_id = event.payload["from_intersection"]
    to_id = event.payload["to_intersection"]
    state.blockage_factors.pop((from_id, to_id), None)
    event.payload["broadcast"] = True
    return []


def handle_congestion_spike(state: SimulationState,
                            event: SimEvent) -> list[SimEvent]:
    """Sudden traffic surge on a specific approach."""
    iid = event.payload["intersection_id"]
    multiplier = event.payload.get("rate_multiplier", 2.0)
    duration_s = event.payload.get("duration_s", 300)

    if iid in state.intersection_queues:
        for q in state.intersection_queues[iid].queues.values():
            q.set_arrival_rate(q.arrival_rate * multiplier, event.scheduled_time)

    # Schedule end of spike (restore rates via next profile shift)
    event.payload["broadcast"] = True
    return []


# Dispatch table
EVENT_HANDLERS: dict[EventType, callable] = {
    EventType.SIGNAL_PHASE_START: handle_signal_phase_start,
    EventType.SIGNAL_MIN_GREEN_EXPIRE: handle_signal_min_green_expire,
    EventType.SIGNAL_MAX_GREEN_EXPIRE: handle_signal_max_green_expire,
    EventType.SIGNAL_AMBER_START: handle_signal_amber_start,
    EventType.SIGNAL_AMBER_END: handle_signal_amber_end,
    EventType.SIGNAL_ALL_RED_START: handle_signal_all_red_start,
    EventType.SIGNAL_ALL_RED_END: handle_signal_all_red_end,
    EventType.EV_DEPART_ORIGIN: handle_ev_depart_origin,
    EventType.EV_ARRIVE_INTERSECTION: handle_ev_arrive_intersection,
    EventType.EV_ENTER_INTERSECTION: handle_ev_enter_intersection,
    EventType.EV_REACH_DESTINATION: handle_ev_reach_destination,
    EventType.MCTS_REPLAN_TRIGGER: handle_mcts_replan_trigger,
    EventType.CONGESTION_SNAPSHOT: handle_congestion_snapshot,
    EventType.TRAFFIC_PROFILE_SHIFT: handle_traffic_profile_shift,
    EventType.BLOCKAGE_START: handle_blockage_start,
    EventType.BLOCKAGE_END: handle_blockage_end,
    EventType.CONGESTION_SPIKE: handle_congestion_spike,
}
