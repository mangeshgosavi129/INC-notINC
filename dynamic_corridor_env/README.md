# Dynamic Corridor Environment

OpenEnv environment for **dynamic corridor clearing**: emergency-vehicle progress through a SUMO signalized corridor with background traffic, plus optional EV route choice.

## Topology and tasks

- Bundled network: **Pune-style grid** (`nets/pune-5/`), built from `pune-5.nod.xml` / `pune-5.edg.xml` into `pune-5.net.xml` on first use.
- Default OpenEnv task id: **`grid_4x4_default`** — **16** signalized intersections (`INT_1_1` … `INT_4_4`). See [`openenv.yaml`](openenv.yaml).

A central agent observes per-intersection traffic and global EV state, then submits one `DynamicCorridorAction` (all phases + optional `next_edge_id`).

## API

```python
from dynamic_corridor_env import DynamicCorridorAction, DynamicCorridorEnv

env = DynamicCorridorEnv(base_url="http://localhost:8000")
result = env.reset(seed=42, episode_id="eval-001", task_id="grid_4x4_default")

action = DynamicCorridorAction(
    phase_by_intersection={
        ix.intersection_id: ix.ev_target_phase or ix.current_phase
        for ix in result.observation.intersections
    }
)
result = env.step(action)
```

Route-choice actions can select the ambulance’s next directed road edge (must be a current candidate):

```python
action = DynamicCorridorAction(next_edge_id="NW_OUT_TO_INT_1_1")
result = env.step(action)
```

### Reset parameters (OpenEnv)

`reset` supports **`seed`**, **`episode_id`**, and kwargs **`task_id`**, **`source_id`**, **`destination_id`**.

- **`task_id`**: must match the built-in scenario (default **`grid_4x4_default`**).
- **`source_id` / `destination_id`**: SUMO node ids (default **`NW_OUT`** / **`SE_OUT`**).
- **`seed`**: updates the environment RNG and SUMO run seed for reproducible episodes.
- **`episode_id`**: stored in state for logging and benchmarks.

Each reset assigns **seeded random road weights** per edge; see `observation.route_choice.road_weights`.

## Action

`DynamicCorridorAction.phase_by_intersection` maps intersection IDs to SUMO green-phase indices, for example:

```json
{
  "INT_1_1": 0,
  "INT_1_2": 2,
  "INT_2_1": 0
}
```

Missing intersections keep their current phase. Invalid phase IDs are ignored and penalized (in **clearing** reward mode).

`DynamicCorridorAction.next_edge_id` selects the next edge from the current candidate set. Invalid or unreachable choices are penalized in **clearing** mode; in **route_weights** mode the step reward is `0` for an invalid route choice.

## Observation

- **`intersections`**: phase, valid phases, queues, speeds, EV approach / target phase, ETA hints.
- **`ev`**: route, progress, waiting time, travel time, arrival.
- **`route_choice`**: source/destination nodes, active route, **road weights**, candidate edges.
- **`global_metrics`**: traffic summaries **plus structured clearing metrics** (no need to parse `feedback`):
  - `reward_mode`, `invalid_action_count_episode`, `mean_corridor_queue`, `ev_travel_time_s`, `ev_clearing_success`, `episode_timeout`, `n_signalized_intersections`, etc.

`/state` returns [`DynamicCorridorState`](models.py) with the same eval-oriented fields.

## Reward modes (`DYNAMIC_CORRIDOR_REWARD_MODE`)

| Mode | Default | Scalar range | Use |
| --- | --- | --- | --- |
| **`clearing`** | yes | clipped **~[-10, 10]** | Corridor clearing: EV progress, wait, queues, throughput, invalid actions, route penalties; terminal bonus/penalty on arrival / timeout. |
| **`route_weights`** | no | **[0, 1]** | Auxiliary / curriculum: reward from **mean seeded edge weight** on the active route only; invalid route step → `0`. |

