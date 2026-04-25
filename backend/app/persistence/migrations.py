import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    corridor_id TEXT NOT NULL,
    controller_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    start_sim_time REAL,
    end_sim_time REAL,
    wall_clock_duration_s REAL,
    random_seed INTEGER
);

CREATE TABLE IF NOT EXISTS simulation_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES simulation_runs(run_id),
    event_type TEXT NOT NULL,
    sim_time REAL NOT NULL,
    payload_json TEXT NOT NULL,
    source TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run_time ON simulation_events(run_id, sim_time);
CREATE INDEX IF NOT EXISTS idx_events_type ON simulation_events(run_id, event_type);

CREATE TABLE IF NOT EXISTS agent_decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES simulation_runs(run_id),
    sim_time REAL NOT NULL,
    corridor_id TEXT NOT NULL,
    state_snapshot_json TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    reward REAL NOT NULL,
    iterations INTEGER NOT NULL,
    tree_depth INTEGER,
    computation_ms REAL,
    exploration_constant REAL
);

CREATE INDEX IF NOT EXISTS idx_agent_run_time ON agent_decisions(run_id, sim_time);

CREATE TABLE IF NOT EXISTS ev_journeys (
    journey_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES simulation_runs(run_id),
    ev_id TEXT NOT NULL,
    corridor_id TEXT NOT NULL,
    dispatch_time REAL NOT NULL,
    arrival_time REAL,
    free_flow_time REAL NOT NULL,
    actual_time REAL,
    total_signal_delay REAL,
    intersections_cleared INTEGER,
    intersections_waited INTEGER
);

CREATE TABLE IF NOT EXISTS ev_intersection_logs (
    log_id TEXT PRIMARY KEY,
    journey_id TEXT NOT NULL REFERENCES ev_journeys(journey_id),
    run_id TEXT NOT NULL,
    intersection_id TEXT NOT NULL,
    arrival_time REAL NOT NULL,
    green_time REAL,
    enter_time REAL,
    wait_duration REAL,
    signal_state_on_arrival TEXT
);

CREATE TABLE IF NOT EXISTS metrics_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES simulation_runs(run_id),
    sim_time REAL NOT NULL,
    total_queue_length REAL,
    max_queue_length REAL,
    avg_queue_length REAL,
    total_throughput INTEGER,
    avg_delay_per_vehicle REAL,
    ev_progress_pct REAL,
    corridor_avg_speed REAL,
    metrics_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_metrics_run_time ON metrics_snapshots(run_id, sim_time);

CREATE TABLE IF NOT EXISTS configs (
    config_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    config_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comparison_pairs (
    pair_id TEXT PRIMARY KEY,
    agent_run_id TEXT NOT NULL REFERENCES simulation_runs(run_id),
    baseline_run_id TEXT NOT NULL REFERENCES simulation_runs(run_id),
    config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


async def run_migrations(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA_SQL)
