"""Database initialization, connection utilities, and GPU history persistence."""

import asyncio
import copy
import logging
import os
import sqlite3
import threading
from typing import Optional

from backend.database.models import CREATE_TABLES_SQL

logger = logging.getLogger(__name__)

# Thread-safe lock for DB writes (used by direct-save methods)
_write_lock = threading.Lock()

# Global async writer instance (optional -- methods fall back to direct writes if None)
_async_writer: Optional["AsyncDBWriter"] = None


# ---------------------------------------------------------------------------
# AsyncDBWriter – non-blocking, background batch writer for SQLite
# ---------------------------------------------------------------------------
class AsyncDBWriter:
    """Background asyncio task that batches DB writes from a thread-safe queue.

    The writer owns its own SQLite connection so it never blocks or contends
    with the main app's read connection.
    """

    def __init__(
        self,
        db_path: str,
        flush_interval_seconds: float = 10,
        max_batch_size: int = 1000,
    ) -> None:
        self.db_path = db_path
        self.flush_interval = flush_interval_seconds
        self.max_batch_size = max_batch_size
        # Queue items: dict with "type" and "data" keys
        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._running = False

    # -- public API ---------------------------------------------------------

    async def async_start(self) -> None:
        """Create the dedicated DB connection and start the background loop."""
        self._running = True
        self._conn = sqlite3.connect(
            self.db_path, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")  # safe with WAL
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._task = asyncio.ensure_future(self._run_loop())
        logger.info("AsyncDBWriter started for %s", self.db_path)

    async def async_stop(self) -> None:
        """Flush remaining queued items and shut down cleanly."""
        self._running = False
        await self.flush()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        logger.info("AsyncDBWriter stopped for %s", self.db_path)

    def enqueue_write(self, write_type: str, data: dict) -> None:
        """Add a write operation to the queue (thread-safe, non-blocking).

        Args:
            write_type: One of 'gpu_reading', 'tick_metrics', 'agent_snapshot'.
            data: Payload dict matching the write_type schema.
        """
        try:
            self._queue.put_nowait({"type": write_type, "data": data})
        except asyncio.QueueFull:
            logger.warning("AsyncDBWriter queue full, dropping write of type %s", write_type)

    def get_queue_size(self) -> int:
        """Return the number of pending write operations."""
        return self._queue.qsize()

    async def flush(self) -> int:
        """Drain the entire queue and write to DB immediately.

        Returns the number of items successfully processed.
        """
        total = 0
        while not self._queue.empty():
            batch = []
            while not self._queue.empty() and len(batch) < self.max_batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if batch:
                total += await self._process_batch(batch)
        return total

    # -- internal -----------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main background loop: periodically flush the write queue."""
        try:
            while self._running:
                # Drain whatever is currently in the queue
                if not self._queue.empty():
                    await self.flush()
                # Sleep for the configured interval
                await asyncio.sleep(self.flush_interval)
            # Final drain on shutdown signal
            await self.flush()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("AsyncDBWriter loop crashed")

    async def _process_batch(self, items: list[dict]) -> int:
        """Execute a batch of queued write operations in a single transaction.

        Returns the number of items successfully processed.
        """
        if not items or self._conn is None:
            return 0

        # Group by write type for optimal batch insert
        gpu_readings: list[dict] = []
        tick_metrics: list[dict] = []
        agent_snapshots: list[dict] = []
        failed = 0

        for item in items:
            wtype = item.get("type", "")
            data = dict(item.get("data", {}))  # shallow copy so we can add defaults
            if wtype == "gpu_reading":
                data.setdefault("tick", 0)
                gpu_readings.append(data)
            elif wtype == "tick_metrics":
                data.setdefault("simulation_id", None)
                data.setdefault("tick", 0)
                tick_metrics.append(data)
            elif wtype == "agent_snapshot":
                data.setdefault("simulation_id", None)
                data.setdefault("tick", 0)
                data.setdefault("agent_id", 0)
                agent_snapshots.append(data)
            else:
                logger.warning("Unknown async write type: %s", wtype)
                failed += 1

        try:
            if gpu_readings:
                self._conn.executemany(
                    """INSERT INTO gpu_history
                       (gpu_utilization, vram_used, vram_total, temperature, power_draw, tick)
                       VALUES (:gpu_utilization, :vram_used, :vram_total, :temperature, :power_draw, :tick)""",
                    gpu_readings,
                )
            if tick_metrics:
                self._conn.executemany(
                    """INSERT INTO tick_metrics
                       (simulation_id, tick, population, avg_energy, avg_health,
                        birth_count, death_count, event_count)
                       VALUES (:simulation_id, :tick, :population, :avg_energy, :avg_health,
                               :birth_count, :death_count, :event_count)""",
                    tick_metrics,
                )
            if agent_snapshots:
                self._conn.executemany(
                    """INSERT INTO agent_snapshots
                       (simulation_id, tick, agent_id, position_x, position_y,
                        energy, health, age, generation, genome, fitness_score, parent_id)
                       VALUES (:simulation_id, :tick, :agent_id, :position_x, :position_y,
                               :energy, :health, :age, :generation, :genome, :fitness_score, :parent_id)""",
                    agent_snapshots,
                )
            self._conn.commit()
            processed = len(gpu_readings) + len(tick_metrics) + len(agent_snapshots)
            return processed
        except Exception:
            logger.exception("AsyncDBWriter batch write failed")
            return 0


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

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


def async_start(
    db_path: str,
    flush_interval_seconds: float = 10,
    max_batch_size: int = 1000,
) -> "AsyncDBWriter":
    """Create, start, and install a global AsyncDBWriter.

    Returns the AsyncDBWriter instance (caller should keep this reference
    if they want to call async_stop later, or use async_stop() directly).
    """
    global _async_writer
    if _async_writer is not None:
        logger.warning("AsyncDBWriter already running; replacing")
    _async_writer = AsyncDBWriter(
        db_path,
        flush_interval_seconds=flush_interval_seconds,
        max_batch_size=max_batch_size,
    )
    # Kick off the asyncio loop in a background thread so callers using
    # the sync API (save_gpu_reading, etc.) don't need to manage an event loop.
    loop = asyncio.new_event_loop()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_async_writer.async_start())
        try:
            loop.run_forever()
        finally:
            loop.close()

    thread = threading.Thread(target=_run_loop, daemon=True, name="AsyncDBWriter")
    thread.start()
    _async_writer._loop = loop  # type: ignore[attr-defined]
    _async_writer._thread = thread  # type: ignore[attr-defined]
    logger.info("AsyncDBWriter thread started for %s", db_path)
    return _async_writer


