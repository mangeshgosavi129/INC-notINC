# Multi-Agent Green Corridors on OpenEnv: RL Meets Traffic Simulation

Train and benchmark policies that clear emergency corridors—without treating the city like a fixed-timer spreadsheet.

[Open Source + Article](https://huggingface.co/blog) · Published April 26, 2026

---

Static signals do not know an ambulance is coming. For the **Meta AI OpenEnv Hackathon**, we built a **Multi-Agent Reinforcement Learning (MARL)**-ready environment whose single goal is the **green corridor**: give emergency vehicles a coordinated path through a signalized grid while limiting the congestion ripple everywhere else.

The stack is deliberately boring in the right way: **OpenEnv** exposes `/reset`, `/step`, and `/state`, so the same simulator speaks to **vectorized RL trainers** today and to **LLM agents** tomorrow—no bespoke socket protocol per model family.

```
Your client (PPO, scripted bot, or LLM tool loop)
  → POST /reset · /step · GET /state
  → OpenEnv server (this repo)
  → SUMO microsimulation
  → Structured observation + scalar reward + rubric scores
```

If you care about reproducible urban RL in 2026, this is the kind of “batteries included” setup the Hugging Face community tends to remix: one Hub-ready narrative, one clear API, metrics that appear in `global_metrics` without parsing prose.

---

## Get the code

The environment lives under `dynamic_corridor_env/` in this repository.

```bash
git clone https://github.com/mangeshgosavi129/INC-notINC.git
cd INC-notINC/dynamic_corridor_env
uv sync
uv run server --port 8000
```

On first `reset`, the **Pune-style 4×4 grid** (`nets/pune-5/`) is materialized with `netconvert` if `pune-5.net.xml` is missing. Point `DYNAMIC_CORRIDOR_NET_FILE` / `DYNAMIC_CORRIDOR_ROUTE_FILE` at your own SUMO network when you outgrow the default scenario.

---

## What you need installed

Not tied to a single OS—anything that runs SUMO and Python 3.10+ works.

- **SUMO** (`sumo`, `netconvert` on `PATH`, or install via the Eclipse SUMO wheels documented in the package README).
- **Python 3.10+** with **`uv`** (or `pip`) for dependencies.
- Optional: **Docker** using `server/Dockerfile` if you want a one-command server.

---

## Step 1: Smoke-test the HTTP surface

With the server up:

```bash
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id":"grid_4x4_default","seed":42,"episode_id":"smoke-1"}' | python3 -m json.tool
```

You should get a `DynamicCorridorObservation`: per-intersection queues, EV route progress, optional route-choice candidates, and `global_metrics` populated for benchmarking.

---

## Step 2: Step with a legal signal plan

Actions are **discrete**: each intersection maps to a **SUMO green-phase index** (`DynamicCorridorAction.phase_by_intersection`). You can also set `next_edge_id` when the episode exposes route-choice candidates.

```bash
curl -s -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "phase_by_intersection": {"INT_1_1": 0, "INT_1_2": 2},
    "reason": "smoke-test"
  }' | python3 -m json.tool
```

Missing intersections keep their current phase; invalid phases are ignored and penalized in **`clearing`** reward mode (see below).

---

## Step 3: Watch rewards and rubrics

Set `DYNAMIC_CORRIDOR_REWARD_MODE` to switch objectives. For PPO-friendly bounded signals, enable **`DYNAMIC_CORRIDOR_REWARD_UNIT_OPEN=1`** so step rewards live strictly inside `(0, 1)` via a sigmoid over the raw clearing signal (scale with `DYNAMIC_CORRIDOR_REWARD_SIGMOID_SCALE`, default `40`).

OpenEnv **rubrics** (e.g. `terminal_ev`, `trajectory_ev`) add evaluation scores in `observation.metadata["rubric_score"]` without replacing `observation.reward`.

---

## How it works

1. **Reset** draws a new SUMO episode: seeded random **road weights** per edge (for route-choice curricula), places background traffic, and positions the ambulance route (`NW_OUT` → `SE_OUT` by default).
2. **Observation** packs **local** intersection state (queues, speeds, EV approach edges, ETA steps, distance in metres) plus **global** EV telemetry (`waiting_time`, `travel_time`, `arrived`) and **`route_choice`** candidates with per-edge weights and queue estimates.
3. **Step** applies your phase map in SUMO, advances simulation by `DYNAMIC_CORRIDOR_DELTA_TIME` seconds (default **5**), and returns the next observation, **scalar reward**, `done`, and human-readable `feedback`.
4. **Training** today uses the bundled **PPO** adapter (`ppo.py`): a **14-D** feature vector per intersection encodes normalized queues, phase timing, EV urgency (ETA + distance proximity), and corridor pressure. The policy emits per-intersection phase logits (and optional route head).
5. **Decentralized coordination** (`decentralized.py`) implements **one-hop peer messages** (`PeerMessage`: ETA, target phase, route index, TTL) so you can run intersection agents that “talk” to grid neighbors—not only a single central brain submitting one fat action.

There is no hidden keyword router: if you plug in an LLM, it should call the same JSON schema your RL trainer uses.

---

## Environment specification (for RL researchers)

### State space (what the agent sees)

Structured JSON (not a flat image):

- **Per intersection (`IntersectionObservation`)**: current / valid phases, **queue_by_phase** (halted vehicles per green phase), total **queue_length**, **vehicle_count**, **mean_speed** (m/s), whether the intersection is on the EV route, **ev_approach_edge**, **ev_target_phase**, **ev_eta_steps**, **ev_distance_m** (metres to the intersection, or `-1` if unknown).
- **EV (`EVObservation`)**: route edges, **edge_progress**, **waiting_time**, **travel_time**, **arrived**, coarse **progress** along the route.
- **Route choice (`RouteChoiceObservation`)**: source/destination nodes, **active_route_edges**, per-episode **road_weights**, and **candidates** with queue estimates, lengths, speed limits, and reachability flags.
- **`global_metrics`**: includes **`ev_travel_time_s`**, **`ev_clearing_success`**, **`mean_corridor_queue`**, **`invalid_action_count_episode`**, reward mode, timeout flags—intended for rubrics and plots without scraping `feedback`.

### Action space (what the agent does)

- **Discrete phases**: `dict[intersection_id → int]` selecting which **green phase** to serve next (SUMO indices).
- **Optional route choice**: `next_edge_id` must appear in the current candidate list; invalid picks are penalized in **`clearing`** mode and yield **0** reward in **`route_weights`** mode.

### Reward function (balancing ambulance delay vs city-wide jam)

Two modes, controlled by **`DYNAMIC_CORRIDOR_REWARD_MODE`**:

| Mode | Typical range | Intent |
| --- | --- | --- |
| **`clearing`** (default) | clipped **~[−10, 10]** | Corridor objective: reward EV progress, penalize EV wait, corridor queues, invalid actions, and bad route choices; terminal bonus/penalty on arrival vs timeout. |
| **`route_weights`** | **[0, 1]** | Auxiliary / curriculum signal from **mean seeded edge weight** along the active route only. |

For analysis, compare **baseline vs agent** EV travel time:

```text
improvement = (baseline_ev_travel_time - agent_ev_travel_time) / baseline_ev_travel_time
```

Use `global_metrics.ev_travel_time_s` and `ev_clearing_success` directly.

---

## Multi-agent coordination logic

- **Information sharing**: the default server path is a **central agent** that sees **all intersections** in one observation. The **`decentralized.AgentRuntime`** path models **local** decisions with **peer messages** between **grid neighbors** (ETA, intended phase, route progress) so you can train or script truly distributed controllers.
- **Global vs local reward**: training uses the **environment scalar** returned on each step (global to the episode). Optional **per-agent reward mixing** in `ppo.py` can add local queue / EV shaping unless you pass **`--env-reward-only`** to trust the env signal alone—useful when rewards are already sigmoid-bounded.

---

## LLM integration (the “agentic” angle)

**Today:** the reference trainer is **PPO** over vectorized observations.

**Tomorrow (same API):** an LLM can:

- **Act directly** as a policy: map `DynamicCorridorObservation` JSON → `DynamicCorridorAction` JSON via tool calling, identical to the `/step` payload.
- **Plan, then act**: use the LLM as a **strategic planner** (route intent, corridor priority tiers) and let a smaller RL policy or rules layer translate to phase indices at 5 s resolution.

**Prompting sketch:** serialize `intersections` (ids, queues, EV ETA/distance), `ev` block, and `route_choice.candidates` into a compact bullet list; instruct the model to output **only** valid JSON matching `phase_by_intersection` and optional `next_edge_id`. Keep numbers verbatim from the observation—no hallucinated phase IDs.

---

## Simulation backend and KPIs

- **Backend**: **SUMO** on a **custom Pune-style 4×4 grid** (16 signalized intersections, `INT_1_1` … `INT_4_4`), not CityFlow in the default bundle.
- **KPIs we optimize for reporting**:
  - **Emergency travel time** (`ev_travel_time_s`) and **clearing success** (`ev_clearing_success`).
  - **Mean corridor queue** (`mean_corridor_queue`) as a proxy for ripple congestion.
  - **Invalid action rate** (`invalid_action_count_episode`) for sample efficiency.
  - **OpenEnv rubric scores** when you enable `DYNAMIC_CORRIDOR_RUBRIC`.

---

## Live progress · Hackathon weekend (April 25–26, 2026)

**Phase 1 (complete):** OpenEnv server, SUMO grid, structured observations, dual reward modes, route choice, PPO baseline, `/viz` dashboard for stepping and schematic views.

**Phase 2 (in flight):** scaling training runs, tightening decentralized messaging policies, and packaging the first **Hub-ready policy checkpoints** plus evaluation cards.

If you are judging this weekend, ask for the latest **`global_metrics` traces** and rubric histograms—we are optimizing for transparent numbers, not demo-only smoke.

---

## Hugging Face roadmap

| Artifact | Plan |
| --- | --- |
| **Space** | Gradio or Streamlit demo hitting the hosted `/reset` `/step` API (live SUMO behind autoscaling is heavy—likely **recorded rollouts** + optional local Docker instructions). |
| **Models** | Initial release: **PPO actor-critic** on the 14-D intersection features; document backbone once public. LLM experiments will cite the **base model** (e.g., instruction-tuned 8B class) when we freeze prompts. |
| **Dataset** | We are evaluating a **trajectory dataset** (observation/action/reward shards) on the Hub for offline RL and LLM fine-tuning—if you want early access, open a discussion on the model repo. |

---

## Troubleshooting

**`netconvert` errors on first boot:** confirm SUMO is installed and `DYNAMIC_CORRIDOR_NET_FILE` points at writable `*.nod.xml` / `*.edg.xml` sources.

**Flat learning curves with PPO:** try **`DYNAMIC_CORRIDOR_REWARD_UNIT_OPEN=1`** and increase **`DYNAMIC_CORRIDOR_REWARD_SIGMOID_SCALE`** if the critic sees overly sharp sigmoid steps.

**Invalid phases every step:** log `feedback` and ensure your policy only emits indices from each intersection’s `valid_phases`.

---

## Environment variables (quick reference)

| Variable | Default | Description |
| --- | --- | --- |
| `DYNAMIC_CORRIDOR_NET_FILE` | bundled Pune grid | SUMO `*.net.xml` |
| `DYNAMIC_CORRIDOR_ROUTE_FILE` | bundled routes | SUMO `*.rou.xml` |
| `DYNAMIC_CORRIDOR_DELTA_TIME` | `5` | Seconds per decision step |
| `DYNAMIC_CORRIDOR_MAX_SECONDS` | `900` | Episode horizon |
| `DYNAMIC_CORRIDOR_REWARD_MODE` | `clearing` | `clearing` or `route_weights` |
| `DYNAMIC_CORRIDOR_REWARD_UNIT_OPEN` | unset | Set `1` for sigmoid-bounded clearing rewards |
| `DYNAMIC_CORRIDOR_REWARD_SIGMOID_SCALE` | `40` | Sigmoid steepness for open-unit clearing mode |
| `DYNAMIC_CORRIDOR_RUBRIC` | `none` | `terminal_ev`, `trajectory_ev`, etc. |
| `SUMO_BINARY` | `sumo` | SUMO executable name |

---

## Why Hugging Face should care

This project sits at the intersection of **Reinforcement Learning** and **agentic orchestration**—two threads the Hub community doubled down on in 2026. OpenEnv gives you a **stable contract**; SUMO gives you **grounded physics**; rubrics give you **verifiable scores**. That combination is what makes the artifact forkable: swap the policy, keep the benchmark.

If you are building something similar, fork the env, swap the network, and publish your **travel-time deltas**—we will be the first to star the comparison.

---

*Add author bylines and model cards as artifacts land on the Hub.*
