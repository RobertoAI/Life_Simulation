"""Database models - raw SQLite schema definitions."""

# SQL statements to create all tables with indexes
CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS simulations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'stopped',
    config TEXT,
    final_metrics TEXT,
    duration_ticks INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agent_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    position_x REAL,
    position_y REAL,
    energy REAL,
    health REAL,
    age REAL,
    generation INTEGER,
    genome TEXT,
    fitness_score REAL,
    parent_id INTEGER,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    location_x REAL,
    location_y REAL,
    severity REAL,
    description TEXT,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS generation_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    population INTEGER,
    avg_fitness REAL,
    avg_energy REAL,
    diversity_index REAL,
    birth_count INTEGER,
    death_count INTEGER,
    tick_recorded INTEGER,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS tick_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER,
    tick INTEGER NOT NULL,
    population INTEGER,
    avg_energy REAL,
    avg_health REAL,
    birth_count INTEGER,
    death_count INTEGER,
    event_count INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

CREATE TABLE IF NOT EXISTS gpu_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gpu_utilization REAL,
    vram_used REAL,
    vram_total REAL,
    temperature REAL,
    power_draw REAL,
    tick INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS balance_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id INTEGER,
    tick INTEGER NOT NULL,
    parameter TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    reason TEXT,
    reverted INTEGER DEFAULT 0,
    FOREIGN KEY (simulation_id) REFERENCES simulations(id)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_agent_snapshots_sim_tick ON agent_snapshots(simulation_id, tick);
CREATE INDEX IF NOT EXISTS idx_agent_snapshots_agent ON agent_snapshots(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_sim_tick ON events(simulation_id, tick);
CREATE INDEX IF NOT EXISTS idx_generation_stats_sim ON generation_stats(simulation_id, generation);
CREATE INDEX IF NOT EXISTS idx_tick_metrics_sim_tick ON tick_metrics(simulation_id, tick);
CREATE INDEX IF NOT EXISTS idx_gpu_history_tick ON gpu_history(tick);
CREATE INDEX IF NOT EXISTS idx_balance_adj_sim ON balance_adjustments(simulation_id, tick);
CREATE INDEX IF NOT EXISTS idx_gpu_history_timestamp ON gpu_history(timestamp);
"""
