#!/usr/bin/env python3
"""CLI tool: runs MCTS + baseline with same config, prints comparison table."""

import sys
import time

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

BASE = "http://localhost:8000"


def main():
    client = httpx.Client(base_url=BASE, timeout=60.0)

    # Check health
    try:
        r = client.get("/api/health")
        r.raise_for_status()
        print(f"Backend: {r.json()}")
    except Exception as e:
        print(f"Cannot reach backend at {BASE}: {e}")
        sys.exit(1)

    seed = 42
    duration = 300
    params = {
        "duration_s": duration,
        "sim_speed": 10,
        "random_seed": seed,
        "start_time_of_day": "08:00",
    }

    print(f"\nRunning comparison (seed={seed}, duration={duration}s)...")
    print("-" * 60)

    # MCTS run
    print("1. Initializing MCTS run...")
    r = client.post("/api/simulation/init", json={**params, "controller_type": "mcts", "name": "MCTS Comparison"})
    r.raise_for_status()
    mcts_id = r.json()["run_id"]

    print("   Dispatching EV...")
    client.post(f"/api/ev/dispatch/{mcts_id}", json={"ev_id": "AMB_01"})

    print("   Running to completion...")
    t0 = time.time()
    client.post(f"/api/simulation/run/{mcts_id}")
    print(f"   Done in {time.time() - t0:.1f}s")

    # Baseline run
    print("\n2. Initializing baseline run...")
    r = client.post("/api/simulation/init", json={**params, "controller_type": "fixed_time", "name": "Baseline Comparison"})
    r.raise_for_status()
    base_id = r.json()["run_id"]

    print("   Dispatching EV...")
    client.post(f"/api/ev/dispatch/{base_id}", json={"ev_id": "AMB_01"})

    print("   Running to completion...")
    t0 = time.time()
    client.post(f"/api/simulation/run/{base_id}")
    print(f"   Done in {time.time() - t0:.1f}s")

    # Compare
    print("\n3. Comparing results...")
    r = client.get(f"/api/analytics/compare-baseline?mcts_run_id={mcts_id}&baseline_run_id={base_id}")
    r.raise_for_status()
    comp = r.json()

    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    print(f"{'Metric':<25} {'MCTS':>10} {'Baseline':>10} {'Improvement':>12}")
    print("-" * 60)
    print(f"{'EV Delay (s)':<25} {comp['mcts_ev_delay']:>10.1f} {comp['baseline_ev_delay']:>10.1f} {comp['ev_delay_improvement_pct']:>+11.1f}%")
    print(f"{'Avg Queue (veh)':<25} {comp['mcts_avg_queue']:>10.2f} {comp['baseline_avg_queue']:>10.2f} {comp['queue_improvement_pct']:>+11.1f}%")
    print(f"{'Throughput (veh)':<25} {comp['mcts_throughput']:>10d} {comp['baseline_throughput']:>10d} {comp['throughput_improvement_pct']:>+11.1f}%")
    print("=" * 60)

    if comp["ev_delay_improvement_pct"] > 0:
        print("\nMCTS outperformed baseline on EV delay reduction.")
    else:
        print("\nBaseline had equal or lower EV delay (may vary by scenario).")


if __name__ == "__main__":
    main()
