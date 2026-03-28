"""Driver dashboard routes — /api/driver/*"""

from fastapi import APIRouter, HTTPException

from backend.app.services.simulation_service import simulation_service
from backend.app.simulation.ev_movement import compute_ev_eta, compute_ev_progress

router = APIRouter(prefix="/api/driver", tags=["driver"])


@router.get("/status/{run_id}")
async def driver_status(run_id: str):
    state = simulation_service._states.get(run_id)
    sim = simulation_service._simulators.get(run_id)
    if state is None or sim is None:
        raise HTTPException(404, "Simulation not found")

    ev = state.ev
    if ev is None:
        return {"status": "no_ev", "instruction": "STANDBY"}

    # Determine instruction
    instruction = "PROCEED"
    next_intersection = None
    next_signal_state = None
    time_to_green = None

    ev_corr = state.ev_corridor or state.corridor
    if ev.waiting_at_intersection:
        instruction = "STOP"
        next_intersection = ev.waiting_at_intersection
        fsm = state.signal_fsms.get(ev.waiting_at_intersection)
        if fsm:
            next_signal_state = fsm.state.current_state.value
            time_to_green = fsm.worst_case_transition_time(sim.sim_time)
    elif ev.current_link_index < len(ev_corr.links):
        link = ev_corr.links[ev.current_link_index]
        next_intersection = link.to_intersection
        fsm = state.signal_fsms.get(link.to_intersection)
        if fsm:
            next_signal_state = fsm.state.current_state.value
            if not fsm.is_green_for_movement(link.ev_approach_movement):
                instruction = "SLOW_DOWN"
                time_to_green = fsm.worst_case_transition_time(sim.sim_time)

    directions = None
    if ev.current_link_index < len(ev_corr.links):
        link = ev_corr.links[ev.current_link_index]
        dist_remaining = max(0, link.length_meters - ev.position_on_link)
        total_remaining = dist_remaining
        for i in range(ev.current_link_index + 1, len(ev_corr.links)):
            total_remaining += ev_corr.links[i].length_meters
            
        ix_name = link.to_intersection
        ix_config = state.intersections.get(link.to_intersection)
        if ix_config:
            ix_name = ix_config.name
            
        directions = {
            "current_link": f"{link.from_intersection} → {link.to_intersection}",
            "distance_remaining_m": round(dist_remaining, 0),
            "next_intersection_name": ix_name,
            "total_distance_remaining_m": round(total_remaining, 0),
            "heading": "Straight ahead",
        }

    return {
        "ev_id": ev.ev_id,
        "status": ev.status.value,
        "instruction": instruction,
        "next_intersection": next_intersection,
        "next_signal_state": next_signal_state,
        "time_to_green_s": round(time_to_green, 1) if time_to_green else None,
        "eta_destination_s": compute_ev_eta(ev, ev_corr, sim.sim_time),
        "progress_pct": round(compute_ev_progress(ev, ev_corr), 1),
        "directions": directions,
        "start_node": ev_corr.intersection_ids[0] if ev_corr.intersection_ids else None,
        "destination_node": ev_corr.intersection_ids[-1] if ev_corr.intersection_ids else None,
    }


@router.get("/route/{run_id}")
async def driver_route(run_id: str):
    state = simulation_service._states.get(run_id)
    if state is None:
        raise HTTPException(404, "Simulation not found")

    ev_corr = state.ev_corridor or state.corridor
    corridor = ev_corr
    route_info = []
    for i, link in enumerate(corridor.links):
        ix_id = link.to_intersection
        fsm = state.signal_fsms.get(ix_id)
        ix_config = state.intersections.get(ix_id)

        route_info.append({
            "index": i,
            "from": link.from_intersection,
            "to": link.to_intersection,
            "distance_m": link.length_meters,
            "intersection_name": ix_config.name if ix_config else ix_id,
            "signal_state": fsm.state.current_state.value if fsm else "UNKNOWN",
            "signal_phase": fsm.state.current_phase if fsm else None,
        })

    return {
        "corridor_id": corridor.corridor_id,
        "start_node": corridor.intersection_ids[0] if corridor.intersection_ids else None,
        "destination_node": corridor.intersection_ids[-1] if corridor.intersection_ids else None,
        "route": route_info
    }


