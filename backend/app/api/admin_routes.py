"""Admin routes — /api/admin/*"""

from fastapi import APIRouter, HTTPException

from backend.app.schemas.requests import BlockageRequest, SignalOverrideRequest
from backend.app.models.events import EventType, SimEvent
from backend.app.services.simulation_service import simulation_service
from backend.app.utils.helpers import gen_id

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/blockage/{run_id}")
async def create_blockage(run_id: str, req: BlockageRequest):
    try:
        sim = simulation_service._simulators.get(run_id)
        if sim is None:
            raise HTTPException(404, "Simulation not found")

        event = SimEvent(
            event_id=gen_id("evt"),
            event_type=EventType.BLOCKAGE_START,
            scheduled_time=sim.sim_time,
            payload={
                "from_intersection": req.from_intersection,
                "to_intersection": req.to_intersection,
                "capacity_reduction_pct": req.capacity_reduction_pct,
            },
            source="user",
        )
        sim.schedule(event)

        if req.duration_s is not None:
            end_event = SimEvent(
                event_id=gen_id("evt"),
                event_type=EventType.BLOCKAGE_END,
                scheduled_time=sim.sim_time + req.duration_s,
                payload={
                    "from_intersection": req.from_intersection,
                    "to_intersection": req.to_intersection,
                },
                source="user",
            )
            sim.schedule(end_event)

        return {"status": "blockage_created", "at_time": sim.sim_time}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/unblock/{run_id}")
async def remove_blockage(run_id: str, from_intersection: str,
                          to_intersection: str):
    sim = simulation_service._simulators.get(run_id)
    if sim is None:
        raise HTTPException(404, "Simulation not found")

    event = SimEvent(
        event_id=gen_id("evt"),
        event_type=EventType.BLOCKAGE_END,
        scheduled_time=sim.sim_time,
        payload={
            "from_intersection": from_intersection,
            "to_intersection": to_intersection,
        },
        source="user",
    )
    sim.schedule(event)
    return {"status": "unblocked"}


@router.post("/override-signal/{run_id}")
async def override_signal(run_id: str, req: SignalOverrideRequest):
    state = simulation_service._states.get(run_id)
    sim = simulation_service._simulators.get(run_id)
    if state is None or sim is None:
        raise HTTPException(404, "Simulation not found")

    fsm = state.signal_fsms.get(req.intersection_id)
    if fsm is None:
        raise HTTPException(404, f"Intersection {req.intersection_id} not found")

    events = fsm.request_phase_change(req.target_phase, sim.sim_time, source="user")
    sim.schedule_many(events)

    return {
        "status": "override_requested",
        "intersection_id": req.intersection_id,
        "target_phase": req.target_phase,
    }


@router.get("/control-room/{run_id}")
async def control_room(run_id: str):
    try:
        state_data = simulation_service.get_state(run_id)
        ev_status = simulation_service.get_ev_status(run_id)
        decisions = simulation_service.get_mcts_decisions(run_id)

        blockages = simulation_service._states.get(run_id)
        active_blockages = []
        if blockages:
            active_blockages = [
                {"from": k[0], "to": k[1], "factor": v}
                for k, v in blockages.blockage_factors.items()
            ]

        return {
            "state": state_data,
            "ev": ev_status,
            "recent_decisions": decisions[-10:] if decisions else [],
            "active_blockages": active_blockages,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/alerts/{run_id}")
async def get_alerts(run_id: str):
    state = simulation_service._states.get(run_id)
    sim = simulation_service._simulators.get(run_id)
    if state is None or sim is None:
        raise HTTPException(404, "Simulation not found")

    alerts = []

    # Check for high queues
    for iid, iq in state.intersection_queues.items():
        mq = iq.max_queue(sim.sim_time)
        if mq > 40:
            alerts.append({
                "type": "high_queue",
                "severity": "warning" if mq < 60 else "critical",
                "intersection_id": iid,
                "queue_length": round(mq, 1),
            })

    # Check EV delays
    if state.ev and state.ev.total_delay_at_signals > 30:
        alerts.append({
            "type": "ev_delay",
            "severity": "warning",
            "ev_id": state.ev.ev_id,
            "total_delay": round(state.ev.total_delay_at_signals, 1),
        })

    # Check blockages
    for (from_id, to_id), factor in state.blockage_factors.items():
        alerts.append({
            "type": "blockage",
            "severity": "warning",
            "from": from_id,
            "to": to_id,
            "capacity_factor": factor,
        })

    return alerts
