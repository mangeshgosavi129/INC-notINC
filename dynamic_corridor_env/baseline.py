"""Run baseline disaster-corridor simulations and produce reward graphs."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from statistics import mean, median

from .models import DynamicCorridorAction
from .server.dynamic_corridor_environment import DynamicCorridorEnvironment


SUMMARY_FIELDS = [
    "episode",
    "seed",
    "mode",
    "steps",
    "total_reward",
    "mean_reward",
    "max_reward",
    "ev_arrived",
    "ev_travel_time",
    "ev_waiting_time",
    "final_ev_progress",
    "final_total_queue",
    "final_max_queue",
    "phase_changes",
]

STEP_FIELDS = [
    "episode",
    "seed",
    "mode",
    "step",
    "reward",
    "cumulative_reward",
    "ev_progress",
    "ev_waiting_time",
    "ev_travel_time",
    "total_queue",
    "max_queue",
    "phase_changes",
    "done",
]


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def run_baseline_episode(
    episode: int,
    seed: int,
    mode: str,
    max_steps: int,
) -> tuple[dict, list[dict]]:
    previous_mode = os.environ.get("DYNAMIC_CORRIDOR_AGENT_MODE")
    os.environ["DYNAMIC_CORRIDOR_AGENT_MODE"] = mode
    env = DynamicCorridorEnvironment(seed=seed)
    rewards: list[float] = []
    step_rows: list[dict] = []
    cumulative = 0.0
    observation = None

    try:
        observation = env.reset()
        while not observation.done and len(rewards) < max_steps:
            observation = env.step(DynamicCorridorAction())
            reward = float(observation.reward)
            rewards.append(reward)
            cumulative += reward
            gm = observation.global_metrics or {}
            step_rows.append(
                {
                    "episode": episode,
                    "seed": seed,
                    "mode": mode,
                    "step": observation.step,
                    "reward": _round(reward),
                    "cumulative_reward": _round(cumulative),
                    "ev_progress": _round(observation.ev.progress),
                    "ev_waiting_time": _round(observation.ev.waiting_time),
                    "ev_travel_time": _round(observation.ev.travel_time),
                    "total_queue": _round(float(gm.get("total_queue", 0.0))),
                    "max_queue": _round(float(gm.get("max_queue", 0.0))),
                    "phase_changes": int(gm.get("phase_changes", 0)),
                    "done": int(bool(observation.done)),
                }
            )

        state = env.state
        final_gm = observation.global_metrics if observation is not None else {}
        summary = {
            "episode": episode,
            "seed": seed,
            "mode": mode,
            "steps": len(rewards),
            "total_reward": _round(sum(rewards)),
            "mean_reward": _round(mean(rewards)) if rewards else 0.0,
            "max_reward": _round(max(rewards)) if rewards else 0.0,
            "ev_arrived": int(bool(state.ev_arrived)),
            "ev_travel_time": _round(state.ev_travel_time),
            "ev_waiting_time": _round(state.ev_waiting_time),
            "final_ev_progress": _round(observation.ev.progress if observation is not None else 0.0),
            "final_total_queue": _round(float(final_gm.get("total_queue", 0.0))),
            "final_max_queue": _round(float(final_gm.get("max_queue", 0.0))),
            "phase_changes": int(state.phase_changes),
        }
        return summary, step_rows
    finally:
        env.shutdown()
        if previous_mode is None:
            os.environ.pop("DYNAMIC_CORRIDOR_AGENT_MODE", None)
        else:
            os.environ["DYNAMIC_CORRIDOR_AGENT_MODE"] = previous_mode


def write_csv(rows: list[dict], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_json(rows: list[dict], path: Path) -> None:
    arrived = [row["ev_arrived"] for row in rows]
    total_rewards = [float(row["total_reward"]) for row in rows]
    travel_times = [float(row["ev_travel_time"]) for row in rows if row["ev_arrived"]]
    payload = {
        "episodes": len(rows),
        "arrival_rate": _round(sum(arrived) / max(1, len(arrived))),
        "total_reward_mean": _round(mean(total_rewards)) if total_rewards else 0.0,
        "total_reward_median": _round(median(total_rewards)) if total_rewards else 0.0,
        "total_reward_min": _round(min(total_rewards)) if total_rewards else 0.0,
        "total_reward_max": _round(max(total_rewards)) if total_rewards else 0.0,
        "ev_travel_time_mean_arrivals": _round(mean(travel_times)) if travel_times else 0.0,
        "ev_travel_time_median_arrivals": _round(median(travel_times)) if travel_times else 0.0,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-family="Arial" font-size="19" font-weight="700">{title}</text>',
    ]


def _axis(parts: list[str], width: int, height: int, margin: int, x_label: str, y_label: str) -> None:
    parts.extend(
        [
            f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#1f2937"/>',
            f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#1f2937"/>',
            f'<text x="{width / 2}" y="{height - 14}" text-anchor="middle" font-family="Arial" font-size="12">{x_label}</text>',
            f'<text x="18" y="{height / 2}" text-anchor="middle" font-family="Arial" font-size="12" transform="rotate(-90 18,{height / 2})">{y_label}</text>',
        ]
    )


def write_line_plot(rows: list[dict], metric: str, path: Path, title: str, y_label: str) -> None:
    width = 980
    height = 460
    margin = 64
    values = [float(row[metric]) for row in rows]
    if not values:
        return
    min_value = min(0.0, min(values))
    max_value = max(1.0, max(values))
    x_den = max(1, len(values) - 1)
    y_den = max(1e-9, max_value - min_value)
    points = []
    for idx, value in enumerate(values):
        x = margin + (idx / x_den) * (width - 2 * margin)
        y = height - margin - ((value - min_value) / y_den) * (height - 2 * margin)
        points.append((x, y))

    parts = _svg_header(width, height, title)
    _axis(parts, width, height, margin, "episode", y_label)
    path_data = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    parts.append(f'<polyline points="{path_data}" fill="none" stroke="#2563eb" stroke-width="3"/>')

    if len(values) >= 5:
        rolling = []
        for idx in range(len(values)):
            window = values[max(0, idx - 4): idx + 1]
            rolling.append(mean(window))
        rolling_points = []
        for idx, value in enumerate(rolling):
            x = margin + (idx / x_den) * (width - 2 * margin)
            y = height - margin - ((value - min_value) / y_den) * (height - 2 * margin)
            rolling_points.append((x, y))
        rolling_data = " ".join(f"{x:.1f},{y:.1f}" for x, y in rolling_points)
        parts.append(f'<polyline points="{rolling_data}" fill="none" stroke="#dc2626" stroke-width="2" stroke-dasharray="8 5"/>')
        parts.append('<text x="760" y="58" font-family="Arial" font-size="12" fill="#dc2626">rolling mean (5)</text>')

    for idx, (x, y) in enumerate(points, start=1):
        if idx == 1 or idx == len(points) or idx % 10 == 0:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#2563eb"/>')
            parts.append(f'<text x="{x:.1f}" y="{height - margin + 18}" text-anchor="middle" font-family="Arial" font-size="10">{idx}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_histogram(values: list[float], path: Path, title: str, x_label: str, bins: int = 12) -> None:
    width = 980
    height = 460
    margin = 64
    if not values:
        return
    lo = min(values)
    hi = max(values)
    if lo == hi:
        hi = lo + 1.0
    counts = [0] * bins
    for value in values:
        idx = min(bins - 1, int(((value - lo) / (hi - lo)) * bins))
        counts[idx] += 1
    max_count = max(counts + [1])
    bar_w = (width - 2 * margin) / bins

    parts = _svg_header(width, height, title)
    _axis(parts, width, height, margin, x_label, "episodes")
    for idx, count in enumerate(counts):
        x = margin + idx * bar_w + bar_w * 0.12
        bar_h = (count / max_count) * (height - 2 * margin)
        y = height - margin - bar_h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.76:.1f}" height="{bar_h:.1f}" fill="#059669"/>')
        bin_lo = lo + (idx / bins) * (hi - lo)
        parts.append(f'<text x="{x + bar_w * 0.38:.1f}" y="{height - margin + 18}" text-anchor="middle" font-family="Arial" font-size="9">{bin_lo:.1f}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_mean_step_reward_plot(step_rows: list[dict], path: Path) -> None:
    by_step: dict[int, list[float]] = {}
    for row in step_rows:
        by_step.setdefault(int(row["step"]), []).append(float(row["reward"]))
    rows = [
        {"step": step, "mean_reward": mean(values)}
        for step, values in sorted(by_step.items())
    ]
    width = 980
    height = 460
    margin = 64
    values = [row["mean_reward"] for row in rows]
    if not values:
        return
    max_step = max(row["step"] for row in rows)
    max_value = max(1.0, max(values))
    parts = _svg_header(width, height, "Mean Baseline Reward By Simulation Step")
    _axis(parts, width, height, margin, "simulation step", "mean reward")
    points = []
    for row in rows:
        x = margin + (row["step"] / max(1, max_step)) * (width - 2 * margin)
        y = height - margin - (row["mean_reward"] / max_value) * (height - 2 * margin)
        points.append((x, y))
    parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" fill="none" stroke="#7c3aed" stroke-width="3"/>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 50 baseline disaster-corridor simulations and plot rewards")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--seed-start", type=int, default=42)
    parser.add_argument("--mode", default="heuristic", help="Baseline controller mode; default avoids LLM/RL calls")
    parser.add_argument("--max-steps", type=int, default=180)
    parser.add_argument("--output-dir", default="artifacts/baseline")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    summaries: list[dict] = []
    all_steps: list[dict] = []

    for episode in range(1, args.episodes + 1):
        seed = args.seed_start + episode - 1
        summary, step_rows = run_baseline_episode(
            episode=episode,
            seed=seed,
            mode=args.mode,
            max_steps=args.max_steps,
        )
        summaries.append(summary)
        all_steps.extend(step_rows)
        print(
            f"episode={episode:03d} seed={seed} total_reward={summary['total_reward']:.3f} "
            f"mean_reward={summary['mean_reward']:.3f} arrived={summary['ev_arrived']} "
            f"travel_time={summary['ev_travel_time']:.1f}s"
        )

    write_csv(summaries, output_dir / "baseline_episodes.csv", SUMMARY_FIELDS)
    write_csv(all_steps, output_dir / "baseline_steps.csv", STEP_FIELDS)
    write_summary_json(summaries, output_dir / "baseline_summary.json")
    write_line_plot(summaries, "total_reward", output_dir / "baseline_total_reward_curve.svg", "Baseline Total Reward Per Episode", "total reward")
    write_line_plot(summaries, "mean_reward", output_dir / "baseline_mean_reward_curve.svg", "Baseline Mean Reward Per Episode", "mean reward")
    write_line_plot(summaries, "ev_travel_time", output_dir / "baseline_travel_time_curve.svg", "Baseline EV Travel Time Per Episode", "travel time (s)")
    write_histogram([float(row["total_reward"]) for row in summaries], output_dir / "baseline_reward_histogram.svg", "Baseline Total Reward Distribution", "total reward")
    write_mean_step_reward_plot(all_steps, output_dir / "baseline_mean_step_reward.svg")

    print(f"wrote {output_dir / 'baseline_episodes.csv'}")
    print(f"wrote {output_dir / 'baseline_steps.csv'}")
    print(f"wrote SVG graphs under {output_dir}")


if __name__ == "__main__":
    main()
