"""Analytics query utilities for the Life Simulation database.

Provides optimized, parameterized queries for common analytics read patterns.
All methods return lists of dicts with column names as keys.
On errors, methods return an empty list and log a warning.
"""

import logging

logger = logging.getLogger(__name__)


class AnalyticsQueries:
    """Static methods for common analytics queries against the simulation database."""

    @staticmethod
    def get_population_history(conn, sim_id: str, limit: int = 1000) -> list[dict]:
        """Get population over time for a simulation.

        Args:
            conn: Active sqlite3 Connection with row_factory set.
            sim_id: Simulation identifier.
            limit: Maximum number of rows to return.

        Returns:
            List of dicts with keys: tick, population.
        """
        try:
            # Prefer tick_metrics as the canonical source
            cursor = conn.execute(
                """SELECT tick, population
                   FROM tick_metrics
                   WHERE simulation_id = ?
                     AND population IS NOT NULL
                   ORDER BY tick ASC
                   LIMIT ?""",
                (sim_id, limit),
            )
            rows = cursor.fetchall()
            # Convert sqlite3.Row to dicts
            return [{"tick": row["tick"], "population": row["population"]} for row in rows]
        except Exception as e:
            logger.warning(f"Failed to get population history for sim {sim_id}: {e}")
            return []

    @staticmethod
    def get_gpu_history(conn, minutes: int = 5) -> list[dict]:
        """Get recent GPU history from the last N minutes.

        Args:
            conn: Active sqlite3 Connection with row_factory set.
            minutes: How many minutes of history to return.

        Returns:
            List of dicts with keys: timestamp, gpu_utilization, vram_used,
            temperature, power_draw.
        """
        try:
            cursor = conn.execute(
                """SELECT timestamp, gpu_utilization, vram_used, temperature, power_draw
                   FROM gpu_history
                   WHERE timestamp >= datetime('now', ?)
                   ORDER BY timestamp ASC""",
                (f"-{minutes} minutes",),
            )
            rows = cursor.fetchall()
            return [
                {
                    "timestamp": row["timestamp"],
                    "gpu_utilization": row["gpu_utilization"],
                    "vram_used": row["vram_used"],
                    "temperature": row["temperature"],
                    "power_draw": row["power_draw"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get GPU history (last {minutes} min): {e}")
            return []

    @staticmethod
    def get_generation_trends(conn, sim_id: str) -> list[dict]:
        """Get per-generation aggregated trends for a simulation.

        Args:
            conn: Active sqlite3 Connection with row_factory set.
            sim_id: Simulation identifier.

        Returns:
            List of dicts with keys: generation, population, avg_fitness,
            avg_energy, birth_count, death_count, diversity_index.
        """
        try:
            cursor = conn.execute(
                """SELECT generation, population, avg_fitness, avg_energy,
                          birth_count, death_count, diversity_index
                   FROM generation_stats
                   WHERE simulation_id = ?
                   ORDER BY generation ASC""",
                (sim_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "generation": row["generation"],
                    "population": row["population"],
                    "avg_fitness": row["avg_fitness"],
                    "avg_energy": row["avg_energy"],
                    "birth_count": row["birth_count"],
                    "death_count": row["death_count"],
                    "diversity_index": row["diversity_index"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get generation trends for sim {sim_id}: {e}")
            return []

    @staticmethod
    def get_event_timeline(conn, sim_id: str, limit: int = 100) -> list[dict]:
        """Get event timeline for a simulation.

        Args:
            conn: Active sqlite3 Connection with row_factory set.
            sim_id: Simulation identifier.
            limit: Maximum number of events to return.

        Returns:
            List of dicts with keys: tick, event_type, severity, description.
        """
        try:
            cursor = conn.execute(
                """SELECT tick, event_type, severity, description
                   FROM events
                   WHERE simulation_id = ?
                   ORDER BY tick ASC
                   LIMIT ?""",
                (sim_id, limit),
            )
            rows = cursor.fetchall()
            return [
                {
                    "tick": row["tick"],
                    "event_type": row["event_type"],
                    "severity": row["severity"],
                    "description": row["description"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get event timeline for sim {sim_id}: {e}")
            return []

    @staticmethod
    def get_balance_history(conn, sim_id: str) -> list[dict]:
        """Get balance adjustment history for a simulation.

        Args:
            conn: Active sqlite3 Connection with row_factory set.
            sim_id: Simulation identifier.

        Returns:
            List of dicts with keys: tick, parameter, old_value, new_value, reason.
        """
        try:
            cursor = conn.execute(
                """SELECT tick, parameter, old_value, new_value, reason
                   FROM balance_adjustments
                   WHERE simulation_id = ?
                   ORDER BY tick ASC""",
                (sim_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "tick": row["tick"],
                    "parameter": row["parameter"],
                    "old_value": row["old_value"],
                    "new_value": row["new_value"],
                    "reason": row["reason"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"Failed to get balance history for sim {sim_id}: {e}")
            return []

    @staticmethod
    def get_tick_summary(conn, sim_id: str, from_tick: int, to_tick: int) -> dict:
        """Get aggregated statistics for a tick range.

        Args:
            conn: Active sqlite3 Connection with row_factory set.
            sim_id: Simulation identifier.
            from_tick: Start tick (inclusive).
            to_tick: End tick (inclusive).

        Returns:
            Dict with aggregated stats, or empty dict on error.
        """
        try:
            cursor = conn.execute(
                """SELECT COUNT(*) AS sample_count,
                          AVG(population) AS avg_population,
                          MIN(population) AS min_population,
                          MAX(population) AS max_population,
                          AVG(avg_energy) AS avg_energy,
                          AVG(avg_health) AS avg_health,
                          SUM(birth_count) AS total_births,
                          SUM(death_count) AS total_deaths,
                          SUM(event_count) AS total_events
                   FROM tick_metrics
                   WHERE simulation_id = ?
                     AND tick BETWEEN ? AND ?""",
                (sim_id, from_tick, to_tick),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "sample_count": row["sample_count"],
                    "avg_population": row["avg_population"],
                    "min_population": row["min_population"],
                    "max_population": row["max_population"],
                    "avg_energy": row["avg_energy"],
                    "avg_health": row["avg_health"],
                    "total_births": row["total_births"],
                    "total_deaths": row["total_deaths"],
                    "total_events": row["total_events"],
                }
            return {}
        except Exception as e:
            logger.warning(
                f"Failed to get tick summary for sim {sim_id} "
                f"(tick {from_tick}..{to_tick}): {e}"
            )
            return {}
