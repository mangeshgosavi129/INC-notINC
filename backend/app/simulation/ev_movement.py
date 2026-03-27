"""Emergency vehicle movement along corridor.

EV traverses corridor as ordered sequence of intersections.
- Link travel time: link_length / min(ev_speed, link_speed * congestion_factor)
- congestion_factor: BPR formula: 1.0 / (1 + 0.15 * (volume/capacity)^4)

CRITICAL: EV MUST wait at red signals. No teleporting, no skipping.
On arriving at intersection:
1. Check signal state for EV's approach movement.
2. If GREEN: schedule EV_ENTER_INTERSECTION after 1-2s startup delay.
3. If NOT GREEN: EV WAITS. When signal turns GREEN for EV's phase,
   the phase_start handler checks waiting_evs and schedules entry.
"""

from __future__ import annotations

from backend.app.models.corridor import Corridor, CorridorLink
from backend.app.models.ev import EVStatus, EmergencyVehicle
from backend.app.models.events import EventType, SimEvent
from backend.app.utils.helpers import gen_id

EV_STARTUP_DELAY_S = 1.5  # time to start moving after green


def bpr_congestion_factor(volume_vph: float, capacity_vph: float) -> float:
    """BPR (Bureau of Public Roads) speed reduction factor."""
    if capacity_vph <= 0:
        return 0.1
    vc = volume_vph / capacity_vph
    return 1.0 / (1.0 + 0.15 * (vc ** 4))


def compute_link_travel_time(link: CorridorLink, ev_speed_kmph: float,
                             current_volume_vph: float = 0.0) -> float:
    """Compute travel time for EV on a link in seconds."""
    congestion = bpr_congestion_factor(current_volume_vph, link.capacity_vph)
    effective_speed_kmph = min(ev_speed_kmph, link.free_flow_speed_kmph * congestion)
    effective_speed_kmph = max(effective_speed_kmph, 5.0)  # floor at 5 km/h
    speed_mps = effective_speed_kmph * 1000.0 / 3600.0
    return link.length_meters / speed_mps


def _find_shortest_path(corridor: Corridor, start: str, end: str) -> list[str] | None:
    """BFS shortest path between two intersections using corridor links."""
    from collections import deque

    adj: dict[str, list[str]] = {}
    for link in corridor.links:
        adj.setdefault(link.from_intersection, []).append(link.to_intersection)
        adj.setdefault(link.to_intersection, []).append(link.from_intersection)

    if start not in adj:
        return None

    visited = {start}
    queue: deque[list[str]] = deque([[start]])
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node == end:
            return path
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])
    return None


def _build_sub_corridor(corridor: Corridor, route: list[str]) -> Corridor:
    """Build a sub-corridor from a route (ordered list of intersection IDs)."""
    sub_links: list[CorridorLink] = []
    for i in range(len(route) - 1):
        link = corridor.get_link(route[i], route[i + 1])
        if link is None:
            # Try reverse direction
            link = corridor.get_link(route[i + 1], route[i])
        if link is not None:
            # Ensure direction matches route
            sub_links.append(CorridorLink(
                from_intersection=route[i],
                to_intersection=route[i + 1],
                length_meters=link.length_meters,
                free_flow_speed_kmph=link.free_flow_speed_kmph,
                num_lanes=link.num_lanes,
                capacity_vph=link.capacity_vph,
                ev_approach_movement=link.ev_approach_movement,
            ))
    return Corridor(
        corridor_id=corridor.corridor_id,
        name=corridor.name,
        intersection_ids=route,
        links=sub_links,
    )


def dispatch_ev(ev: EmergencyVehicle, corridor: Corridor,
                sim_time: float,
                start_intersection: str | None = None,
                end_intersection: str | None = None) -> tuple[list[SimEvent], Corridor]:
    """Dispatch EV. Returns (initial events, effective corridor for this route)."""
    effective_corridor = corridor

    if start_intersection and end_intersection:
        route = _find_shortest_path(corridor, start_intersection, end_intersection)
        if route and len(route) >= 2:
            effective_corridor = _build_sub_corridor(corridor, route)

    ev.status = EVStatus.DISPATCHED
    ev.dispatch_time = sim_time
    ev.route = list(effective_corridor.intersection_ids)
    ev.current_link_index = 0
    ev.position_on_link = 0.0
    ev.speed_kmph = ev.max_speed_kmph

    return [
        SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.EV_DEPART_ORIGIN,
            scheduled_time=sim_time,
            payload={
                "ev_id": ev.ev_id,
                "corridor_id": effective_corridor.corridor_id,
            },
            source="simulation",
        ),
    ], effective_corridor