Set `DYNAMIC_CORRIDOR_REWARD_MODE=route_weights` for weight-only training; omit or set `clearing` for the main clearing objective.

Baseline evaluation often uses **EV travel-time improvement**:

```text
improvement = (baseline_ev_travel_time - agent_ev_travel_time) / baseline_ev_travel_time
```

Use `global_metrics.ev_travel_time_s` and `ev_clearing_success` for rubrics without parsing `feedback`.

## OpenEnv rubrics (benchmark scores)

The environment implements the OpenEnv **`Rubric`** API: optional rubrics run **after** each `step`, using the same `action` and post-step `DynamicCorridorObservation`. They do **not** replace `observation.reward` (that remains the environment reward from `DYNAMIC_CORRIDOR_REWARD_MODE`).

- **`observation.metadata["rubric_score"]`** — scalar from `rubric(action, observation)` (typically in **[0, 1]** for the bundled rubrics).
- **`observation.global_metrics["rubric_score"]`** — same value for convenience.
- **`observation.metadata["rubric_scores"]`** — per-child scores when using composed rubrics (e.g. `Sequential` / `WeightedSum` from `openenv.core.rubrics`).
- **`state.last_rubric_score`** — last step’s rubric value (see `/state`).

Rubrics are **reset** on every `reset()` (`TrajectoryRubric` trajectory cleared).

### Built-in rubric names (`DYNAMIC_CORRIDOR_RUBRIC`)

| Value | Class | Behavior |
| --- | --- | --- |
| `none` (default) | — | No rubric. |
| `terminal_ev` | `TerminalEVCorridorRubric` | 0 until `done`; then **1 − travel_time / max_sim_time** if EV arrived, else 0. |
| `trajectory_ev` | `TrajectoryEVArrivalRubric` | Same terminal score; intermediate steps return 0; use `compute_step_rewards()` for credit assignment over the trajectory. |

Programmatic use:

```python
from dynamic_corridor_env import TerminalEVCorridorRubric
from dynamic_corridor_env.server.dynamic_corridor_environment import DynamicCorridorEnvironment

env = DynamicCorridorEnvironment(rubric=TerminalEVCorridorRubric(max_sim_time_s=900))
```

## Running

```bash
cd dynamic_corridor_env
uv sync
uv run server --port 8000
```

The first reset generates `nets/pune-5/pune-5.net.xml` if it is missing (requires `netconvert`).

## Docker

```bash
docker build -f server/Dockerfile -t dynamic-corridor-env:latest .
docker run -p 8000:8000 dynamic-corridor-env:latest
```

```bash
docker run -p 8001:8000 dynamic-corridor-env:latest
curl -X POST http://localhost:8001/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"grid_4x4_default","seed":42,"episode_id":"curl-1"}'
```

## Custom Simulation UI

Dashboard at `/viz` for stepping, rewards, and schematic corridor view.

## Configuration

| Variable | Default |
| --- | --- |
| `DYNAMIC_CORRIDOR_NET_FILE` | `nets/pune-5/pune-5.net.xml` |
| `DYNAMIC_CORRIDOR_ROUTE_FILE` | `nets/pune-5/pune-5.rou.xml` |
| `DYNAMIC_CORRIDOR_DELTA_TIME` | `5` |
| `DYNAMIC_CORRIDOR_MAX_SECONDS` | `900` |
| `DYNAMIC_CORRIDOR_SEED` | `42` |
| `DYNAMIC_CORRIDOR_REWARD_MODE` | `clearing` |
| `DYNAMIC_CORRIDOR_RUBRIC` | `none` |
| `SUMO_BINARY` | `sumo` |

## Local Python SUMO install

```bash
uv pip install --find-links https://sumo.dlr.de/daily/wheels/ eclipse-sumo
```

The environment resolves `sumo` and `netconvert` via `sumolib.checkBinary()` when they are not on `PATH`.
