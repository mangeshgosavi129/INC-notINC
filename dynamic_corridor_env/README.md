---
title: Smart Traffic Dynamic Corridor
emoji: 🚑
colorFrom: red
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
---

# Disaster Dynamic Corridor Environment

OpenEnv environment for LLM-controlled emergency traffic response. The task targets Theme #3 World Modeling with a multi-agent flavor: a controller must keep a live model of a partially observable 16-intersection city grid while a hospital-bound ambulance, road incidents, congestion surges, and degraded roads change the corridor over time.

The default controller is `Season998/Traffic-R1` through Hugging Face Inference Providers. The server asks the model for strict JSON matching `DynamicCorridorAction`; if Hugging Face is unavailable, it falls back to the rule-based peer-agent controller so demos and tests still run.

## What The Agent Does

At each step the agent receives the existing OpenEnv observation:

- `intersections`: signal phases, valid green phases, queues, EV ETA, EV target phase, and approach signal states.
- `ev`: ambulance route, current edge, progress, waiting time, travel time, and arrival status.
- `route_choice`: candidate next road edges, seeded road weights, queues, backtracking flags, and reachability.
- `global_metrics`: traffic metrics, Traffic-R1 runtime status, reward breakdown, and disaster context.

The action schema is unchanged:

```json
{
  "phase_by_intersection": {
    "INT_1_1": 1
  },
  "next_edge_id": "NW_OUT_TO_INT_1_1",
  "reason": "clear ambulance route"
}
```

If a client sends a non-empty action, the environment applies it directly. If the client sends an empty/default action, the internal Traffic-R1 runtime chooses signal phases and route choices.

## Disaster Mode

Each reset deterministically creates a seeded disaster episode:

- temporary blocked road edges,
- degraded-speed road segments,
- demand surges at selected intersections,
- a hospital urgency deadline.

The public Pydantic models are unchanged. Incident state is exposed through `observation.global_metrics["disaster_context"]`, and reward details are exposed through `observation.global_metrics["reward_breakdown"]`.

Blocked and degraded roads affect route candidates and route scoring. Demand surges affect queue pressure. The reward still stays in `[0, 1]`, but now explicitly values EV progress, safe rerouting around blocked edges, low EV waiting time, controlled queues, throughput, and limited phase churn.

## API

```python
from dynamic_corridor_env import DynamicCorridorAction, DynamicCorridorEnv

env = DynamicCorridorEnv(base_url="http://localhost:8000")
result = env.reset(task_id="grid_4x4_default")

action = DynamicCorridorAction(
    phase_by_intersection={
        ix.intersection_id: ix.ev_target_phase or ix.current_phase
        for ix in result.observation.intersections
    },
    next_edge_id=(
        result.observation.route_choice.candidates[0].edge_id
        if result.observation.route_choice.candidates
        else None
    ),
)
result = env.step(action)
```

For backward compatibility, reset requests using `task_id="pune_5_default"` are accepted and mapped to `grid_4x4_default`.

## Hugging Face Configuration

Set these environment variables in local runs or as Hugging Face Space secrets:

| Variable | Default |
| --- | --- |
| `HF_TOKEN` | required for Traffic-R1 calls |
| `HF_MODEL` | `Season998/Traffic-R1` |
| `HF_PROVIDER` | `auto` |
| `HF_TIMEOUT_SECONDS` | `20` |
| `HF_MAX_RETRIES` | `2` |
| `DYNAMIC_CORRIDOR_AGENT_MODE` | `traffic_r1` |
| `DYNAMIC_CORRIDOR_DISASTER_MODE` | `1` |

Fallback/offline modes:

```bash
DYNAMIC_CORRIDOR_AGENT_MODE=heuristic uv run server --port 8000
DYNAMIC_CORRIDOR_AGENT_MODE=meta_ppo uv run server --port 8000
```

## Running

```bash
cd dynamic_corridor_env
uv sync
export HF_TOKEN=...
uv run server --port 8000
```

The first reset generates `nets/pune-5/pune-5.net.xml` from the bundled SUMO node and edge files if it is missing.

## Docker

```bash
cd dynamic_corridor_env
docker build -f server/Dockerfile -t dynamic-corridor-env:latest .
docker run -p 8000:8000 -e HF_TOKEN=$HF_TOKEN dynamic-corridor-env:latest
```

## Visualization

The custom dashboard at `/viz` shows the 4x4 grid, EV marker, queue bars, route candidates, signal choices, reward feedback, and Traffic-R1 runtime metadata.

Visit [http://localhost:8000/viz](http://localhost:8000/viz).

## Evaluation

The main metric is ambulance travel-time improvement under disaster incidents:

```text
improvement = (baseline_ev_travel_time - agent_ev_travel_time) / baseline_ev_travel_time
```

Recommended baselines are fixed-time, emergency-aware heuristic, peer-agent fallback, and Traffic-R1. Commit reward and travel-time plots from fixed seeds before final submission.

Create the 50-run baseline reward dataset and graph images before reinforcement learning:

```bash
uv run baseline-disaster --episodes 50 --seed-start 42 --mode heuristic --output-dir artifacts/baseline
```

Outputs:

- `baseline_episodes.csv`: one row per seeded simulation.
- `baseline_steps.csv`: per-step reward trace for every episode.
- `baseline_summary.json`: aggregate reward, arrival, and travel-time stats.
- `baseline_total_reward_curve.svg`, `baseline_mean_reward_curve.svg`, `baseline_reward_histogram.svg`, `baseline_travel_time_curve.svg`, and `baseline_mean_step_reward.svg`.

Run the bundled evaluation harness:

```bash
uv run evaluate-disaster --seeds 42,43,44 --modes heuristic,traffic_r1 --output-dir artifacts/evaluation
```

It writes `disaster_evaluation.csv`, `reward_plot.svg`, and `travel_time_plot.svg`. Traffic-R1 runs require `HF_TOKEN`; without it, the runtime reports fallback in `global_metrics.agent_runtime`.