@router.get("/clearance/{run_id}")
async def driver_clearance(run_id: str):
    state = simulation_service._states.get(run_id)
    sim = simulation_service._simulators.get(run_id)
    if state is None or sim is None:
        raise HTTPException(404, "Simulation not found")

    ev = state.ev
    ev_corr = state.ev_corridor or state.corridor
    clearance = []
    for link in ev_corr.links:
        ix_id = link.to_intersection
        fsm = state.signal_fsms.get(ix_id)

        is_green = False
        if fsm:
            is_green = fsm.is_green_for_movement(link.ev_approach_movement)

        ev_cleared = False
        ev_waiting = False
        if ev:
            link_idx = ev_corr.links.index(link)
            ev_cleared = ev.current_link_index > link_idx
            ev_waiting = (ev.waiting_at_intersection == ix_id)

        clearance.append({
            "intersection_id": ix_id,
            "signal_green": is_green,
            "ev_cleared": ev_cleared,
            "ev_waiting": ev_waiting,
        })

    return clearance


@router.get("/eta/{run_id}")
async def driver_eta(run_id: str):
    state = simulation_service._states.get(run_id)
    sim = simulation_service._simulators.get(run_id)
    if state is None or sim is None:
        raise HTTPException(404, "Simulation not found")

    ev = state.ev
    if ev is None:
        return {"eta_s": None, "free_flow_eta_s": None}

    corridor = state.ev_corridor or state.corridor
    free_flow = corridor.free_flow_travel_time_s()
    current_eta = compute_ev_eta(ev, corridor, sim.sim_time)

    return {
        "eta_s": round(current_eta, 1) if current_eta else None,
        "free_flow_eta_s": round(free_flow, 1),
        "progress_pct": round(compute_ev_progress(ev, corridor), 1),
    }


@router.get("/live-corridor/{run_id}")
async def live_corridor(run_id: str):
    state = simulation_service._states.get(run_id)
    sim = simulation_service._simulators.get(run_id)
    if state is None or sim is None:
        raise HTTPException(404, "Simulation not found")

    ev_corr = state.ev_corridor or state.corridor
    intersections = []
    for iid in ev_corr.intersection_ids:
        fsm = state.signal_fsms.get(iid)
        iq = state.intersection_queues.get(iid)
        ix = state.intersections.get(iid)

        intersections.append({
            "intersection_id": iid,
            "name": ix.name if ix else iid,
            "signal_state": fsm.state.current_state.value if fsm else "UNKNOWN",
            "green_movements": list(fsm.green_movements()) if fsm else [],
            "total_queue": round(iq.total_queue(sim.sim_time), 1) if iq else 0,
        })

    ev_data = None
    if state.ev:
        ev_data = {
            "position_link_index": state.ev.current_link_index,
            "position_on_link": state.ev.position_on_link,
            "status": state.ev.status.value,
        }

    return {
        "start_node": ev_corr.intersection_ids[0] if ev_corr.intersection_ids else None,
        "destination_node": ev_corr.intersection_ids[-1] if ev_corr.intersection_ids else None,
        "intersections": intersections, 
        "ev": ev_data
    }


from backend.app.services.analytics_service import analytics_service

@router.get("/arrival-comparison/{run_id}")
async def arrival_comparison(run_id: str):
    state = simulation_service._states.get(run_id)
    config = simulation_service._run_configs.get(run_id)
    
    if not state or not config:
        raise HTTPException(404, "Simulation not found")
        
    ev = state.ev
    if not ev or ev.status.value != "arrived":
        raise HTTPException(400, "EV has not arrived yet")
        
    start_ix = ev.route[0] if ev.route else None
    end_ix = ev.route[-1] if ev.route else None
    
    current_ctrl = config.get("controller_type", "mcts")
    baseline_ctrl = "fixed_time" if current_ctrl == "mcts" else "mcts"
    
    base_id = simulation_service.init_simulation(
        name=f"Comparison for {config.get('name', run_id)}",
        corridor_id=config.get("corridor_id", "CORR_01"),
        controller_type=baseline_ctrl,
        duration_s=config.get("duration_s", 3600.0),
        sim_speed=1.0,
        random_seed=config.get("random_seed"),
        traffic_profile=config.get("traffic_profile", "default"),
        start_time_of_day=config.get("start_time_of_day", "08:00")
    )
    
    simulation_service.dispatch_ev(
        run_id=base_id,
        ev_id=ev.ev_id,
        vehicle_type=ev.vehicle_type,
        corridor_id=ev.corridor_id,
        max_speed_kmph=ev.max_speed_kmph,
        start_intersection=start_ix,
        end_intersection=end_ix,
        dispatch_time=ev.dispatch_time
    )
    
    simulation_service.start_sync(base_id)
    if current_ctrl == "mcts":
        comparison = analytics_service.compare_runs(run_id, base_id)
    else:
        # If running fixed time, we compare MCTS against the current!
        # compare_runs(mcts_run_id, baseline_run_id)
        comparison = analytics_service.compare_runs(base_id, run_id)
    simulation_service.reset(base_id)
    
    return comparison
