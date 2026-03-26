"""MCTS Controller — wraps MCTS search and applies decisions to simulation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from backend.app.mcts.actions import Action, ActionType
from backend.app.mcts.reward import RewardWeights
from backend.app.mcts.search import MCTSConfig, MCTSSearch, MCTSSearchResult
from backend.app.mcts.state import MCTSState
from backend.app.models.events import SimEvent
from backend.app.utils.helpers import gen_id

if TYPE_CHECKING:
    from backend.app.simulation.engine import SimulationState


class MCTSController:
    """Signal controller that uses RH-MCTS for corridor-wide optimization."""

    def __init__(self, intersection_configs: list[dict],
                 intersection_ids: list[str],
                 ev_approach_movements: dict[str, str],
                 mcts_config: MCTSConfig | None = None):
        """
        Args:
            intersection_configs: list of intersection config dicts
            intersection_ids: ordered corridor intersection IDs
            ev_approach_movements: intersection_id -> movement_id EV uses
            mcts_config: MCTS hyperparameters
        """
        self.intersection_configs = intersection_configs
        self.intersection_ids = intersection_ids
        self.ev_approach_movements = ev_approach_movements
        self.config = mcts_config or MCTSConfig()
        self.decision_history: list[MCTSSearchResult] = []

    def decide(self, state: SimulationState,
               sim_time: float) -> list[SimEvent]:
        """Run MCTS and apply the best actions."""
        # Build EV phase mapping
        ev_phases = self._build_ev_phases(state)

        # Build MCTS state from simulation
        mcts_state = MCTSState.from_simulation(state, sim_time)

        # Run search
        search = MCTSSearch(
            config=self.config,
            intersection_configs=self.intersection_configs,
            intersection_ids=self.intersection_ids,
            ev_phases=ev_phases,
        )
        result = search.search(mcts_state)
        self.decision_history.append(result)

        # Apply actions to simulation FSMs
        events: list[SimEvent] = []
        for iid, action in result.actions.items():
            fsm = state.signal_fsms.get(iid)
            if fsm is None:
                continue

            new_events = self._apply_action(fsm, action, sim_time)
            events.extend(new_events)

        return events

    def _build_ev_phases(self, state: SimulationState) -> dict[str, int]:
        """Map intersection_id -> phase that serves EV approach."""
        ev_phases: dict[str, int] = {}

        if state.ev is None or state.ev.status.value in ("idle", "arrived"):
            return ev_phases

        for iid in self.intersection_ids:
            movement_id = self.ev_approach_movements.get(iid)
            if movement_id is None:
                continue
            ix = state.intersections.get(iid)
            if ix is None:
                continue
            phase = ix.get_phase_for_movement(movement_id)
            if phase:
                ev_phases[iid] = phase.phase_id

        return ev_phases

    def _apply_action(self, fsm, action: Action,
                      sim_time: float) -> list[SimEvent]:
        """Apply a single action to an FSM."""
        if action.action_type == ActionType.HOLD:
            return []
        elif action.action_type == ActionType.TERMINATE:
            return fsm.request_terminate(sim_time, source="mcts")
        elif action.action_type == ActionType.SKIP_TO_EV_PHASE:
            if action.target_phase is not None:
                return fsm.request_phase_change(
                    action.target_phase, sim_time, source="mcts"
                )
            return []
        elif action.action_type in (ActionType.EXTEND_5, ActionType.EXTEND_10,
                                     ActionType.EXTEND_15):
            # Extensions are handled by NOT terminating
            return []
        return []

    @staticmethod
    def from_config(intersections: list, corridor, mcts_json: dict | None = None):
        """Build MCTSController from intersection and corridor models."""
        from backend.app.config import settings

        int_configs = []
        int_ids = list(corridor.intersection_ids)

        for ix in intersections:
            cfg = {
                "intersection_id": ix.intersection_id,
                "phases": [p.model_dump() for p in ix.phases],
                "rings": [r.model_dump() for r in ix.rings],
            }
            int_configs.append(cfg)

        ev_movements = {}
        for link in corridor.links:
            ev_movements[link.to_intersection] = link.ev_approach_movement

        mcts_config = MCTSConfig(
            iterations=settings.mcts_iterations,
            horizon_length_s=settings.mcts_horizon_s,
            horizon_step_s=settings.mcts_horizon_step_s,
            exploration_constant=settings.mcts_exploration_constant,
            reward_weights=RewardWeights(
                w_ev=settings.w_ev,
                w_queue=settings.w_queue,
                w_throughput=settings.w_throughput,
                w_stability=settings.w_stability,
                w_max_queue=settings.w_max_queue,
                max_queue_threshold=settings.max_queue_threshold,
            ),
        )

        if mcts_json:
            mcts_cfg = mcts_json.get("mcts", {})
            mcts_config.iterations = mcts_cfg.get("iterations", mcts_config.iterations)
            mcts_config.horizon_length_s = mcts_cfg.get("horizon_length_s",
                                                         mcts_config.horizon_length_s)
            mcts_config.horizon_step_s = mcts_cfg.get("horizon_step_s",
                                                       mcts_config.horizon_step_s)
            mcts_config.exploration_constant = mcts_cfg.get("exploration_constant",
                                                             mcts_config.exploration_constant)
            rw = mcts_json.get("reward_weights", {})
            if rw:
                mcts_config.reward_weights = RewardWeights.from_config(mcts_json)

        return MCTSController(int_configs, int_ids, ev_movements, mcts_config)
