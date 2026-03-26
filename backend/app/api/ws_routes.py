"""WebSocket routes for admin and driver dashboards."""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.api.ws_manager import ws_manager
from backend.app.services.simulation_service import simulation_service

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/admin/{simulation_id}")
async def admin_websocket(websocket: WebSocket, simulation_id: str):
    await ws_manager.connect_admin(websocket, simulation_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")

                if action == "dispatch_ev":
                    simulation_service.dispatch_ev(
                        simulation_id,
                        msg.get("ev_id", "AMB_01"),
                        msg.get("vehicle_type", "ambulance"),
                        msg.get("corridor_id", "CORR_01"),
                        msg.get("max_speed_kmph", 60.0),
                    )
                    await websocket.send_text(json.dumps({
                        "type": "ack", "action": "dispatch_ev", "status": "ok"
                    }))

                elif action == "set_sim_speed":
                    simulation_service.set_speed(
                        simulation_id, msg.get("speed", 1.0)
                    )
                    await websocket.send_text(json.dumps({
                        "type": "ack", "action": "set_sim_speed",
                        "speed": msg.get("speed", 1.0)
                    }))

                elif action == "pause":
                    simulation_service.pause(simulation_id)
                    await websocket.send_text(json.dumps({
                        "type": "ack", "action": "pause"
                    }))

                elif action == "resume":
                    simulation_service.resume(simulation_id)
                    await websocket.send_text(json.dumps({
                        "type": "ack", "action": "resume"
                    }))

                elif action == "stop":
                    simulation_service.stop(simulation_id)
                    await websocket.send_text(json.dumps({
                        "type": "ack", "action": "stop"
                    }))

                elif action == "override_signal":
                    state = simulation_service._states.get(simulation_id)
                    sim = simulation_service._simulators.get(simulation_id)
                    if state and sim:
                        fsm = state.signal_fsms.get(msg.get("intersection_id"))
                        if fsm:
                            events = fsm.request_phase_change(
                                msg.get("target_phase", 1),
                                sim.sim_time,
                                source="user",
                            )
                            sim.schedule_many(events)
                    await websocket.send_text(json.dumps({
                        "type": "ack", "action": "override_signal"
                    }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error", "message": f"Unknown action: {action}"
                    }))

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error", "message": "Invalid JSON"
                }))
    except WebSocketDisconnect:
        ws_manager.disconnect_admin(websocket, simulation_id)


@router.websocket("/ws/driver/{simulation_id}/{ev_id}")
async def driver_websocket(websocket: WebSocket, simulation_id: str, ev_id: str):
    await ws_manager.connect_driver(websocket, simulation_id, ev_id)
    try:
        while True:
            # Driver WS is primarily server → client, but keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect_driver(simulation_id, ev_id)
