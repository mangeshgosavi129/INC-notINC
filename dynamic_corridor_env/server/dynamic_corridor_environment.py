"""SUMO-backed dynamic corridor clearing environment."""

from __future__ import annotations

import os
import random
import subprocess
import tempfile
import threading
import uuid
import shutil
import math
import heapq
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openenv.core.env_server.interfaces import Environment
from openenv.core.rubrics.base import Rubric

RewardMode = Literal["clearing", "route_weights"]

try:
    from ..rubrics import resolve_rubric_from_env
    from ..decentralized import AgentRuntime
    from ..models import (
        DynamicCorridorAction,
        DynamicCorridorObservation,
        DynamicCorridorState,
        EVObservation,
        IntersectionObservation,
        RouteCandidateObservation,
        RouteChoiceObservation,
    )
except ImportError:
    from rubrics import resolve_rubric_from_env
    from decentralized import AgentRuntime
    from models import (
        DynamicCorridorAction,
        DynamicCorridorObservation,
        DynamicCorridorState,
        EVObservation,
        IntersectionObservation,
        RouteCandidateObservation,
        RouteChoiceObservation,
    )


@dataclass(frozen=True)
class CorridorScenario:
    task_id: str
    tls_ids: tuple[str, ...]
    ev_route_edges: tuple[str, ...]
    edge_to_intersection: dict[str, str]
    ev_id: str = "ambulance_0"
    max_sim_time_s: int = 900
    delta_time_s: int = 5


@dataclass(frozen=True)
class RoadEdge:
    edge_id: str
    from_node: str
    to_node: str
    speed_m_s: float
    length_m: float


GRID_TLS_IDS = tuple(f"INT_{row}_{col}" for row in range(1, 5) for col in range(1, 5))

GRID_DEFAULT_EV_ROUTE = (
    "NW_OUT_TO_INT_1_1",
    "INT_1_1_TO_INT_1_2",
    "INT_1_2_TO_INT_1_3",
    "INT_1_3_TO_INT_1_4",
    "INT_1_4_TO_INT_2_4",
    "INT_2_4_TO_INT_3_4",
    "INT_3_4_TO_INT_4_4",
    "INT_4_4_TO_SE_OUT",
)


def _grid_edge_to_intersection() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in range(1, 5):
        for col in range(1, 5):
            intersection = f"INT_{row}_{col}"
            if col > 1:
                mapping[f"INT_{row}_{col - 1}_TO_{intersection}"] = intersection
            if col < 4:
                mapping[f"INT_{row}_{col + 1}_TO_{intersection}"] = intersection
            if row > 1:
                mapping[f"INT_{row - 1}_{col}_TO_{intersection}"] = intersection
            if row < 4:
                mapping[f"INT_{row + 1}_{col}_TO_{intersection}"] = intersection

    mapping.update(
        {
            "NW_OUT_TO_INT_1_1": "INT_1_1",
            "E1_TO_INT_1_4": "INT_1_4",
            "W2_TO_INT_2_1": "INT_2_1",
            "E2_TO_INT_2_4": "INT_2_4",
            "W3_TO_INT_3_1": "INT_3_1",
            "E3_TO_INT_3_4": "INT_3_4",
            "W4_TO_INT_4_1": "INT_4_1",
            "SE_OUT_TO_INT_4_4": "INT_4_4",
            "N1_TO_INT_1_1": "INT_1_1",
            "N2_TO_INT_1_2": "INT_1_2",
            "N3_TO_INT_1_3": "INT_1_3",
            "N4_TO_INT_1_4": "INT_1_4",
            "S1_TO_INT_4_1": "INT_4_1",
            "S2_TO_INT_4_2": "INT_4_2",
            "S3_TO_INT_4_3": "INT_4_3",
            "S4_TO_INT_4_4": "INT_4_4",
        }
    )
    return mapping


DEFAULT_SCENARIO = CorridorScenario(
    task_id="grid_4x4_default",
    tls_ids=GRID_TLS_IDS,
    ev_route_edges=GRID_DEFAULT_EV_ROUTE,
    edge_to_intersection=_grid_edge_to_intersection(),
)


