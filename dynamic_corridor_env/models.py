"""Models for the dynamic corridor clearing OpenEnv environment."""

from __future__ import annotations

from typing import Any

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class DynamicCorridorAction(Action):
    """Environment action containing optional per-intersection phase choices."""

    phase_by_intersection: dict[str, int] = Field(
        default_factory=dict,
        description="Mapping from traffic-light/intersection ID to target green phase index.",
    )
    next_edge_id: str | None = Field(
        default=None,
        description="Optional route-choice action selecting the ambulance's next directed road edge.",
    )
    reason: str = Field(
        default="",
        description="Optional explanation for logging/debugging.",
    )


class IntersectionObservation(Observation):
    """Local traffic state for one intersection."""

    intersection_id: str = Field(..., description="Intersection/traffic-light ID.")
    current_phase: int = Field(0, description="Current SUMO phase index.")
    valid_phases: list[int] = Field(default_factory=list, description="Controllable green phases.")
    queue_by_phase: dict[int, float] = Field(
        default_factory=dict,
        description="Estimated halted vehicles served by each controllable green phase.",
    )
    elapsed_phase_time: int = Field(
        0,
        description="Decision steps elapsed since the current phase was selected.",
    )
    queue_length: float = Field(0.0, description="Total halted vehicles on incoming lanes.")
    vehicle_count: int = Field(0, description="Total vehicles on incoming lanes.")
    mean_speed: float = Field(0.0, description="Mean speed on incoming lanes in m/s.")
    is_on_ev_route: bool = Field(False, description="Whether this intersection is on the ambulance route.")
    ev_approach_edge: str = Field("", description="Edge used by the ambulance to enter this intersection.")
    ev_target_phase: int | None = Field(None, description="Green phase that serves the ambulance approach.")
    ev_eta_steps: float = Field(
        -1.0,
        description="Estimated decision steps until the ambulance reaches this intersection, or -1 if unavailable.",
    )
    ev_distance_m: float = Field(
        -1.0,
        description="Estimated ambulance distance to this intersection in metres, or -1 if unavailable.",
    )


class EVObservation(Observation):
    """Ambulance state exposed to the agent."""

    ev_id: str = Field("ambulance_0", description="Emergency vehicle ID.")
    route_edges: list[str] = Field(default_factory=list, description="SUMO edge route for the ambulance.")
    current_edge: str = Field("", description="Current SUMO edge occupied by the ambulance.")
    route_index: int = Field(0, description="Current edge index within the route.")
    edge_progress: float = Field(0.0, description="Progress on the current edge from 0 to 1.")
    next_intersection: str = Field("", description="Next signalized intersection on the route.")
    progress: float = Field(0.0, description="Route progress from 0 to 1.")
    waiting_time: float = Field(0.0, description="Accumulated waiting time in seconds.")
    travel_time: float = Field(0.0, description="Elapsed ambulance travel time in seconds.")
    arrived: bool = Field(False, description="Whether the ambulance has reached its destination.")


class RouteCandidateObservation(Observation):
    """One selectable outgoing road for the EV route-choice agent."""

    edge_id: str = Field(..., description="Directed SUMO edge ID.")
    from_node: str = Field(..., description="Source node of this directed edge.")
    to_node: str = Field(..., description="Destination node of this directed edge.")
    road_weight: float = Field(0.0, description="Seeded per-episode traffic cost weight in [0, 1].")
    estimated_queue: float = Field(0.0, description="Current halted vehicles estimated on this edge.")
    length_m: float = Field(0.0, description="Road length in metres.")
    speed_m_s: float = Field(0.0, description="Road speed limit in metres per second.")
    destination_distance_delta: float = Field(
        0.0,
        description="Euclidean distance-to-destination improvement after taking this edge.",
    )
    moves_closer: bool = Field(False, description="Whether this edge moves closer to the destination.")
    is_backtrack: bool = Field(False, description="Whether this edge reverses the previous directed edge.")
    destination_reachable: bool = Field(False, description="Whether destination remains reachable after this edge.")


class RouteChoiceObservation(Observation):
    """Route-choice state exposed to the EV path-selection agent."""

    source_id: str = Field("NW_OUT", description="Episode source node.")
    destination_id: str = Field("SE_OUT", description="Episode destination node.")
    current_node: str = Field("NW_OUT", description="Node from which the next route choice is made.")
    current_edge_id: str = Field("", description="Current EV edge, if active in SUMO.")
    previous_edge_id: str = Field("", description="Previous/current directed edge used for backtrack detection.")
    active_route_edges: list[str] = Field(default_factory=list, description="Current planned EV route.")
    road_weights: dict[str, float] = Field(default_factory=dict, description="Per-episode edge weights.")
    candidates: list[RouteCandidateObservation] = Field(default_factory=list)


class DynamicCorridorObservation(Observation):
    """Observation returned by reset and step."""

    task_id: str = Field("grid_4x4_default", description="Scenario/task identifier.")
    sim_time: float = Field(0.0, description="Current simulation time in seconds.")
    step: int = Field(0, description="Decision step index.")
    intersections: list[IntersectionObservation] = Field(default_factory=list)
    ev: EVObservation = Field(default_factory=EVObservation)
    route_choice: RouteChoiceObservation = Field(default_factory=RouteChoiceObservation)
    global_metrics: dict[str, Any] = Field(default_factory=dict)
    reward: float = Field(0.0, description="Reward from the previous action.")
    done: bool = Field(False, description="Whether the episode has ended.")
    feedback: str = Field("", description="Human-readable summary of the last transition.")


class DynamicCorridorState(State):
    """Environment state exposed through /state."""

    episode_id: str = Field("", description="Unique episode ID.")
    task_id: str = Field("grid_4x4_default", description="Scenario/task identifier.")
    step_count: int = Field(0, description="Number of decisions taken.")
    sim_time: float = Field(0.0, description="Current simulation time.")
    cumulative_reward: float = Field(0.0, description="Total reward this episode.")
    ev_arrived: bool = Field(False, description="Whether the ambulance reached the destination.")
    ev_travel_time: float = Field(0.0, description="Ambulance travel time in seconds.")
    ev_waiting_time: float = Field(0.0, description="Ambulance waiting time in seconds.")
    total_queue: float = Field(0.0, description="Current total queue across controlled intersections.")
    max_queue: float = Field(0.0, description="Current maximum queue at one controlled intersection.")
    throughput: int = Field(0, description="Vehicles that arrived in the simulation.")
    phase_changes: int = Field(0, description="Phase changes requested by the agent.")
    agent_runtime: dict[str, Any] = Field(
        default_factory=dict,
        description="Read-only decentralized intersection-agent runtime metadata.",
    )
    done: bool = Field(False, description="Whether the episode is complete.")
