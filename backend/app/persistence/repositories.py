import json
from datetime import datetime, timezone

import aiosqlite


class SimulationRunRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create(self, run_id: str, name: str, config: dict,
                     corridor_id: str, controller_type: str, seed: int | None = None) -> None:
        await self.conn.execute(
            "INSERT INTO simulation_runs (run_id, name, created_at, config_json, corridor_id, controller_type, random_seed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, name, datetime.now(timezone.utc).isoformat(),
             json.dumps(config), corridor_id, controller_type, seed),
        )
        await self.conn.commit()

    async def update_status(self, run_id: str, status: str, **kwargs) -> None:
        sets = ["status = ?"]
        vals: list = [status]
        for k, v in kwargs.items():
            sets.append(f"{k} = ?")
            vals.append(v)
        vals.append(run_id)
        await self.conn.execute(
            f"UPDATE simulation_runs SET {', '.join(sets)} WHERE run_id = ?", vals
        )
        await self.conn.commit()

    async def get(self, run_id: str) -> dict | None:
        cursor = await self.conn.execute(
            "SELECT * FROM simulation_runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_all(self, limit: int = 50, offset: int = 0) -> list[dict]:
        cursor = await self.conn.execute(
            "SELECT * FROM simulation_runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in await cursor.fetchall()]


class EventRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(self, event_id: str, run_id: str, event_type: str,
                     sim_time: float, payload: dict, source: str) -> None:
        await self.conn.execute(
            "INSERT INTO simulation_events (event_id, run_id, event_type, sim_time, payload_json, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, run_id, event_type, sim_time, json.dumps(payload), source),
        )

    async def get_by_run(self, run_id: str, event_type: str | None = None,
                         limit: int = 500) -> list[dict]:
        if event_type:
            cursor = await self.conn.execute(
                "SELECT * FROM simulation_events WHERE run_id = ? AND event_type = ? ORDER BY sim_time LIMIT ?",
                (run_id, event_type, limit),
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM simulation_events WHERE run_id = ? ORDER BY sim_time LIMIT ?",
                (run_id, limit),
            )
        return [dict(r) for r in await cursor.fetchall()]


class MCTSDecisionRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(self, decision_id: str, run_id: str, sim_time: float,
                     corridor_id: str, state_snapshot: dict, actions: dict,
                     reward: float, iterations: int, tree_depth: int | None = None,
                     computation_ms: float | None = None,
                     exploration_constant: float | None = None) -> None:
        await self.conn.execute(
            "INSERT INTO mcts_decisions (decision_id, run_id, sim_time, corridor_id, "
            "state_snapshot_json, actions_json, reward, iterations, tree_depth, "
            "computation_ms, exploration_constant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (decision_id, run_id, sim_time, corridor_id,
             json.dumps(state_snapshot), json.dumps(actions),
             reward, iterations, tree_depth, computation_ms, exploration_constant),
        )

    async def get_by_run(self, run_id: str, limit: int = 200) -> list[dict]:
        cursor = await self.conn.execute(
            "SELECT * FROM mcts_decisions WHERE run_id = ? ORDER BY sim_time LIMIT ?",
            (run_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


class EVJourneyRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create(self, journey_id: str, run_id: str, ev_id: str,
                     corridor_id: str, dispatch_time: float, free_flow_time: float) -> None:
        await self.conn.execute(
            "INSERT INTO ev_journeys (journey_id, run_id, ev_id, corridor_id, "
            "dispatch_time, free_flow_time) VALUES (?, ?, ?, ?, ?, ?)",
            (journey_id, run_id, ev_id, corridor_id, dispatch_time, free_flow_time),
        )

    async def update_arrival(self, journey_id: str, arrival_time: float,
                             actual_time: float, total_signal_delay: float,
                             cleared: int, waited: int) -> None:
        await self.conn.execute(
            "UPDATE ev_journeys SET arrival_time=?, actual_time=?, total_signal_delay=?, "
            "intersections_cleared=?, intersections_waited=? WHERE journey_id=?",
            (arrival_time, actual_time, total_signal_delay, cleared, waited, journey_id),
        )

    async def log_intersection(self, log_id: str, journey_id: str, run_id: str,
                               intersection_id: str, arrival_time: float,
                               green_time: float | None, enter_time: float | None,
                               wait_duration: float | None,
                               signal_state_on_arrival: str | None) -> None:
        await self.conn.execute(
            "INSERT INTO ev_intersection_logs (log_id, journey_id, run_id, intersection_id, "
            "arrival_time, green_time, enter_time, wait_duration, signal_state_on_arrival) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (log_id, journey_id, run_id, intersection_id, arrival_time,
             green_time, enter_time, wait_duration, signal_state_on_arrival),
        )

    async def get_journey(self, journey_id: str) -> dict | None:
        cursor = await self.conn.execute(
            "SELECT * FROM ev_journeys WHERE journey_id = ?", (journey_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_intersection_logs(self, journey_id: str) -> list[dict]:
        cursor = await self.conn.execute(
            "SELECT * FROM ev_intersection_logs WHERE journey_id = ? ORDER BY arrival_time",
            (journey_id,),
        )
        return [dict(r) for r in await cursor.fetchall()]


class MetricsRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def insert(self, snapshot_id: str, run_id: str, sim_time: float,
                     metrics: dict) -> None:
        await self.conn.execute(
            "INSERT INTO metrics_snapshots (snapshot_id, run_id, sim_time, "
            "total_queue_length, max_queue_length, avg_queue_length, "
            "total_throughput, avg_delay_per_vehicle, ev_progress_pct, "
            "corridor_avg_speed, metrics_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, run_id, sim_time,
             metrics.get("total_queue_length", 0),
             metrics.get("max_queue_length", 0),
             metrics.get("avg_queue_length", 0),
             metrics.get("total_throughput", 0),
             metrics.get("avg_delay_per_vehicle", 0),
             metrics.get("ev_progress_pct", 0),
             metrics.get("corridor_avg_speed", 0),
             json.dumps(metrics)),
        )

    async def get_by_run(self, run_id: str, limit: int = 500) -> list[dict]:
        cursor = await self.conn.execute(
            "SELECT * FROM metrics_snapshots WHERE run_id = ? ORDER BY sim_time LIMIT ?",
            (run_id, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


class ComparisonRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def create(self, pair_id: str, mcts_run_id: str, baseline_run_id: str,
                     config_hash: str) -> None:
        await self.conn.execute(
            "INSERT INTO comparison_pairs (pair_id, mcts_run_id, baseline_run_id, config_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (pair_id, mcts_run_id, baseline_run_id, config_hash,
             datetime.now(timezone.utc).isoformat()),
        )
        await self.conn.commit()

    async def list_all(self) -> list[dict]:
        cursor = await self.conn.execute(
            "SELECT * FROM comparison_pairs ORDER BY created_at DESC"
        )
        return [dict(r) for r in await cursor.fetchall()]
