"""Random-policy smoke test for dynamic corridor clearing."""

from __future__ import annotations

import random

from dynamic_corridor_env import DynamicCorridorAction, DynamicCorridorEnv


def main() -> None:
    env = DynamicCorridorEnv(base_url="http://localhost:8000")
    result = env.reset()
    total_reward = 0.0

    for _ in range(100):
        phase_by_intersection = {
            ix.intersection_id: random.choice(ix.valid_phases)
            for ix in result.observation.intersections
            if ix.valid_phases
        }
        result = env.step(DynamicCorridorAction(phase_by_intersection=phase_by_intersection))
        total_reward += result.reward or 0.0
        obs = result.observation
        print(
            f"step={obs.step:03d} reward={result.reward:8.2f} "
            f"ev_progress={obs.ev.progress:.2f} queue={obs.global_metrics.get('total_queue', 0):.1f}"
        )
        if result.done:
            break

    state = env.state()
    print(
        f"done={state.done} total_reward={total_reward:.2f} "
        f"ev_arrived={state.ev_arrived} ev_travel_time={state.ev_travel_time:.1f}s "
        f"ev_waiting_time={state.ev_waiting_time:.1f}s"
    )


if __name__ == "__main__":
    main()