async def async_stop() -> None:
    """Flush and stop the global AsyncDBWriter if one is running."""
    global _async_writer
    if _async_writer is not None:
        writer = _async_writer
        _async_writer = None
        # Signal the writer thread to stop
        if hasattr(writer, "_loop"):
            loop = writer._loop
            # Schedule the stop + loop shutdown from the thread's own loop
            loop.call_soon_threadsafe(
                asyncio.ensure_future, _stop_writer_in_loop(writer)
            )
            # Signal the loop to exit after the coroutine finishes
            loop.call_later(2, lambda: loop.call_soon_threadsafe(loop.stop))
        if hasattr(writer, "_thread"):
            writer._thread.join(timeout=5)


async def _stop_writer_in_loop(writer: "AsyncDBWriter") -> None:
    """Run inside the writer's own event loop to flush and close."""
    await writer.async_stop()


def get_async_writer() -> Optional[AsyncDBWriter]:
    """Return the current global AsyncDBWriter (or None)."""
    return _async_writer


# ---------------------------------------------------------------------------
# Save helpers – transparently route to the async writer when available.
# ---------------------------------------------------------------------------

def save_gpu_reading(db_path: str, reading: dict, tick: int) -> None:
    """Save a single GPU reading, routing to the async writer if available."""
    if _async_writer is not None:
        _async_writer.enqueue_write(
            "gpu_reading",
            {
                "gpu_utilization": reading.get("gpu_utilization"),
                "vram_used": reading.get("vram_used"),
                "vram_total": reading.get("vram_total"),
                "temperature": reading.get("temperature"),
                "power_draw": reading.get("power_draw"),
                "tick": tick,
            },
        )
    else:
        _direct_save_gpu_reading(db_path, reading, tick)


def _direct_save_gpu_reading(db_path: str, reading: dict, tick: int) -> None:
    """Direct (blocking) GPU read save – kept for backward compatibility."""
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
    if _async_writer is not None:
        # Enqueue each reading individually; the background loop will batch
        for reading in readings_batch:
            _async_writer.enqueue_write("gpu_reading", reading)
        return len(readings_batch)
    return _direct_batch_save_gpu_history(db_path, readings_batch)


def _direct_batch_save_gpu_history(db_path: str, readings_batch: list[dict]) -> int:
    """Direct (blocking) batch GPU save – kept for backward compatibility."""
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
    """Save tick metrics for a simulation, routing to the async writer if available."""
    if _async_writer is not None:
        _async_writer.enqueue_write(
            "tick_metrics",
            {
                "simulation_id": sim_id,
                "tick": tick,
                "population": metrics.get("population"),
                "avg_energy": metrics.get("avg_energy"),
                "avg_health": metrics.get("avg_health"),
                "birth_count": metrics.get("birth_count"),
                "death_count": metrics.get("death_count"),
                "event_count": metrics.get("event_count"),
            },
        )
    else:
        _direct_save_simulation_metrics(db_path, sim_id, tick, metrics)


def _direct_save_simulation_metrics(
    db_path: str, sim_id: int, tick: int, metrics: dict
) -> None:
    """Direct (blocking) tick metrics save – kept for backward compatibility."""
    try:
        with _write_lock:
            conn = sqlite3.connect(db_path)
            try:
                # Uses INSERT for each call
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
        logger.warning(
            f"Failed to save simulation metrics (sim={sim_id}, tick={tick}): {e}"
        )


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
    if _async_writer is not None:
        for m in metrics_batch:
            _async_writer.enqueue_write("tick_metrics", m)
        return len(metrics_batch)
    return _direct_batch_save_simulation_metrics(db_path, metrics_batch)


def _direct_batch_save_simulation_metrics(
    db_path: str, metrics_batch: list[dict]
) -> int:
    """Direct (blocking) batch metrics save – kept for backward compatibility."""
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
        logger.warning(
            f"Failed to batch save {len(metrics_batch)} metric rows: {e}"
        )
        return 0
