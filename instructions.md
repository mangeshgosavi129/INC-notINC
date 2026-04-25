# INC — Agent-Based Corridor Clearing Shell

This project is now a blank implementation shell for an AI-agent-orchestrated routing system.

The simulator, dashboards, EV workflow, fixed-time controller, and configuration plumbing remain. Dynamic route and signal decisions are intentionally unimplemented in `backend/app/controllers/agent_controller.py`.

## Start

```bash
./scripts/run_backend.sh
./scripts/run_frontend.sh
```

## Initialize A Placeholder Agent Run

```bash
curl -X POST http://localhost:8000/api/simulation/init \
  -H "Content-Type: application/json" \
  -d '{"controller_type":"agent","duration_s":300,"name":"Test Run"}'
```

## Compare Against Fixed Time

```bash
curl "http://localhost:8000/api/analytics/compare-baseline?agent_run_id=AGENT_RUN&baseline_run_id=BASELINE_RUN"
```
