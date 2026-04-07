"""Database initialization, connection utilities, and GPU history persistence."""

import logging
import os
import sqlite3
import threading

from backend.database.models import CREATE_TABLES_SQL

logger = logging.getLogger(__name__)

# Thread-safe lock for DB writes
_write_lock = threading.Lock()


def init_db(db_path: str) -> str:
    """Initialize the database: create data directory and all tables.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The absolute path to the created database.
    """
    # Ensure the parent directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.executescript(CREATE_TABLES_SQL)
    conn.close()
    return db_path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a database connection with WAL mode enabled.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A sqlite3.Connection object.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def save_gpu_reading(db_path: str, reading: dict, tick: int) -> None:
    """Save a single GPU reading to the database.

    Args:
        db_path: Path to the SQLite database file.
        reading: Dictionary with GPU metrics (gpu_utilization, vram_used,
                 vram_total, temperature, power_draw).
        tick: Current simulation tick number.
    """
    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """INSERT INTO gpu_history
                       (gpu_utilization, vram_used, vram_total, temperature, power_draw, tick)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        reading.get("gpu_utilization"),
                        reading.get("vram_used"),
                        reading.get("vram_total"),
                        reading.get("temperature"),
                        reading.get("power_draw"),
                        tick,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to save GPU reading at tick {tick}: {e}")


def batch_save_gpu_history(db_path: str, readings_batch: list[dict]) -> int:
    """Bulk-insert a batch of GPU readings into the database.

    This is more efficient than calling save_gpu_reading individually.

    Args:
        db_path: Path to the SQLite database file.
        readings_batch: List of dicts, each with keys:
            gpu_utilization, vram_used, vram_total, temperature, power_draw, tick.

    Returns:
        Number of readings successfully inserted.
    """
    if not readings_batch:
        return 0

    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.executemany(
                    """INSERT INTO gpu_history
                       (gpu_utilization, vram_used, vram_total, temperature, power_draw, tick)
                       VALUES (:gpu_utilization, :vram_used, :vram_total, :temperature, :power_draw, :tick)""",
                    readings_batch,
                )
                conn.commit()
                return len(readings_batch)
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to batch save {len(readings_batch)} GPU readings: {e}")
        return 0


def save_simulation_metrics(db_path: str, sim_id: int, tick: int, metrics: dict) -> None:
    """Save tick metrics for a simulation.

    Args:
        db_path: Path to the SQLite database file.
        sim_id: Simulation database ID.
        tick: Current tick number.
        metrics: Dictionary with keys:
            population, avg_energy, avg_health, birth_count, death_count, event_count.
    """
    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                # Uses REPLACE INTO for idempotent saves
                conn.execute(
                    """INSERT INTO tick_metrics
                       (simulation_id, tick, population, avg_energy, avg_health,
                        birth_count, death_count, event_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sim_id,
                        tick,
                        metrics.get("population"),
                        metrics.get("avg_energy"),
                        metrics.get("avg_health"),
                        metrics.get("birth_count"),
                        metrics.get("death_count"),
                        metrics.get("event_count"),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to save simulation metrics (sim={sim_id}, tick={tick}): {e}")


def batch_save_simulation_metrics(db_path: str, metrics_batch: list[dict]) -> int:
    """Bulk-insert simulation tick metrics.

    Args:
        db_path: Path to the SQLite database file.
        metrics_batch: List of dicts with keys:
            simulation_id, tick, population, avg_energy, avg_health,
            birth_count, death_count, event_count.

    Returns:
        Number of metric rows successfully inserted.
    """
    if not metrics_batch:
        return 0

    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.executemany(
                    """INSERT INTO tick_metrics
                       (simulation_id, tick, population, avg_energy, avg_health,
                        birth_count, death_count, event_count)
                       VALUES (:simulation_id, :tick, :population, :avg_energy, :avg_health,
                               :birth_count, :death_count, :event_count)""",
                    metrics_batch,
                )
                conn.commit()
                return len(metrics_batch)
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to batch save {len(metrics_batch)} metric rows: {e}")
        return 0


# ------------------------------------------------------------------
# Push notification subscription helpers
# ------------------------------------------------------------------


def save_push_subscription(db_path: str, subscription: dict) -> bool:
    """Save or update a push subscription.

    Args:
        db_path: Path to the SQLite database file.
        subscription: Dict with keys: endpoint, p256dh_key, auth_key, id (UUID).

    Returns:
        True if saved successfully, False on error.
    """
    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """INSERT OR REPLACE INTO push_subscriptions
                       (id, endpoint, p256dh_key, auth_key, active)
                       VALUES (?, ?, ?, ?, 1)""",
                    (
                        subscription.get("id"),
                        subscription.get("endpoint"),
                        subscription.get("p256dh_key"),
                        subscription.get("auth_key"),
                    ),
                )
                conn.commit()
                return True
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to save push subscription: {e}")
        return False


def remove_push_subscription(db_path: str, subscription_id: str) -> bool:
    """Deactivate (soft-delete) a push subscription.

    Args:
        db_path: Path to the SQLite database file.
        subscription_id: The subscription UUID to remove.

    Returns:
        True if removed, False on error.
    """
    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    "UPDATE push_subscriptions SET active = 0 WHERE id = ?",
                    (subscription_id,),
                )
                conn.commit()
                return True
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to remove push subscription {subscription_id}: {e}")
        return False


def get_all_active_subscriptions(db_path: str) -> list[dict]:
    """Retrieve all active push subscriptions.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        List of dicts with keys: id, endpoint, p256dh_key, auth_key.
    """
    try:
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT id, endpoint, p256dh_key, auth_key FROM push_subscriptions WHERE active = 1"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Failed to get active push subscriptions: {e}")
        return []
