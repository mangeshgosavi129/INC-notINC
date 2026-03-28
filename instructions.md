# INC — Dynamic Corridor Clearing with RH-MCTS

Traffic signal optimization system that uses Monte Carlo Tree Search to clear corridors for emergency vehicles in real-time. Simulates a 5-intersection Pune corridor, compares MCTS adaptive control vs fixed-time baseline.

## Quick Start

```bash
# 1. Install backend dependencies
pip install fastapi uvicorn pydantic aiosqlite httpx pytest pytest-asyncio

# 2. Start backend (port 8000)
cd /path/to/INC
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Install frontend dependencies
cd frontend
npm install

# 4. Start admin dashboard (port 3000)
npm run dev --workspace=admin-dashboard

# 5. Start driver dashboard (port 3001) — in another terminal
npm run dev --workspace=driver-dashboard
```

## Access

- **Backend API**: http://localhost:8000/api/health
- **Admin Dashboard**: http://localhost:3000
- **Driver Dashboard**: http://localhost:3001?sim_id=YOUR_RUN_ID&ev_id=AMB_01

## Run Tests

```bash
python3 -m pytest backend/tests/ -q
```

## Run MCTS vs Baseline Comparison (CLI)

```bash
python3 scripts/run_comparison.py
```

## Key API Endpoints

```bash
# Init and run a simulation
curl -X POST http://localhost:8000/api/simulation/init \
  -H "Content-Type: application/json" \
  -d '{"controller_type":"mcts","duration_s":300,"name":"Test Run"}'

# Start it (use run_id from above)
curl -X POST http://localhost:8000/api/simulation/start/{run_id}

# Dispatch EV
curl -X POST http://localhost:8000/api/ev/dispatch/{run_id} \
  -H "Content-Type: application/json" \
  -d '{"ev_id":"AMB_01","vehicle_type":"ambulance"}'

# Get state
curl http://localhost:8000/api/simulation/state/{run_id}

# Compare two runs
curl "http://localhost:8000/api/analytics/compare-baseline?mcts_run_id=X&baseline_run_id=Y"
```
