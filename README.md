# INC — Dynamic Corridor Clearing

Blank project shell for emergency-vehicle corridor clearing.

The previous adaptive-search implementation has been removed. The current backend preserves the simulator, signal FSM, EV movement, APIs, dashboards, and fixed-time controller, while dynamic routing/control is represented by an unimplemented AI-agent placeholder.

## Current Controller Surface

- `agent` — default placeholder controller. It records dummy decisions and schedules no signal-control events.
- `fixed_time` — existing timing-plan controller retained for baseline simulations and UI compatibility.

## Key Files

- `backend/app/controllers/agent_controller.py` — main AI-agent controller placeholder.
- `backend/data/agent_default_config.json` — blank config for future agent orchestration.
- `backend/app/simulation/` — event-driven simulation, queues, signal FSM, and EV movement.
- `frontend/admin-dashboard/` — admin dashboard.
- `frontend/driver-dashboard/` — driver dashboard.

## Run

```bash
./scripts/run_backend.sh
./scripts/run_frontend.sh
```

## API Example

```bash
curl -X POST http://localhost:8000/api/simulation/init \
  -H "Content-Type: application/json" \
  -d '{"controller_type":"agent","duration_s":300,"name":"Agent Placeholder Run"}'
```
