"""Simulation service — orchestrates simulation lifecycle."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.app.api.ws_manager import ws_manager
from backend.app.config import settings
from backend.app.controllers.fixed_time import FixedTimeController
from backend.app.controllers.mcts_controller import MCTSController
from backend.app.models.ev import EVStatus
from backend.app.services.config_service import config_service
from backend.app.simulation.engine import EventDrivenSimulator, SimulationState
from backend.app.utils.helpers import gen_id, time_str_to_seconds


class SimulationService:
    """Manages active simulation instances."""

    def __init__(self):
        self._simulators: dict[str, EventDrivenSimulator] = {}
        self._states: dict[str, SimulationState] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_configs: dict[str, dict] = {}

    def init_simulation(self, name: str = "Unnamed Run",
                        corridor_id: str = "CORR_01",
                        controller_type: str = "mcts",
                        duration_s: float = 3600.0,
                        sim_speed: float = 1.0,
                        random_seed: int | None = None,
                        traffic_profile: str = "default",
                        start_time_of_day: str = "08:00") -> str:
        """Initialize a new simulation run."""
        run_id = gen_id("run")

        intersections = config_service.intersections
        corridor = config_service.corridor
        profile = config_service.profile

        # Build controller
        controller = None
        if controller_type == "mcts":
            controller = MCTSController.from_config(
                intersections, corridor, config_service.mcts_config
            )
        elif controller_type == "fixed_time":
            controller = FixedTimeController.from_timing_plans_json(
                config_service.timing_plans
            )

        start_tod = time_str_to_seconds(start_time_of_day)

        state = SimulationState(
            intersections=intersections,
            corridor=corridor,
            traffic_profile=profile,
            controller=controller,
            start_time_of_day_s=start_tod,
            replan_interval_s=settings.mcts_replan_interval_s,
            replan_interval_ev_s=settings.mcts_replan_interval_ev_s,
        )

        sim = EventDrivenSimulator(state, end_time=duration_s, seed=random_seed)
        sim.clock.set_speed(sim_speed)
        sim.initialize()

        self._simulators[run_id] = sim
        self._states[run_id] = state
        self._run_configs[run_id] = {
            "name": name,
            "corridor_id": corridor_id,
            "controller_type": controller_type,
            "duration_s": duration_s,
            "sim_speed": sim_speed,
            "random_seed": random_seed,
            "traffic_profile": traffic_profile,
            "start_time_of_day": start_time_of_day,
        }

        return run_id

    async def start(self, run_id: str) -> None:
        """Start simulation in real-time mode."""
        sim = self._get_sim(run_id)

        last_decision_count = 0

        async def broadcast(snapshot):
            nonlocal last_decision_count
            await ws_manager.broadcast_admin(run_id, {
                "type": "state_update",
                "data": snapshot,
                "sim_time": snapshot.get("sim_time"),
            })
            # Broadcast new MCTS decisions since last broadcast
            state = self._states[run_id]
            if (state.controller is not None
                    and hasattr(state.controller, 'decision_history')):
                history = state.controller.decision_history
                while last_decision_count < len(history):
                    d = history[last_decision_count]
                    d_dict = d.to_dict()
                    d_dict["decision_id"] = f"mcts_{last_decision_count}"
                    d_dict["sim_time"] = snapshot.get("sim_time", 0)
                    await ws_manager.broadcast_admin(run_id, {
                        "type": "mcts_decision",
                        "data": d_dict,
                        "sim_time": snapshot.get("sim_time"),
                    })
                    last_decision_count += 1
            # Also send driver updates
            if state.ev and state.ev.status != EVStatus.IDLE:
                await self._send_driver_update(run_id, state)

        sim.set_broadcast_callback(broadcast)
        task = asyncio.create_task(sim.run_realtime())
        self._tasks[run_id] = task

    def start_sync(self, run_id: str) -> None:
        """Run simulation to completion synchronously."""
        sim = self._get_sim(run_id)
        sim.run_to_completion()

    def pause(self, run_id: str) -> None:
        sim = self._get_sim(run_id)
        sim.clock.pause()

    def resume(self, run_id: str) -> None:
        sim = self._get_sim(run_id)
        sim.clock.resume()

    def stop(self, run_id: str) -> None:
        sim = self._get_sim(run_id)
        sim.stop()
        task = self._tasks.pop(run_id, None)
        if task and not task.done():
            task.cancel()

    def reset(self, run_id: str) -> None:
        self.stop(run_id)
        self._simulators.pop(run_id, None)
        self._states.pop(run_id, None)
        self._run_configs.pop(run_id, None)

    def step(self, run_id: str) -> dict | None:
        """Advance one event. Returns event data or None."""
        sim = self._get_sim(run_id)
        event = sim.step()
        if event is None:
            return None
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "sim_time": event.scheduled_time,
            "payload": event.payload,
        }

    def set_speed(self, run_id: str, speed: float) -> None:
        sim = self._get_sim(run_id)
        sim.clock.set_speed(speed)

    def dispatch_ev(self, run_id: str, ev_id: str, vehicle_type: str,
                    corridor_id: str, max_speed_kmph: float,
                    start_intersection: str | None = None,
                    end_intersection: str | None = None) -> None:
        sim = self._get_sim(run_id)
        sim.dispatch_ev(ev_id, vehicle_type, corridor_id,
                        max_speed_kmph, sim.sim_time,
                        start_intersection, end_intersection)

    def get_state(self, run_id: str) -> dict:
        sim = self._get_sim(run_id)
        state = self._states[run_id]
        config = self._run_configs.get(run_id, {})
        snapshot = state.get_state_snapshot(sim.sim_time)
        return {
            "run_id": run_id,
            "status": "running" if run_id in self._tasks else "initialized",
            "sim_time": sim.sim_time,
            "wall_clock_elapsed": sim.clock.wall_clock_elapsed(),
            "controller_type": config.get("controller_type", "unknown"),
            "corridor_id": config.get("corridor_id", ""),
            "intersections": snapshot["intersections"],
            "ev": snapshot.get("ev"),
            "metrics": state.metrics_history[-1] if state.metrics_history else {},
        }

    def get_metrics(self, run_id: str) -> list[dict]:
        state = self._states.get(run_id)
        if state is None:
            return []
        return state.metrics_history

    def get_event_history(self, run_id: str, limit: int = 500) -> list[dict]:
        state = self._states.get(run_id)
        if state is None:
            return []
        return state.event_log[-limit:]

    def get_ev_status(self, run_id: str) -> dict | None:
        state = self._states.get(run_id)
        if state is None or state.ev is None:
            return None
        ev = state.ev
        from backend.app.simulation.ev_movement import compute_ev_progress, compute_ev_eta
        return {
            "ev_id": ev.ev_id,
            "status": ev.status.value,
            "vehicle_type": ev.vehicle_type,
            "corridor_id": ev.corridor_id,
            "current_link_index": ev.current_link_index,
            "position_on_link": ev.position_on_link,
            "speed_kmph": ev.speed_kmph,
            "total_delay": ev.total_delay_at_signals,
            "intersections_cleared": ev.intersections_cleared,
            "intersections_waited": ev.intersections_waited,
            "progress_pct": compute_ev_progress(ev, state.ev_corridor or state.corridor),
            "eta_s": compute_ev_eta(ev, state.ev_corridor or state.corridor, self._get_sim(run_id).sim_time),
            "waiting_at": ev.waiting_at_intersection,
        }

    def get_mcts_decisions(self, run_id: str) -> list[dict]:
        state = self._states.get(run_id)
        if state is None or state.controller is None:
            return []
        if not hasattr(state.controller, 'decision_history'):
            return []
        results = []
        for i, d in enumerate(state.controller.decision_history):
            d_dict = d.to_dict()
            d_dict["decision_id"] = f"mcts_{i}"
            d_dict.setdefault("sim_time", 0)
            results.append(d_dict)
        return results

    def list_runs(self) -> list[dict]:
        runs = []
        for run_id, config in self._run_configs.items():
            sim = self._simulators.get(run_id)
            runs.append({
                "run_id": run_id,
                "name": config.get("name", ""),
                "controller_type": config.get("controller_type", ""),
                "status": "running" if run_id in self._tasks else "initialized",
                "sim_time": sim.sim_time if sim else 0,
            })
        return runs

    async def _send_driver_update(self, run_id: str, state: SimulationState) -> None:
        ev = state.ev
        if ev is None:
            return

        sim = self._simulators.get(run_id)
        if sim is None:
            return

        from backend.app.simulation.ev_movement import compute_ev_progress, compute_ev_eta

        # Determine instruction
        instruction = "PROCEED"
        next_intersection = None
        next_signal = None

        if ev.waiting_at_intersection:
            instruction = "STOP"
            next_intersection = ev.waiting_at_intersection
            fsm = state.signal_fsms.get(ev.waiting_at_intersection)
            if fsm:
                next_signal = fsm.state.current_state.value
        elif ev.status == EVStatus.EN_ROUTE and ev.current_link_index < len(state.corridor.links):
            link = state.corridor.links[ev.current_link_index]
            next_intersection = link.to_intersection
            fsm = state.signal_fsms.get(link.to_intersection)
            if fsm:
                next_signal = fsm.state.current_state.value
                if not fsm.is_green_for_movement(link.ev_approach_movement):
                    instruction = "SLOW_DOWN"

        await ws_manager.send_driver(run_id, ev.ev_id, {
            "type": "instruction",
            "data": {
                "instruction": instruction,
                "next_intersection": next_intersection,
                "next_signal_state": next_signal,
                "progress_pct": compute_ev_progress(ev, state.corridor),
                "eta_s": compute_ev_eta(ev, state.corridor, sim.sim_time),
                "ev_status": ev.status.value,
            },
            "sim_time": sim.sim_time,
        })

    def _get_sim(self, run_id: str) -> EventDrivenSimulator:
        sim = self._simulators.get(run_id)
        if sim is None:
            raise ValueError(f"Simulation {run_id} not found")
        return sim


simulation_service = SimulationService()
