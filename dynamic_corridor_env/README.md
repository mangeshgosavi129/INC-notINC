# Dynamic Corridor Environment

OpenEnv environment for emergency vehicle green-corridor learning with SUMO.

The environment models a 5-intersection Pune corridor slice. A central RL agent observes local traffic state for each intersection plus global ambulance progress, then submits a bundle of phase choices.

## API

```python
from dynamic_corridor_env import DynamicCorridorAction, DynamicCorridorEnv

env = DynamicCorridorEnv(base_url="http://localhost:8000")
result = env.reset()

action = DynamicCorridorAction(
    phase_by_intersection={
        ix.intersection_id: ix.ev_target_phase or ix.current_phase
        for ix in result.observation.intersections
    }
)
result = env.step(action)
```

Route-choice actions can also select the ambulance's next directed road edge:

```python
action = DynamicCorridorAction(next_edge_id="WEST_TO_INT_01")
result = env.step(action)
```

`reset` accepts optional `source_id` and `destination_id` fields through the HTTP API. They default to `WEST` and `EAST`. Each reset assigns seeded random road weights for the episode and exposes them in `observation.route_choice`.

## Action

`DynamicCorridorAction.phase_by_intersection` maps intersection IDs to SUMO green-phase indices:

```json
{
  "INT_01": 0,
  "INT_02": 2,
  "INT_03": 0
}
```

Missing intersections hold their current phase. Invalid phase IDs are ignored and penalized.

`DynamicCorridorAction.next_edge_id` selects the ambulance's next candidate road. Invalid, unreachable, or non-candidate edges are penalized. Backtracking and moves away from the destination receive additional route-choice penalties.

## Observation

Each observation contains:

- `intersections`: current phase, valid phases, queue length, vehicle count, mean speed, EV route flag, and EV target phase.
- `ev`: route, next intersection, progress, waiting time, travel time, and arrival status.
- `route_choice`: source, destination, current node/edge, previous edge, active route, seeded road weights, and candidate next-road options.
- `global_metrics`: total queue, max queue, throughput, mean speed, and phase changes.

## Reward

The v1 reward is EV-first but still penalizes normal traffic disruption:

```text
raw_reward =
  20  * ev_progress_delta
  - 100 * ev_wait_time_delta
  - 1   * total_queue
  - 2   * max(0, max_queue - 50)
  - 0.1 * phase_changes
  + 0.5 * throughput_delta
  - 5   * invalid_actions
```

Terminal rewards:

- Ambulance arrives: `+ max(0, 500 - ev_travel_time)`
- Timeout: `-500`

The environment returns the final reward normalized to `[-10, 10]` after all step and terminal terms are combined. The step feedback includes both `raw_reward` and `normalized_reward` for debugging.

The main evaluation baseline metric is EV travel-time improvement over fixed-time, greedy preemption, or the existing RHMCTS controller:

```text
improvement = (baseline_ev_travel_time - agent_ev_travel_time) / baseline_ev_travel_time
```

## Running

```bash
cd OpenEnv/envs/dynamic_corridor_env
uv sync
uv run server --port 8000
```

The first reset generates `nets/pune-5/pune-5.net.xml` from the bundled SUMO node and edge files if it is missing.

## Docker

```bash
cd OpenEnv
docker build -f envs/dynamic_corridor_env/server/Dockerfile -t dynamic-corridor-env:latest envs/dynamic_corridor_env
docker run -p 8000:8000 dynamic-corridor-env:latest
```

The Docker image installs SUMO from the Python `eclipse-sumo` wheel instead of Debian `apt`, then uses `traci` and `sumolib` from Python. It installs only the small `libexpat1` runtime library needed by the wheel-provided SUMO binaries.

If you want to call the API on host port `8001`, map it explicitly:

```bash
docker run -p 8001:8000 dynamic-corridor-env:latest
curl -X POST http://localhost:8001/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"pune_5_default"}'
```

## Custom Simulation UI

The environment includes a custom browser dashboard at `/viz` for step-by-step visualization of EV movement, traffic conditions, and agent signal decisions.

Visit [http://localhost:8001/viz](http://localhost:8001/viz) in your browser.

UI highlights:

- Schematic corridor rendering for 3, 4, or 5 intersections.
- EV marker, queue bars, and per-intersection phase state.
- Controls: reset, step, auto step, pause.
- Agent decision panel with chosen phase, EV target phase, and reward breakdown.
- Timeline-ready snapshot history with slider and prev/next browsing.

Notes:

- This is a custom schematic visualizer, not SUMO's native map GUI.
- If `/step` reports the episode is done, click reset before stepping again.

## Configuration

Environment variables:

| Variable | Default |
| --- | --- |
| `DYNAMIC_CORRIDOR_NET_FILE` | `nets/pune-5/pune-5.net.xml` |
| `DYNAMIC_CORRIDOR_ROUTE_FILE` | `nets/pune-5/pune-5.rou.xml` |
| `DYNAMIC_CORRIDOR_DELTA_TIME` | `5` |
| `DYNAMIC_CORRIDOR_MAX_SECONDS` | `900` |
| `DYNAMIC_CORRIDOR_SEED` | `42` |
| `SUMO_BINARY` | `sumo` |

## Local Python SUMO Install

SUMO's `traci` and `sumolib` packages are Python control libraries. To get the actual SUMO binaries from Python packaging, install `eclipse-sumo`:

```bash
uv pip install --find-links https://sumo.dlr.de/daily/wheels/ eclipse-sumo
```

The environment resolves `sumo` and `netconvert` through `sumolib.checkBinary()`.
