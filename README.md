# INC — Dynamic Corridor Clearing with RH-MCTS

Real-time traffic signal optimization for emergency vehicle corridor clearance using Rolling Horizon Monte Carlo Tree Search. Built for the Pune corridor (5 intersections, 4 links).

## Overview

INC simulates a traffic corridor and dynamically optimizes signal timing to clear a path for emergency vehicles while minimizing disruption to general traffic. The system compares MCTS-based adaptive control against fixed-time baseline to demonstrate improvement in EV delay, queue management, and throughput.

**Key capabilities:**
- Event-driven traffic simulation with realistic signal FSM (min green, amber, all-red constraints)
- MCTS decision engine with configurable reward weights (EV delay, queue, throughput, stability)
- Real-time admin dashboard with corridor visualization (abstract graph + Leaflet map)
- Driver dashboard showing EV navigation instructions
- MCTS vs baseline comparison analytics

## Architecture

```
backend/                       frontend/
  app/                           shared-ui/        (theme, SignalIcon, QueueBar)
    models/       (data models)  admin-dashboard/   (React + Vite, port 3000)
    simulation/   (event engine) driver-dashboard/  (React + Vite, port 3001)
    mcts/         (MCTS search)
    controllers/  (MCTS + fixed-time)
    services/     (orchestration)
    api/          (REST + WebSocket)
    persistence/  (SQLite)
  data/           (JSON configs)
  tests/          (95 tests)
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+

## Backend Setup

```bash
pip install fastapi uvicorn pydantic aiosqlite httpx pytest pytest-asyncio
./scripts/run_backend.sh
# Server starts at http://localhost:8000
```

## Frontend Setup

```bash
./scripts/run_frontend.sh
# Admin:  http://localhost:3000
# Driver: http://localhost:3001?sim_id=RUN_ID&ev_id=AMB_01
```

## RH-MCTS Algorithm

The Rolling Horizon MCTS operates on a 60-second horizon with 15-second steps:

1. **State Snapshot**: Captures signal phases, queue lengths, EV position from live simulation
2. **Action Space**: HOLD, TERMINATE, SKIP_TO_EV_PHASE, EXTEND_5/10/15 per intersection
3. **Fast-Forward**: Lightweight analytical simulator (no event queue) for rollouts
4. **Reward Function**: `-W_EV*ev_delay - W_QUEUE*total_queue + W_THROUGHPUT*discharged - W_STABILITY*phase_changes - W_MAX_QUEUE*overflow`
5. **Rollout Policy**: Heuristic — EV-priority (skip to EV phase) + Longest Queue First

Default weights: W_EV=10, W_QUEUE=1, W_THROUGHPUT=0.5, W_STABILITY=0.3, W_MAX_QUEUE=2.

## Traffic Model

- **Queue Model**: Lazy evaluation — queues computed on demand, not every tick
- **BPR Congestion**: `speed_factor = 1 / (1 + 0.15 * (V/C)^4)`
- **Signal FSM**: GREEN -> AMBER (3s, non-interruptible) -> ALL_RED (2s, non-interruptible) -> GREEN
- **Traffic Profiles**: Piecewise-linear arrival rates with peak/off-peak patterns

## Pune Corridor Configuration

5 intersections (INT_01 to INT_05), 4 links (380-520m each), 35-40 km/h free flow, 3600 vph capacity. EV approach via SBT (southbound through) movement.

Editable JSON configs in `backend/data/`:
- `pune_default_intersections.json` — intersection geometry and phases
- `pune_default_corridor.json` — link properties
- `pune_default_timing_plans.json` — fixed-time splits and offsets
- `pune_traffic_profiles.json` — time-of-day demand profiles
- `mcts_default_config.json` — MCTS hyperparameters and reward weights

## Admin Dashboard

Real-time control room at `http://localhost:3000`:
- **Corridor Visualization**: Abstract SVG graph or Leaflet map (toggleable)
- **Signal Indicators**: Per-intersection phase state with green movement chips
- **Queue Charts**: Recharts line chart showing queue evolution
- **EV Tracker**: Progress bar with intersection waypoints
- **MCTS Decision Log**: Scrollable table of decisions with reward/actions
- **KPI Panel**: Total queue, max queue, throughput, EV progress sparklines
- **Controls**: Init/start/pause/reset, speed selector, EV dispatch, blockage injection

Additional pages: Configuration editor, MCTS vs baseline comparison, simulation history.

## Driver Dashboard

EV navigation display at `http://localhost:3001?sim_id=RUN_ID`:
- **Instruction Banner**: Full-width colored banner (PROCEED/STOP/SLOW_DOWN)
- **Signal Ahead**: Large traffic light with countdown to green
- **Route Progress**: Waypoint bar with EV position
- **ETA Display**: Countdown vs free-flow comparison
- **Corridor Status**: Per-intersection signal/queue/clearance list

## Baseline Comparison

Run automated comparison:

```bash
# Via CLI script
python3 scripts/run_comparison.py

# Via admin dashboard
# Navigate to Compare page, click "Auto Run & Compare"
```

Both methods initialize MCTS and fixed-time runs with identical parameters, dispatch an EV, run to completion, and display improvement percentages.

## API Reference

~50 REST endpoints + 2 WebSocket endpoints:

| Group | Prefix | Key Endpoints |
|-------|--------|---------------|
| Simulation | `/api/simulation/` | init, start, pause, resume, reset, step, run, state, metrics, list |
| EV | `/api/ev/` | dispatch, status, clearance-log, eta |
| Control | `/api/control/` | decide, set-baseline, set-mcts, decision-log |
| Admin | `/api/admin/` | blockage, unblock, override-signal, control-room, alerts |
| Driver | `/api/driver/` | status, route, clearance, eta, live-corridor |
| Analytics | `/api/analytics/` | queue, delay, throughput, ev-journey, ev-waterfall, compare-baseline, plots |
| Config | `/api/config` | get, load, reset, intersections, corridors |
| WebSocket | `/ws/admin/{sim_id}` | Bidirectional: state updates, commands |
| WebSocket | `/ws/driver/{sim_id}/{ev_id}` | Server-to-client: instructions |

## Testing

```bash
# Run all 95 tests
python3 -m pytest backend/tests/ -q

# Run specific test files
python3 -m pytest backend/tests/test_mcts.py -v
python3 -m pytest backend/tests/test_comparison_integration.py -v
```

Test coverage: signal FSM (16), queue model (9), EV movement (15), simulation engine (9), MCTS (15), reward (8), fixed-time (5), API endpoints (14), integration (4).

## Project Structure

```
backend/
  app/
    models/          intersection, corridor, signal_controller, ev, events, metrics
    simulation/      clock, queue_model, signal_fsm, ev_movement, traffic_profile, event_handlers, engine
    mcts/            state, actions, fast_forward, reward, rollout_policy, tree, search
    controllers/     fixed_time, mcts_controller, preemption
    services/        config, simulation, ev, analytics, export
    api/             config, simulation, control, ev, admin, driver, analytics, ws routes + manager
    persistence/     migrations, repositories
    schemas/         requests, responses, ws_messages
    utils/           helpers
  data/              6 JSON config files
  tests/             9 test files, 95 tests
frontend/
  shared-ui/         theme, SignalIcon, QueueBar
  admin-dashboard/   React app (pages: Simulation, Config, Compare, History)
  driver-dashboard/  React app (single-page EV navigation)
scripts/
  run_backend.sh     Start backend server
  run_frontend.sh    Start both frontend dev servers
  run_comparison.py  CLI comparison tool
```