class DynamicCorridorEnvironment(Environment):
    """Central-agent SUMO environment for emergency green-corridor learning."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def __init__(
        self,
        net_file: str | None = None,
        route_file: str | None = None,
        sumo_binary: str | None = None,
        delta_time_s: int | None = None,
        max_sim_time_s: int | None = None,
        seed: int | None = None,
        reward_mode: RewardMode | str | None = None,
        rubric: Rubric | None = None,
    ):
        super().__init__(transform=None, rubric=None)
        self.scenario = DEFAULT_SCENARIO
        self.env_dir = Path(__file__).resolve().parent.parent
        self.net_file = Path(net_file or os.getenv(
            "DYNAMIC_CORRIDOR_NET_FILE",
            str(self.env_dir / "nets" / "pune-5" / "pune-5.net.xml"),
        ))
        self.route_file = Path(route_file or os.getenv(
            "DYNAMIC_CORRIDOR_ROUTE_FILE",
            str(self.env_dir / "nets" / "pune-5" / "pune-5.rou.xml"),
        ))
        self.node_file = self.net_file.with_name(f"{self.net_file.name.removesuffix('.net.xml')}.nod.xml")
        self.edge_file = self.net_file.with_name(f"{self.net_file.name.removesuffix('.net.xml')}.edg.xml")
        self.sumo_binary = sumo_binary or os.getenv("SUMO_BINARY", "sumo")
        self.scenario = CorridorScenario(
            task_id=self.scenario.task_id,
            tls_ids=self.scenario.tls_ids,
            ev_route_edges=self.scenario.ev_route_edges,
            edge_to_intersection=self.scenario.edge_to_intersection,
            ev_id=self.scenario.ev_id,
            max_sim_time_s=int(max_sim_time_s or os.getenv("DYNAMIC_CORRIDOR_MAX_SECONDS", self.scenario.max_sim_time_s)),
            delta_time_s=int(delta_time_s or os.getenv("DYNAMIC_CORRIDOR_DELTA_TIME", self.scenario.delta_time_s)),
        )
        self.seed = int(seed if seed is not None else os.getenv("DYNAMIC_CORRIDOR_SEED", "42"))
        _mode = (reward_mode or os.getenv("DYNAMIC_CORRIDOR_REWARD_MODE", "clearing")).strip().lower()
        if _mode not in ("clearing", "route_weights"):
            raise ValueError(
                f"Invalid DYNAMIC_CORRIDOR_REWARD_MODE or reward_mode={_mode!r}; "
                "use 'clearing' or 'route_weights'."
            )
        self._reward_mode: RewardMode = _mode  # type: ignore[assignment]

        self.rubric = (
            rubric
            if rubric is not None
            else resolve_rubric_from_env(os.getenv("DYNAMIC_CORRIDOR_RUBRIC"), self.scenario.max_sim_time_s)
        )

        self._traci = None
        self._label = f"dynamic_corridor_{uuid.uuid4().hex}"
        self._state = DynamicCorridorState(episode_id=str(uuid.uuid4()))
        self._done = False
        self._last_metrics = self._empty_metrics()
        self._cumulative_reward = 0.0
        self._ev_waiting_time = 0.0
        self._phase_changes = 0
        self._phase_elapsed_steps: dict[str, int] = {
            tls_id: 0 for tls_id in self.scenario.tls_ids
        }
        self._source_id = "NW_OUT"
        self._destination_id = "SE_OUT"
        self._episode_index = 0
        self._road_edges, self._node_xy, self._outgoing_edges = self._load_road_graph()
        self._road_weights: dict[str, float] = {}
        self._active_route_edges: list[str] = list(self.scenario.ev_route_edges)
        self._pending_ev_route_edges: list[str] | None = None
        self._active_route_file: Path = self.route_file
        self._agent_runtime = AgentRuntime(self.scenario.tls_ids)
        self._lock = threading.RLock()
        self._invalid_actions_episode = 0

    def _reward_bounds(self) -> tuple[float, float]:
        if self._reward_mode == "route_weights":
            return (0.0, 1.0)
        return (-10.0, 10.0)

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        **kwargs: Any,
    ) -> DynamicCorridorObservation:
        """OpenEnv-compatible reset; pass task_id, source_id, destination_id via kwargs."""
        task_id = str(kwargs.get("task_id", self.scenario.task_id))
        source_id = str(kwargs.get("source_id", "NW_OUT"))
        destination_id = str(kwargs.get("destination_id", "SE_OUT"))
        with self._lock:
            return self._reset_unlocked(
                task_id,
                source_id,
                destination_id,
                seed=seed,
                episode_id=episode_id,
            )

    def _reset_unlocked(
        self,
        task_id: str = "grid_4x4_default",
        source_id: str = "NW_OUT",
        destination_id: str = "SE_OUT",
        seed: int | None = None,
        episode_id: str | None = None,
    ) -> DynamicCorridorObservation:
        if task_id != self.scenario.task_id:
            raise ValueError(f"Unsupported task_id '{task_id}'. Expected '{self.scenario.task_id}'.")
        self._reset_rubric()
        if seed is not None:
            self.seed = int(seed)
        self._invalid_actions_episode = 0
        self._configure_route_choice(source_id, destination_id)

        self._ensure_net_file()
        self._close_sumo()
        self._start_sumo()

        self._done = False
        self._cumulative_reward = 0.0
        self._ev_waiting_time = 0.0
        self._phase_changes = 0
        self._phase_elapsed_steps = {
            tls_id: 0 for tls_id in self.scenario.tls_ids
        }
        self._last_metrics = self._collect_metrics()
        ep_id = episode_id if episode_id else str(uuid.uuid4())
        n_tls = max(1, len(self.scenario.tls_ids))
        mean_q = float(self._last_metrics["total_queue"]) / n_tls
        self._state = DynamicCorridorState(
            episode_id=ep_id,
            task_id=task_id,
            step_count=0,
            sim_time=0.0,
            cumulative_reward=0.0,
            done=False,
            reward_mode=self._reward_mode,
            invalid_action_count_episode=0,
            mean_corridor_queue=round(mean_q, 3),
            ev_clearing_success=bool(self._last_metrics.get("ev_arrived")),
            episode_timeout=False,
            episode_seed=int(self.seed),
            last_rubric_score=None,
        )
        observation = self._observe(0.0, "Episode started.")
        self._agent_runtime.reset(observation)
        self._state.agent_runtime = self._agent_runtime.state()
        observation.global_metrics["agent_runtime"] = self._agent_runtime.state()
        return observation

    def step(self, action: DynamicCorridorAction | None = None) -> DynamicCorridorObservation:
        with self._lock:
            return self._step_unlocked(action or DynamicCorridorAction())

    def _step_unlocked(self, action: DynamicCorridorAction) -> DynamicCorridorObservation:
        if self._traci is None:
            raise RuntimeError("Environment must be reset before step().")
        if self._done:
            return self._observe(0.0, "Episode already finished.")

        current_observation = self._observe(0.0, "Agent-routed step planning.")
        agent_action = self._agent_runtime.step(current_observation)
        agent_action.next_edge_id = action.next_edge_id
        if action.reason:
            agent_action.reason = f"{agent_action.reason} | client_reason={action.reason}"

        route_feedback = self._apply_route_choice(agent_action)
        invalid_actions = self._apply_action(agent_action)
        if route_feedback["invalid"]:
            invalid_actions += 1
        previous = self._last_metrics
        self._advance_sumo()
        current = self._collect_metrics()

        raw_reward, feedback = self._compute_reward(previous, current, invalid_actions, route_feedback)
        self._last_metrics = current
        self._invalid_actions_episode += int(invalid_actions)

        self._done = bool(current["ev_arrived"] or current["sim_time"] >= self.scenario.max_sim_time_s)
        if self._reward_mode == "clearing":
            if self._done and current["ev_arrived"]:
                raw_reward += max(0.0, 500.0 - current["ev_travel_time"])
                feedback += " | ambulance arrived"
            elif self._done:
                raw_reward -= 500.0
                feedback += " | timeout before ambulance arrival"
        else:
            if self._done and current["ev_arrived"]:
                feedback += " | ambulance arrived"
            elif self._done:
                feedback += " | timeout before ambulance arrival"

        reward = self._normalize_reward(raw_reward)
        self._cumulative_reward += reward
        feedback += (
            f" raw_reward={raw_reward:.3f} normalized_reward={reward:.3f} "
            f"active_agent={self._agent_runtime.state().get('active_agent_id', '') or '-'} "
            f"touched_agents={len(self._agent_runtime.state().get('last_touched_agent_ids', []))}"
        )

        self._state.step_count += 1
        self._sync_state(current)
        observation = self._observe(round(reward, 3), feedback)
        if self.rubric is not None:
            rubric_score = float(self._apply_rubric(action, observation))
            observation.metadata["rubric_score"] = rubric_score
            observation.global_metrics["rubric_score"] = rubric_score
            for path, child in self.rubric.named_rubrics():
                if child.last_score is not None:
                    observation.metadata.setdefault("rubric_scores", {})[path] = child.last_score
            self._state.last_rubric_score = rubric_score
        else:
            self._state.last_rubric_score = None
        return observation

    @property
    def state(self) -> DynamicCorridorState:
        return self._state

    def _load_road_graph(self) -> tuple[dict[str, RoadEdge], dict[str, tuple[float, float]], dict[str, list[str]]]:
        if not self.node_file.exists() or not self.edge_file.exists():
            raise FileNotFoundError(f"Missing SUMO graph source files: {self.node_file} / {self.edge_file}")

        nodes_root = ET.parse(self.node_file).getroot()
        node_xy: dict[str, tuple[float, float]] = {}
        for node in nodes_root.findall("node"):
            node_id = str(node.attrib["id"])
            node_xy[node_id] = (float(node.attrib.get("x", 0.0)), float(node.attrib.get("y", 0.0)))

        edges_root = ET.parse(self.edge_file).getroot()
        road_edges: dict[str, RoadEdge] = {}
        outgoing: dict[str, list[str]] = {}
        for edge in edges_root.findall("edge"):
            edge_id = str(edge.attrib["id"])
            from_node = str(edge.attrib["from"])
            to_node = str(edge.attrib["to"])
            speed = float(edge.attrib.get("speed", 13.9))
            length = self._node_distance(from_node, to_node, node_xy)
            road_edges[edge_id] = RoadEdge(
                edge_id=edge_id,
                from_node=from_node,
                to_node=to_node,
                speed_m_s=speed,
                length_m=length,
            )
            outgoing.setdefault(from_node, []).append(edge_id)
        return road_edges, node_xy, outgoing

    @staticmethod
    def _node_distance(
        from_node: str,
        to_node: str,
        node_xy: dict[str, tuple[float, float]],
    ) -> float:
        fx, fy = node_xy.get(from_node, (0.0, 0.0))
        tx, ty = node_xy.get(to_node, (fx, fy))
        return max(1.0, math.hypot(tx - fx, ty - fy))

    def _configure_route_choice(self, source_id: str, destination_id: str) -> None:
        if source_id not in self._node_xy:
            raise ValueError(f"Unknown source_id '{source_id}'.")
        if destination_id not in self._node_xy:
            raise ValueError(f"Unknown destination_id '{destination_id}'.")
        if source_id == destination_id:
            raise ValueError("source_id and destination_id must be different.")

        self._source_id = source_id
        self._destination_id = destination_id
        self._episode_index += 1
        self._road_weights = self._generate_road_weights(self.seed, self._episode_index)
        route = self._shortest_path_edges(source_id, destination_id)
        if not route:
            raise ValueError(f"No route from source_id '{source_id}' to destination_id '{destination_id}'.")
        self._active_route_edges = route
        self._pending_ev_route_edges = None
        self._active_route_file = self._write_episode_route_file(route)

    def _generate_road_weights(self, seed: int, episode_index: int) -> dict[str, float]:
        rng = random.Random(f"{seed}:{episode_index}:{self._source_id}:{self._destination_id}")
        return {
            edge_id: round(rng.random(), 6)
            for edge_id in sorted(self._road_edges)
        }

    def _write_episode_route_file(self, ev_route_edges: list[str]) -> Path:
        root = ET.parse(self.route_file).getroot()
        route_text = " ".join(ev_route_edges)
        for route in root.findall("route"):
            if route.attrib.get("id") == "ev_route":
                route.set("edges", route_text)
                break
        else:
            ET.SubElement(root, "route", {"id": "ev_route", "edges": route_text})

        for vehicle in root.findall("vehicle"):
            if vehicle.attrib.get("id") == self.scenario.ev_id:
                vehicle.set("route", "ev_route")
                break

        temp_dir = Path(tempfile.gettempdir()) / "dynamic_corridor_env"
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"{self._label}_{self._episode_index}.rou.xml"
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=False)
        return path

    def _edge_cost(self, edge_id: str, include_live_queue: bool = False) -> float:
        edge = self._road_edges[edge_id]
        weight = self._road_weights.get(edge_id, 0.0)
        queue_cost = self._edge_queue(edge_id) if include_live_queue else 0.0
        return edge.length_m * (1.0 + weight) + queue_cost * 25.0

    def _shortest_path_edges(self, source_id: str, destination_id: str) -> list[str] | None:
        if source_id == destination_id:
            return []

        heap: list[tuple[float, str, list[str]]] = [(0.0, source_id, [])]
        best: dict[str, float] = {source_id: 0.0}
        while heap:
            cost, node_id, path = heapq.heappop(heap)
            if node_id == destination_id:
                return path
            if cost > best.get(node_id, math.inf):
                continue
            for edge_id in self._outgoing_edges.get(node_id, []):
                edge = self._road_edges[edge_id]
                next_cost = cost + self._edge_cost(edge_id)
                if next_cost < best.get(edge.to_node, math.inf):
                    best[edge.to_node] = next_cost
                    heapq.heappush(heap, (next_cost, edge.to_node, [*path, edge_id]))
        return None

    def _destination_distance(self, node_id: str) -> float:
        return self._node_distance(node_id, self._destination_id, self._node_xy)

    def _route_choice_position(self) -> tuple[str, str, str]:
        if self._traci is None or not self._vehicle_exists(self.scenario.ev_id):
            return self._source_id, "", ""

        current_edge = self._traci.vehicle.getRoadID(self.scenario.ev_id)
        if current_edge in self._road_edges:
            edge = self._road_edges[current_edge]
            return edge.to_node, current_edge, current_edge

        route_index = self._traci.vehicle.getRouteIndex(self.scenario.ev_id)
        route = list(self._traci.vehicle.getRoute(self.scenario.ev_id))
        if 0 <= route_index < len(route) and route[route_index] in self._road_edges:
            edge_id = route[route_index]
            edge = self._road_edges[edge_id]
            return edge.to_node, edge_id, edge_id
        return self._destination_id, current_edge, ""

    def _route_candidates(self, current_node: str, previous_edge_id: str) -> list[RouteCandidateObservation]:
        if current_node == self._destination_id:
            return []

        current_distance = self._destination_distance(current_node)
        candidates: list[RouteCandidateObservation] = []
        previous_edge = self._road_edges.get(previous_edge_id)
        for edge_id in self._outgoing_edges.get(current_node, []):
            edge = self._road_edges[edge_id]
            next_distance = self._destination_distance(edge.to_node)
            tail = self._shortest_path_edges(edge.to_node, self._destination_id)
            is_backtrack = bool(
                previous_edge
                and previous_edge.from_node == edge.to_node
                and previous_edge.to_node == edge.from_node
            )
            delta = current_distance - next_distance
            candidates.append(
                RouteCandidateObservation(
                    edge_id=edge.edge_id,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    road_weight=self._road_weights.get(edge_id, 0.0),
                    estimated_queue=self._edge_queue(edge_id),
                    length_m=round(edge.length_m, 3),
                    speed_m_s=edge.speed_m_s,
                    destination_distance_delta=round(delta, 3),
                    moves_closer=delta > 0.0,
                    is_backtrack=is_backtrack,
                    destination_reachable=tail is not None,
                )
            )
        return candidates

    def _ensure_net_file(self) -> None:
        stem = self.net_file.name.removesuffix(".net.xml")
        nod_file = self.net_file.with_name(f"{stem}.nod.xml")
        edg_file = self.net_file.with_name(f"{stem}.edg.xml")
        if not nod_file.exists() or not edg_file.exists():
            raise FileNotFoundError(f"Missing SUMO source files: {nod_file} / {edg_file}")
        if (
            self.net_file.exists()
            and self.net_file.stat().st_mtime >= nod_file.stat().st_mtime
            and self.net_file.stat().st_mtime >= edg_file.stat().st_mtime
        ):
            return

        self.net_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self._sumo_binary("netconvert"),
            "--node-files",
            str(nod_file),
            "--edge-files",
            str(edg_file),
            "--output-file",
            str(self.net_file),
            "--tls.guess",
            "true",
            "--no-turnarounds",
            "true",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            binary = cmd[0]
            raise RuntimeError(
                f"Could not run SUMO tool {binary!r} (file not found). "
                "Install SUMO so that netconvert (and sumo) are on PATH, e.g. "
                "`brew install sumo` on macOS, or `pip install eclipse-sumo` from "
                "https://sumo.dlr.de/daily/wheels/ and ensure SUMO_HOME is set, "
                "or place a pre-generated net at "
                f"{str(self.net_file)} to skip this step (see README)."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Failed to generate SUMO network with netconvert. "
                f"Command: {' '.join(cmd)}\n"
                f"exit_code={exc.returncode}\n"
                f"stdout={exc.stdout}\n"
                f"stderr={exc.stderr}"
            ) from exc

    def _start_sumo(self) -> None:
        try:
            import traci
        except ImportError as exc:
            raise ImportError("traci is required. Install SUMO Python tools with `pip install traci`.") from exc

        self._label = f"dynamic_corridor_{uuid.uuid4().hex}"
        cmd = [
            self._sumo_binary(self.sumo_binary),
            "-n",
            str(self.net_file),
            "-r",
            str(self._active_route_file),
            "--seed",
            str(self.seed),
            "--no-warnings",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "-1",
        ]
        traci.start(cmd, label=self._label)
        self._traci = traci.getConnection(self._label)

    def _sumo_binary(self, binary: str) -> str:
        """Resolve SUMO binaries from PATH, SUMO_HOME, or the eclipse-sumo wheel."""
        if os.path.isabs(binary) or shutil.which(binary):
            return binary
        if "SUMO_HOME" not in os.environ:
            try:
                import sumo

                os.environ["SUMO_HOME"] = sumo.SUMO_HOME
            except Exception:
                pass
        try:
            import sumolib

            return sumolib.checkBinary(binary)
        except Exception as exc:
            raise RuntimeError(
                f"Could not locate SUMO binary '{binary}'. Install SUMO locally or install "
                "`eclipse-sumo` from https://sumo.dlr.de/daily/wheels/."
            ) from exc

    def _close_sumo(self) -> None:
        if self._traci is not None:
            try:
                self._traci.close()
            except Exception:
                pass
            self._traci = None

    def _apply_action(self, action: DynamicCorridorAction) -> int:
        invalid = 0
        changed: set[str] = set()
        for tls_id, target_phase in action.phase_by_intersection.items():
            if tls_id not in self.scenario.tls_ids:
                invalid += 1
                continue
            valid_phases = self._valid_green_phases(tls_id)
            if target_phase not in valid_phases:
                invalid += 1
                continue
            current_phase = self._traci.trafficlight.getPhase(tls_id)
            if current_phase != target_phase:
                self._traci.trafficlight.setPhase(tls_id, target_phase)
                self._phase_changes += 1
                changed.add(tls_id)
        for tls_id in self.scenario.tls_ids:
            if tls_id in changed:
                self._phase_elapsed_steps[tls_id] = 0
            else:
                self._phase_elapsed_steps[tls_id] = self._phase_elapsed_steps.get(tls_id, 0) + 1
        return invalid

    def _apply_route_choice(self, action: DynamicCorridorAction) -> dict[str, Any]:
        edge_id = action.next_edge_id
        feedback: dict[str, Any] = {
            "selected_edge": edge_id or "",
            "invalid": False,
            "reason": "none",
            "road_weight": 0.0,
            "estimated_queue": 0.0,
            "moves_closer": False,
            "is_backtrack": False,
            "destination_distance_delta": 0.0,
        }
        if not edge_id:
            return feedback

        current_node, _, previous_edge_id = self._route_choice_position()
        candidates = {candidate.edge_id: candidate for candidate in self._route_candidates(current_node, previous_edge_id)}
        candidate = candidates.get(edge_id)
        if candidate is None:
            feedback.update({"invalid": True, "reason": "not_candidate"})
            return feedback
        if not candidate.destination_reachable:
            feedback.update({"invalid": True, "reason": "unreachable"})
            return feedback

        tail = self._shortest_path_edges(candidate.to_node, self._destination_id)
        if tail is None:
            feedback.update({"invalid": True, "reason": "unreachable"})
            return feedback

        future_route = [edge_id, *tail]
        self._active_route_edges = self._route_prefix_for_active_vehicle() + future_route
        feedback.update(
            {
                "reason": "accepted",
                "road_weight": candidate.road_weight,
                "estimated_queue": candidate.estimated_queue,
                "moves_closer": candidate.moves_closer,
                "is_backtrack": candidate.is_backtrack,
                "destination_distance_delta": candidate.destination_distance_delta,
            }
        )

        if self._traci is None or not self._vehicle_exists(self.scenario.ev_id):
            self._pending_ev_route_edges = future_route
            return feedback

        route = self._route_prefix_for_active_vehicle() + future_route
        try:
            self._traci.vehicle.setRoute(self.scenario.ev_id, route)
        except Exception as exc:
            feedback.update({"invalid": True, "reason": f"reroute_failed:{exc}"})
        return feedback

    def _route_prefix_for_active_vehicle(self) -> list[str]:
        if self._traci is None or not self._vehicle_exists(self.scenario.ev_id):
            return []
        current_edge = self._traci.vehicle.getRoadID(self.scenario.ev_id)
        if current_edge in self._road_edges:
            return [current_edge]
        return []

    def _apply_pending_ev_route(self) -> None:
        if not self._pending_ev_route_edges or self._traci is None:
            return
        if not self._vehicle_exists(self.scenario.ev_id):
            return
        prefix = self._route_prefix_for_active_vehicle()
        if prefix and self._pending_ev_route_edges[0] == prefix[0]:
            route = list(self._pending_ev_route_edges)
        else:
            route = prefix + self._pending_ev_route_edges
        try:
            self._traci.vehicle.setRoute(self.scenario.ev_id, route)
            self._active_route_edges = route
            self._pending_ev_route_edges = None
        except Exception:
            pass

    def _advance_sumo(self) -> None:
        for _ in range(self.scenario.delta_time_s):
            if self._traci.simulation.getMinExpectedNumber() <= 0:
                break
            self._traci.simulationStep()
            self._apply_pending_ev_route()
            if self._vehicle_exists(self.scenario.ev_id):
                speed = self._traci.vehicle.getSpeed(self.scenario.ev_id)
                if speed < 0.1:
                    self._ev_waiting_time += 1.0

    def _mean_active_route_road_weight(self) -> float:
        """Mean of per-edge seeded [0,1] weights over the current active EV route (road ids only)."""
        if not self._active_route_edges:
            return 0.0
        weights = [float(self._road_weights.get(eid, 0.0)) for eid in self._active_route_edges]
        return sum(weights) / max(1, len(weights))

    def _compute_reward(
        self,
        previous: dict[str, Any],
        current: dict[str, Any],
        invalid_actions: int,
        route_feedback: dict[str, Any] | None,
    ) -> tuple[float, str]:
        route_feedback = route_feedback or {}
        if self._reward_mode == "route_weights":
            return self._compute_reward_route_weights(route_feedback)
        return self._compute_reward_clearing(previous, current, invalid_actions, route_feedback)

    def _compute_reward_route_weights(self, route_feedback: dict[str, Any]) -> tuple[float, str]:
        """[0,1] reward from mean seeded edge weight on the active route only; invalid route -> 0."""
        mean_w = self._mean_active_route_road_weight()
        if route_feedback.get("invalid"):
            raw = 0.0
        else:
            raw = 1.0 - mean_w
        raw = max(0.0, min(1.0, float(raw)))
        feedback = (
            f"reward_mode=route_weights mean_road_weight={mean_w:.4f} reward={raw:.4f} "
            f"route_invalid={int(bool(route_feedback.get('invalid')))} "
            f"route_edge={route_feedback.get('selected_edge', '') or '-'}"
        )
        return raw, feedback

    def _compute_reward_clearing(
        self,
        previous: dict[str, Any],
        current: dict[str, Any],
        invalid_actions: int,
        route_feedback: dict[str, Any],
    ) -> tuple[float, str]:
        """Default corridor-clearing shaped reward; normalized to ~[-10, 10] after terminal terms in step()."""
        ev_progress_delta = current["ev_progress"] - previous["ev_progress"]
        ev_wait_delta = current["ev_waiting_time"] - previous["ev_waiting_time"]
        throughput_delta = current["throughput"] - previous["throughput"]
        phase_delta = current["phase_changes"] - previous["phase_changes"]
        queue_overflow = max(0.0, current["max_queue"] - 50.0)
        route_delta = float(route_feedback.get("destination_distance_delta", 0.0))
        route_reward = 0.05 * route_delta
        route_reward -= 10.0 * float(route_feedback.get("road_weight", 0.0))
        route_reward -= 0.25 * float(route_feedback.get("estimated_queue", 0.0))
        if route_feedback.get("is_backtrack"):
            route_reward -= 75.0
        if route_feedback.get("selected_edge") and not route_feedback.get("moves_closer", False):
            route_reward -= 25.0
        if route_feedback.get("invalid"):
            route_reward -= 50.0

        reward = (
            20.0 * ev_progress_delta
            - 100.0 * ev_wait_delta
            - 1.0 * current["total_queue"]
            - 2.0 * queue_overflow
            - 0.1 * phase_delta
            + 0.5 * throughput_delta
            - 5.0 * invalid_actions
            + route_reward
        )

        feedback = (
            f"reward_mode=clearing progress_delta={ev_progress_delta:.3f} "
            f"ev_wait_delta={ev_wait_delta:.1f}s queue={current['total_queue']:.1f} "
            f"throughput_delta={throughput_delta} invalid_actions={invalid_actions} "
            f"route_edge={route_feedback.get('selected_edge', '') or '-'} "
            f"route_delta={route_delta:.1f} route_backtrack={int(bool(route_feedback.get('is_backtrack')))} "
            f"route_invalid={int(bool(route_feedback.get('invalid')))}"
        )
        return reward, feedback

    def _normalize_reward(self, reward: float) -> float:
        lo, hi = self._reward_bounds()
        return max(lo, min(hi, float(reward)))

    def _collect_metrics(self) -> dict[str, Any]:
        total_queue = 0.0
        max_queue = 0.0
        total_vehicle_count = 0
        total_speed = 0.0
        speed_count = 0

        for tls_id in self.scenario.tls_ids:
            tls_queue = 0.0
            for lane_id in set(self._traci.trafficlight.getControlledLanes(tls_id)):
                halted = self._traci.lane.getLastStepHaltingNumber(lane_id)
                count = self._traci.lane.getLastStepVehicleNumber(lane_id)
                mean_speed = self._traci.lane.getLastStepMeanSpeed(lane_id)
                tls_queue += halted
                total_vehicle_count += count
                if count > 0:
                    total_speed += mean_speed
                    speed_count += 1
            total_queue += tls_queue
            max_queue = max(max_queue, tls_queue)

        sim_time = float(self._traci.simulation.getTime())
        ev_arrived = (not self._vehicle_exists(self.scenario.ev_id)) and sim_time > 0
        ev_progress = 1.0 if ev_arrived and sim_time > 0 else self._ev_progress()

        return {
            "sim_time": sim_time,
            "total_queue": total_queue,
            "max_queue": max_queue,
            "vehicle_count": total_vehicle_count,
            "mean_speed": total_speed / max(1, speed_count),
            "throughput": int(self._traci.simulation.getArrivedNumber()),
            "ev_progress": ev_progress,
            "ev_arrived": ev_arrived,
            "ev_waiting_time": self._ev_waiting_time,
            "ev_travel_time": sim_time,
            "phase_changes": self._phase_changes,
        }

    def _corridor_eval_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Structured metrics for rubrics / baselines (no string parsing)."""
        n_tls = max(1, len(self.scenario.tls_ids))
        mean_q = float(metrics.get("total_queue", 0.0)) / n_tls
        return {
            "reward_mode": self._reward_mode,
            "invalid_action_count_episode": self._invalid_actions_episode,
            "mean_corridor_queue": round(mean_q, 3),
            "ev_travel_time_s": round(float(metrics.get("ev_travel_time", 0.0)), 3),
            "ev_clearing_success": bool(metrics.get("ev_arrived")),
            "episode_timeout": bool(self._done and not metrics.get("ev_arrived")),
            "n_signalized_intersections": n_tls,
        }

    def _observe(self, reward: float, feedback: str) -> DynamicCorridorObservation:
        metrics = self._last_metrics if self._traci is not None else self._empty_metrics()
        intersections = [self._intersection_observation(tls_id) for tls_id in self.scenario.tls_ids]
        eval_block = self._corridor_eval_metrics(metrics)
        return DynamicCorridorObservation(
            task_id=self._state.task_id,
            sim_time=metrics["sim_time"],
            step=self._state.step_count,
            intersections=intersections,
            ev=self._ev_observation(metrics),
            route_choice=self._route_choice_observation(),
            global_metrics={
                "total_queue": round(metrics["total_queue"], 3),
                "max_queue": round(metrics["max_queue"], 3),
                "vehicle_count": metrics["vehicle_count"],
                "mean_speed": round(metrics["mean_speed"], 3),
                "throughput": metrics["throughput"],
                "phase_changes": metrics["phase_changes"],
                "agent_runtime": self._agent_runtime.state(),
                **eval_block,
            },
            reward=reward,
            done=self._done,
            feedback=feedback,
        )

    def _route_choice_observation(self) -> RouteChoiceObservation:
        current_node, current_edge, previous_edge = self._route_choice_position()
        return RouteChoiceObservation(
            source_id=self._source_id,
            destination_id=self._destination_id,
            current_node=current_node,
            current_edge_id=current_edge,
            previous_edge_id=previous_edge,
            active_route_edges=list(self._active_route_edges),
            road_weights=dict(self._road_weights),
            candidates=self._route_candidates(current_node, previous_edge),
        )

    def _intersection_observation(self, tls_id: str) -> IntersectionObservation:
        lanes = set(self._traci.trafficlight.getControlledLanes(tls_id))
        queue = sum(self._traci.lane.getLastStepHaltingNumber(lane_id) for lane_id in lanes)
        vehicle_count = sum(self._traci.lane.getLastStepVehicleNumber(lane_id) for lane_id in lanes)
        speeds = [
            self._traci.lane.getLastStepMeanSpeed(lane_id)
            for lane_id in lanes
            if self._traci.lane.getLastStepVehicleNumber(lane_id) > 0
        ]
        ev_edge = self._ev_approach_edge_for(tls_id)
        ev_eta_steps, ev_distance_m = self._ev_eta_distance_to_edge(ev_edge)
        return IntersectionObservation(
            intersection_id=tls_id,
            current_phase=self._traci.trafficlight.getPhase(tls_id),
            valid_phases=self._valid_green_phases(tls_id),
            queue_by_phase=self._queue_by_phase(tls_id),
            elapsed_phase_time=self._phase_elapsed_steps.get(tls_id, 0),
            queue_length=float(queue),
            vehicle_count=int(vehicle_count),
            mean_speed=float(sum(speeds) / max(1, len(speeds))),
            is_on_ev_route=bool(ev_edge),
            ev_approach_edge=ev_edge,
            ev_target_phase=self._ev_target_phase(tls_id, ev_edge),
            ev_eta_steps=ev_eta_steps,
            ev_distance_m=ev_distance_m,
        )

    def _ev_observation(self, metrics: dict[str, Any]) -> EVObservation:
        current_edge, route_index, edge_progress = self._ev_position()
        return EVObservation(
            ev_id=self.scenario.ev_id,
            route_edges=list(self._active_route_edges),
            current_edge=current_edge,
            route_index=route_index,
            edge_progress=round(edge_progress, 4),
            next_intersection=self._next_ev_intersection(),
            progress=round(metrics["ev_progress"], 4),
            waiting_time=round(metrics["ev_waiting_time"], 3),
            travel_time=round(metrics["ev_travel_time"], 3),
            arrived=bool(metrics["ev_arrived"]),
        )

    def _sync_state(self, metrics: dict[str, Any]) -> None:
        n_tls = max(1, len(self.scenario.tls_ids))
        self._state.sim_time = metrics["sim_time"]
        self._state.cumulative_reward = round(self._cumulative_reward, 3)
        self._state.ev_arrived = metrics["ev_arrived"]
        self._state.ev_travel_time = metrics["ev_travel_time"]
        self._state.ev_waiting_time = metrics["ev_waiting_time"]
        self._state.total_queue = metrics["total_queue"]
        self._state.max_queue = metrics["max_queue"]
        self._state.throughput = metrics["throughput"]
        self._state.phase_changes = metrics["phase_changes"]
        self._state.agent_runtime = self._agent_runtime.state()
        self._state.done = self._done
        self._state.reward_mode = self._reward_mode
        self._state.invalid_action_count_episode = self._invalid_actions_episode
        self._state.mean_corridor_queue = round(float(metrics["total_queue"]) / n_tls, 3)
        self._state.ev_clearing_success = bool(metrics["ev_arrived"])
        self._state.episode_timeout = bool(self._done and not metrics["ev_arrived"])
        self._state.episode_seed = int(self.seed)
        if self.rubric is None:
            self._state.last_rubric_score = None

    def _valid_green_phases(self, tls_id: str) -> list[int]:
        program = self._traci.trafficlight.getAllProgramLogics(tls_id)[0]
        valid = []
        for idx, phase in enumerate(program.phases):
            state = phase.state
            if ("G" in state or "g" in state) and "y" not in state.lower():
                valid.append(idx)
        return valid

    def _queue_by_phase(self, tls_id: str) -> dict[int, float]:
        controlled_lanes = self._traci.trafficlight.getControlledLanes(tls_id)
        program = self._traci.trafficlight.getAllProgramLogics(tls_id)[0]
        queues: dict[int, float] = {}
        for idx in self._valid_green_phases(tls_id):
            phase = program.phases[idx]
            phase_lanes = {
                lane_id
                for link_idx, lane_id in enumerate(controlled_lanes)
                if link_idx < len(phase.state) and phase.state[link_idx] in {"G", "g"}
            }
            queues[idx] = float(
                sum(self._traci.lane.getLastStepHaltingNumber(lane_id) for lane_id in phase_lanes)
            )
        return queues

    def _ev_target_phase(self, tls_id: str, ev_edge: str) -> int | None:
        if not ev_edge:
            return None
        ev_lanes = {lane for lane in self._traci.trafficlight.getControlledLanes(tls_id) if lane.startswith(f"{ev_edge}_")}
        if not ev_lanes:
            return None
        controlled_lanes = self._traci.trafficlight.getControlledLanes(tls_id)
        program = self._traci.trafficlight.getAllProgramLogics(tls_id)[0]
        for idx in self._valid_green_phases(tls_id):
            phase = program.phases[idx]
            for link_idx, lane_id in enumerate(controlled_lanes):
                if lane_id in ev_lanes and link_idx < len(phase.state) and phase.state[link_idx] in {"G", "g"}:
                    return idx
        return None

    def _ev_approach_edge_for(self, tls_id: str) -> str:
        active_route = list(self._active_route_edges)
        if self._traci is not None and self._vehicle_exists(self.scenario.ev_id):
            try:
                active_route = list(self._traci.vehicle.getRoute(self.scenario.ev_id))
            except Exception:
                pass
        for edge_id in active_route:
            if self.scenario.edge_to_intersection.get(edge_id) == tls_id:
                return edge_id
        for edge_id, intersection_id in self.scenario.edge_to_intersection.items():
            if intersection_id == tls_id:
                return edge_id
        return ""

    def _ev_eta_distance_to_edge(self, target_edge: str) -> tuple[float, float]:
        if not target_edge or not self._vehicle_exists(self.scenario.ev_id):
            return -1.0, -1.0

        route = list(self._traci.vehicle.getRoute(self.scenario.ev_id))
        current_edge = self._traci.vehicle.getRoadID(self.scenario.ev_id)
        if target_edge not in route or current_edge not in route:
            return -1.0, -1.0

        current_index = route.index(current_edge)
        target_index = route.index(target_edge)
        if target_index < current_index:
            return -1.0, -1.0

        distance_m = 0.0
        lane_id = self._traci.vehicle.getLaneID(self.scenario.ev_id)
        current_edge_length = self._lane_or_edge_length(current_edge, lane_id)
        current_position = self._traci.vehicle.getLanePosition(self.scenario.ev_id)
        if current_index == target_index:
            distance_m = max(0.0, current_edge_length - current_position)
        else:
            distance_m += max(0.0, current_edge_length - current_position)
            for edge_id in route[current_index + 1: target_index + 1]:
                distance_m += self._edge_length(edge_id)

        speed_m_s = self._estimated_ev_speed_m_s()
        eta_seconds = distance_m / max(speed_m_s, 0.1)
        eta_steps = math.ceil(eta_seconds / max(self.scenario.delta_time_s, 1))
        return float(eta_steps), round(float(distance_m), 3)

    def _estimated_ev_speed_m_s(self) -> float:
        if not self._vehicle_exists(self.scenario.ev_id):
            return 0.0
        speed = float(self._traci.vehicle.getSpeed(self.scenario.ev_id))
        if speed > 0.1:
            return speed
        try:
            lane_id = self._traci.vehicle.getLaneID(self.scenario.ev_id)
            allowed = float(self._traci.lane.getMaxSpeed(lane_id))
            if allowed > 0.1:
                return allowed
        except Exception:
            pass
        return 13.9

    def _lane_or_edge_length(self, edge_id: str, lane_id: str) -> float:
        try:
            if lane_id:
                return max(1.0, float(self._traci.lane.getLength(lane_id)))
        except Exception:
            pass
        return self._edge_length(edge_id)

    def _edge_length(self, edge_id: str) -> float:
        try:
            lane_count = int(self._traci.edge.getLaneNumber(edge_id))
        except Exception:
            lane_count = 1
        for idx in range(max(1, lane_count)):
            try:
                return max(1.0, float(self._traci.lane.getLength(f"{edge_id}_{idx}")))
            except Exception:
                continue
        return 1.0

    def _edge_queue(self, edge_id: str) -> float:
        if self._traci is None:
            return 0.0
        queue = 0.0
        try:
            lane_count = int(self._traci.edge.getLaneNumber(edge_id))
        except Exception:
            lane_count = self._road_edges.get(edge_id) and 1 or 0
        for idx in range(max(0, lane_count)):
            try:
                queue += float(self._traci.lane.getLastStepHaltingNumber(f"{edge_id}_{idx}"))
            except Exception:
                continue
        return queue

    def _next_ev_intersection(self) -> str:
        if not self._vehicle_exists(self.scenario.ev_id):
            return ""
        route_index = self._traci.vehicle.getRouteIndex(self.scenario.ev_id)
        route = self._traci.vehicle.getRoute(self.scenario.ev_id)
        if route_index < 0 or route_index >= len(route):
            return ""
        return self.scenario.edge_to_intersection.get(route[route_index], "")

    def _ev_progress(self) -> float:
        _, route_index, edge_progress = self._ev_position()
        if route_index < 0:
            return 1.0 if self._last_metrics.get("sim_time", 0.0) > 0 else 0.0
        route = self._traci.vehicle.getRoute(self.scenario.ev_id)
        return min(1.0, (route_index + edge_progress) / max(1, len(route)))

    def _ev_position(self) -> tuple[str, int, float]:
        if not self._vehicle_exists(self.scenario.ev_id):
            return "", -1, 0.0
        route = self._traci.vehicle.getRoute(self.scenario.ev_id)
        route_index = max(0, self._traci.vehicle.getRouteIndex(self.scenario.ev_id))
        current_edge = self._traci.vehicle.getRoadID(self.scenario.ev_id)
        edge_length = 1.0
        try:
            lane_id = self._traci.vehicle.getLaneID(self.scenario.ev_id)
            edge_length = max(1.0, self._traci.lane.getLength(lane_id))
        except Exception:
            pass
        edge_progress = min(1.0, max(0.0, self._traci.vehicle.getLanePosition(self.scenario.ev_id) / edge_length))
        if current_edge and route:
            try:
                route_index = route.index(current_edge)
            except ValueError:
                pass
        return current_edge, route_index, edge_progress

    def _vehicle_exists(self, vehicle_id: str) -> bool:
        return vehicle_id in self._traci.vehicle.getIDList()

    def close(self) -> None:
        """
        Keep environment state alive across HTTP requests.

        OpenEnv's HTTP handlers call close() after every request; for this
        environment we intentionally preserve the live SUMO session so
        `/reset` followed by `/step` via curl works as a single episode.
        """
        pass

    def shutdown(self) -> None:
        """Release SUMO resources when the server process exits."""
        self._close_sumo()

    @staticmethod
    def _empty_metrics() -> dict[str, Any]:
        return {
            "sim_time": 0.0,
            "total_queue": 0.0,
            "max_queue": 0.0,
            "vehicle_count": 0,
            "mean_speed": 0.0,
            "throughput": 0,
            "ev_progress": 0.0,
            "ev_arrived": False,
            "ev_waiting_time": 0.0,
            "ev_travel_time": 0.0,
            "phase_changes": 0,
        }
