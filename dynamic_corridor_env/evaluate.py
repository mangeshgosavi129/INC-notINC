"""Evaluate disaster-corridor controllers over fixed seeds.

This script intentionally uses only stdlib plotting so it can run in the HF
Space/container without extra visualization dependencies.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from statistics import mean

from .models import DynamicCorridorAction
from .server.dynamic_corridor_environment import DynamicCorridorEnvironment


def run_episode(seed: int, mode: str, max_steps: int) -> dict:
    previous_mode = os.environ.get("DYNAMIC_CORRIDOR_AGENT_MODE")
    os.environ["DYNAMIC_CORRIDOR_AGENT_MODE"] = mode
    env = DynamicCorridorEnvironment(seed=seed)
    rewards: list[float] = []
    try:
        observation = env.reset()
        while not observation.done and len(rewards) < max_steps:
            observation = env.step(DynamicCorridorAction())
            rewards.append(float(observation.reward))
        state = env.state
        return {
            "mode": mode,
            "seed": seed,
            "steps": len(rewards),
            "total_reward": round(sum(rewards), 6),
            "mean_reward": round(mean(rewards), 6) if rewards else 0.0,
            "ev_arrived": int(bool(state.ev_arrived)),
            "ev_travel_time": round(float(state.ev_travel_time), 6),
            "ev_waiting_time": round(float(state.ev_waiting_time), 6),
            "total_queue": round(float(state.total_queue), 6),
        }
    finally:
        env.shutdown()
        if previous_mode is None:
            os.environ.pop("DYNAMIC_CORRIDOR_AGENT_MODE", None)
        else:
            os.environ["DYNAMIC_CORRIDOR_AGENT_MODE"] = previous_mode


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "mode",
        "seed",
        "steps",
        "total_reward",
        "mean_reward",
        "ev_arrived",
        "ev_travel_time",
        "ev_waiting_time",
        "total_queue",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_svg_bar_plot(rows: list[dict], metric: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = [f"{row['mode']}:{row['seed']}" for row in rows]
    values = [float(row[metric]) for row in rows]
    width = max(720, len(values) * 92)
    height = 420
    margin = 58
    chart_h = height - margin * 2
    chart_w = width - margin * 2
    max_value = max(values + [1.0])
    bar_w = chart_w / max(1, len(values))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Arial" font-size="18" font-weight="700">{metric}</text>',
        f'<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#222"/>',
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#222"/>',
    ]
    for idx, (label, value) in enumerate(zip(labels, values)):
        x = margin + idx * bar_w + bar_w * 0.16
        bar_height = (value / max_value) * chart_h
        y = height - margin - bar_height
        color = "#2563eb" if label.startswith("traffic_r1") else "#059669"
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.68:.1f}" height="{bar_height:.1f}" fill="{color}"/>',
                f'<text x="{x + bar_w * 0.34:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-family="Arial" font-size="11">{value:.2f}</text>',
                f'<text x="{x + bar_w * 0.34:.1f}" y="{height - margin + 18}" text-anchor="middle" font-family="Arial" font-size="10" transform="rotate(25 {x + bar_w * 0.34:.1f},{height - margin + 18})">{label}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate disaster corridor controllers")
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--modes", default="heuristic,traffic_r1")
    parser.add_argument("--max-steps", type=int, default=180)
    parser.add_argument("--output-dir", default="artifacts/evaluation")
    args = parser.parse_args()

    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    modes = [value.strip() for value in args.modes.split(",") if value.strip()]
    output_dir = Path(args.output_dir)
    rows = [run_episode(seed, mode, args.max_steps) for mode in modes for seed in seeds]
    write_csv(rows, output_dir / "disaster_evaluation.csv")
    write_svg_bar_plot(rows, "total_reward", output_dir / "reward_plot.svg")
    write_svg_bar_plot(rows, "ev_travel_time", output_dir / "travel_time_plot.svg")
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
