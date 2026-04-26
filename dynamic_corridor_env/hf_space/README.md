---
title: Smart Traffic Dynamic Corridor
emoji: 🚑
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Disaster Dynamic Corridor

OpenEnv disaster-response traffic environment for training and evaluating LLM agents. A `Season998/Traffic-R1` controller on Hugging Face emits strict JSON actions for a 16-intersection SUMO corridor with an ambulance, blocked roads, degraded speeds, demand surges, and a hospital urgency deadline.

Theme fit: World Modeling plus Multi-Agent Interactions. The model must maintain state over changing traffic and incident conditions, pick safe route edges, and coordinate signal phases without breaking the existing OpenEnv action/observation schema.

## Required Secret

Set `HF_TOKEN` in the Space secrets. Optional overrides:

- `HF_MODEL=Season998/Traffic-R1`
- `HF_PROVIDER=auto`
- `HF_TIMEOUT_SECONDS=20`
- `HF_MAX_RETRIES=2`

If the token or model call fails, the environment remains runnable through the heuristic peer-agent fallback and reports that status in `global_metrics.agent_runtime`.

## API

```python
from dynamic_corridor_env import DynamicCorridorAction, DynamicCorridorEnv

env = DynamicCorridorEnv(base_url="https://mangesh29-smart-traffic.hf.space")
result = env.reset(task_id="grid_4x4_default")

result = env.step(DynamicCorridorAction())
print(result.observation.global_metrics["agent_runtime"])
print(result.observation.global_metrics["disaster_context"])
```

Non-empty client actions are applied directly. Empty actions ask Traffic-R1 to choose:

```json
{
  "phase_by_intersection": {"INT_1_1": 1},
  "next_edge_id": "NW_OUT_TO_INT_1_1",
  "reason": "clear ambulance route"
}
```

## Endpoints

- `GET /health` - health check
- `POST /reset` - reset the seeded disaster episode
- `POST /step` - step with a client action or default Traffic-R1 action
- `GET /state` - current episode state
- `GET /viz` - custom corridor dashboard