def ev_depart_origin(ev: EmergencyVehicle, corridor: Corridor,
                     sim_time: float,
                     volume_vph: float = 0.0) -> list[SimEvent]:
    """EV departs origin — schedule arrival at first intersection."""
    ev.status = EVStatus.EN_ROUTE
    if not corridor.links:
        # Single-intersection corridor — already arrived
        ev.status = EVStatus.ARRIVED
        ev.arrival_time = sim_time
        return [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.EV_REACH_DESTINATION,
                scheduled_time=sim_time,
                payload={"ev_id": ev.ev_id},
                source="simulation",
            ),
        ]

    link = corridor.links[0]
    travel_time = compute_link_travel_time(link, ev.max_speed_kmph, volume_vph)

    return [
        SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.EV_ARRIVE_INTERSECTION,
            scheduled_time=sim_time + travel_time,
            payload={
                "ev_id": ev.ev_id,
                "intersection_id": link.to_intersection,
                "link_index": 0,
                "movement_id": link.ev_approach_movement,
            },
            source="simulation",
        ),
    ]


def ev_arrive_at_intersection(ev: EmergencyVehicle, intersection_id: str,
                              link_index: int, is_green: bool,
                              sim_time: float) -> list[SimEvent]:
    """EV arrives at intersection stop-bar.

    If green: schedule entry after startup delay.
    If not green: EV WAITS. Returns no events — the signal phase_start
    handler will schedule entry when green arrives.
    """
    ev.current_link_index = link_index
    ev.position_on_link = 1.0

    if is_green:
        ev.status = EVStatus.TRAVERSING_INTERSECTION
        ev.intersections_cleared += 1
        return [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.EV_ENTER_INTERSECTION,
                scheduled_time=sim_time + EV_STARTUP_DELAY_S,
                payload={
                    "ev_id": ev.ev_id,
                    "intersection_id": intersection_id,
                    "link_index": link_index,
                },
                source="simulation",
            ),
        ]
    else:
        # EV MUST WAIT
        ev.status = EVStatus.WAITING_AT_SIGNAL
        ev.waiting_at_intersection = intersection_id
        ev.intersections_waited += 1
        return []


def ev_signal_turned_green(ev: EmergencyVehicle, intersection_id: str,
                           sim_time: float) -> list[SimEvent]:
    """Called when a signal turns green for a waiting EV."""
    if (ev.status != EVStatus.WAITING_AT_SIGNAL or
            ev.waiting_at_intersection != intersection_id):
        return []

    wait_start = sim_time  # approximate — real tracking in event handler
    ev.status = EVStatus.TRAVERSING_INTERSECTION
    ev.waiting_at_intersection = None

    return [
        SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.EV_ENTER_INTERSECTION,
            scheduled_time=sim_time + EV_STARTUP_DELAY_S,
            payload={
                "ev_id": ev.ev_id,
                "intersection_id": intersection_id,
                "link_index": ev.current_link_index,
            },
            source="simulation",
        ),
    ]


def ev_enter_intersection(ev: EmergencyVehicle, corridor: Corridor,
                          intersection_id: str, sim_time: float,
                          volume_vph: float = 0.0) -> list[SimEvent]:
    """EV has entered and is traversing the intersection. Schedule next link or arrival."""
    next_link_index = ev.current_link_index + 1

    if next_link_index >= len(corridor.links):
        # Reached destination
        ev.status = EVStatus.ARRIVED
        ev.arrival_time = sim_time
        return [
            SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.EV_REACH_DESTINATION,
                scheduled_time=sim_time,
                payload={"ev_id": ev.ev_id, "corridor_id": corridor.corridor_id},
                source="simulation",
            ),
        ]

    # Travel to next intersection
    link = corridor.links[next_link_index]
    travel_time = compute_link_travel_time(link, ev.max_speed_kmph, volume_vph)
    ev.current_link_index = next_link_index
    ev.position_on_link = 0.0
    ev.status = EVStatus.EN_ROUTE

    return [
        SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.EV_ARRIVE_INTERSECTION,
            scheduled_time=sim_time + travel_time,
            payload={
                "ev_id": ev.ev_id,
                "intersection_id": link.to_intersection,
                "link_index": next_link_index,
                "movement_id": link.ev_approach_movement,
            },
            source="simulation",
        ),
    ]


def compute_ev_progress(ev: EmergencyVehicle, corridor: Corridor) -> float:
    """Compute EV progress as percentage (0-100) along corridor."""
    if ev.status == EVStatus.ARRIVED:
        return 100.0
    if ev.status == EVStatus.IDLE:
        return 0.0

    total_links = len(corridor.links)
    if total_links == 0:
        return 100.0

    completed = ev.current_link_index
    on_link = ev.position_on_link
    return ((completed + on_link) / total_links) * 100.0


def compute_ev_eta(ev: EmergencyVehicle, corridor: Corridor,
                   current_time: float) -> float | None:
    """Estimate time remaining for EV to reach destination."""
    if ev.status in (EVStatus.ARRIVED, EVStatus.IDLE):
        return None

    remaining_time = 0.0
    for i in range(ev.current_link_index, len(corridor.links)):
        link = corridor.links[i]
        tt = compute_link_travel_time(link, ev.max_speed_kmph)
        if i == ev.current_link_index:
            tt *= (1.0 - ev.position_on_link)
        remaining_time += tt
        # Add estimated signal delay (5s average per intersection)
        remaining_time += 5.0

    return remaining_time
