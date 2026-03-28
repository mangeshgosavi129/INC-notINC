"""Control routes — /api/control/* (MCTS)"""

from fastapi import APIRouter, HTTPException

from backend.app.schemas.requests import MCTSParamsUpdate
from backend.app.services.simulation_service import simulation_service

router = APIRouter(prefix="/api/control", tags=["control"])


@router.post("/decide/{run_id}")
async def force_decide(run_id: str):
    """Force an MCTS decision at the current simulation time."""
    try:
        state = simulation_service._states.get(run_id)
        sim = simulation_service._simulators.get(run_id)
        if state is None or sim is None:
            raise HTTPException(404, "Simulation not found")

        if state.controller is None:
            raise HTTPException(400, "No controller configured")

        events = state.controller.decide(state, sim.sim_time)
        sim.schedule_many(events)

        return {"status": "decided", "events_scheduled": len(events)}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/set-baseline/{run_id}")
async def set_baseline(run_id: str):
    """Switch to fixed-time baseline controller."""
    state = simulation_service._states.get(run_id)
    if state is None:
        raise HTTPException(404, "Simulation not found")

    from backend.app.controllers.fixed_time import FixedTimeController
    from backend.app.services.config_service import config_service
    state.controller = FixedTimeController.from_timing_plans_json(
        config_service.timing_plans
    )
    return {"status": "ok", "controller": "fixed_time"}


@router.post("/set-mcts/{run_id}")
async def set_mcts(run_id: str):
    """Switch to MCTS controller."""
    state = simulation_service._states.get(run_id)
    if state is None:
        raise HTTPException(404, "Simulation not found")

    from backend.app.controllers.mcts_controller import MCTSController
    from backend.app.services.config_service import config_service
    state.controller = MCTSController.from_config(
        list(state.intersections.values()),
        state.corridor,
        config_service.mcts_config,
    )
    return {"status": "ok", "controller": "mcts"}


@router.get("/decision-log/{run_id}")
async def get_decision_log(run_id: str):
    return simulation_service.get_mcts_decisions(run_id)


@router.get("/explain-last-decision/{run_id}")
async def explain_last(run_id: str):
    decisions = simulation_service.get_mcts_decisions(run_id)
    if not decisions:
        return {"message": "No decisions yet"}
    last = decisions[-1]
    return {
        "decision": last,
        "explanation": _explain(last),
    }


def _explain(decision: dict) -> str:
    actions = decision.get("actions", {})
    parts = []
    for iid, a in actions.items():
        at = a.get("action_type", "HOLD")
        if at == "HOLD":
            parts.append(f"{iid}: maintain current phase")
        elif at == "TERMINATE":
            parts.append(f"{iid}: terminate current phase → next")
        elif at == "SKIP_TO_EV_PHASE":
            parts.append(f"{iid}: preempt to EV phase {a.get('target_phase')}")
        elif at.startswith("EXTEND"):
            parts.append(f"{iid}: extend current green")
    reward = decision.get("reward", 0)
    return f"Reward={reward:.2f}. " + "; ".join(parts)
