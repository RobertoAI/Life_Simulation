import numpy as np; np.random.seed(42)
import pytest
import sqlite3
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database.db import init_db, save_gpu_reading, get_connection
from backend.database.queries import AnalyticsQueries


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_init_db_creates_tables(tmp_db):
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()
    expected = {
        'simulations', 'agent_snapshots', 'events',
        'generation_stats', 'tick_metrics', 'gpu_history',
        'balance_adjustments',
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


def test_save_gpu_reading(tmp_db):
    init_db(tmp_db)
    reading = {
        'gpu_utilization': 75.5,
        'vram_used': 4096.0,
        'vram_total': 8192.0,
        'temperature': 65.0,
        'power_draw': 150.0,
    }
    save_gpu_reading(tmp_db, reading, tick=42)
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM gpu_history WHERE tick=42")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row['gpu_utilization'] == 75.5
    assert row['vram_used'] == 4096.0
    assert row['tick'] == 42


def test_analytics_queries(tmp_db):
    init_db(tmp_db)
    # Insert some test data
    conn = get_connection(tmp_db)
    # Insert a simulation
    conn.execute("INSERT INTO simulations (id, name) VALUES (1, 'test_sim')")
    # Insert tick metrics
    conn.executemany(
        "INSERT INTO tick_metrics (simulation_id, tick, population, avg_energy, avg_health, birth_count, death_count, event_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 1, 100, 80.0, 90.0, 5, 2, 0),
            (1, 2, 105, 78.0, 88.0, 8, 3, 1),
            (1, 3, 110, 75.0, 85.0, 10, 5, 0),
        ],
    )
    conn.commit()

    # Test population history query
    pop = AnalyticsQueries.get_population_history(conn, "1")
    assert len(pop) == 3
    assert pop[0]['tick'] == 1
    assert pop[0]['population'] == 100

    # Test tick summary query
    summary = AnalyticsQueries.get_tick_summary(conn, "1", 1, 3)
    assert summary['sample_count'] == 3
    assert summary['avg_population'] == 105.0
    assert summary['total_births'] == 23

    # Test non-existent simulation
    pop_empty = AnalyticsQueries.get_population_history(conn, "999")
    assert pop_empty == []

    conn.close()
