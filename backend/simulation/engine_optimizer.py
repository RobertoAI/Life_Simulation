"""Simulation profiler and chunk-based processing utilities for large-scale simulations (10K-50K+ agents)."""

import time
import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.simulation.agent_state import AgentState
    from backend.simulation.world import World


class SimulationProfiler:
    """Records per-phase timing statistics for each simulation tick.

    Tracks: movement, energy, hunger, death, reproduction, world, decision.
    Provides avg, min, max, and last-run durations for each phase.
    """

    PHASE_NAMES = [
        "movement",
        "energy",
        "hunger",
        "death",
        "reproduction",
        "world",
        "decisions",
    ]

    def __init__(self) -> None:
        self._tick_start: float | None = None
        self._tick_end: float | None = None
        # For each phase: list of durations in milliseconds
        self._phase_records: dict[str, list[float]] = {name: [] for name in self.PHASE_NAMES}
        self._total_records: list[float] = []

    def start_tick(self) -> None:
        """Mark the beginning of a tick."""
        self._tick_start = time.perf_counter()

    def end_tick(self) -> None:
        """Mark the end of a tick and record total duration."""
        if self._tick_start is not None:
            self._tick_end = time.perf_counter()
            total_ms = (self._tick_end - self._tick_start) * 1000.0
            self._total_records.append(total_ms)

    def record_phase(self, phase: str, duration_ms: float) -> None:
        """Record the duration of a single phase in milliseconds."""
        if phase in self._phase_records:
            self._phase_records[phase].append(duration_ms)

    def get_stats(self) -> dict:
        """Return avg, min, max, last for each phase plus total tick time."""
        stats: dict = {}

        for phase in self.PHASE_NAMES:
            records = self._phase_records[phase]
            if records:
                stats[phase] = {
                    "avg_ms": float(np.mean(records)),
                    "min_ms": float(np.min(records)),
                    "max_ms": float(np.max(records)),
                    "last_ms": float(records[-1]),
                }
            else:
                stats[phase] = {
                    "avg_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                    "last_ms": 0.0,
                }

        # Total tick timing
        if self._total_records:
            stats["total"] = {
                "avg_ms": float(np.mean(self._total_records)),
                "min_ms": float(np.min(self._total_records)),
                "max_ms": float(np.max(self._total_records)),
                "last_ms": float(self._total_records[-1]),
            }
        else:
            stats["total"] = {"avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "last_ms": 0.0}

        return stats

    def get_report(self) -> dict:
        """Return a formatted dict suitable for frontend consumption."""
        stats = self.get_stats()
        report: dict = {
            "summary": {
                "total_ticks_recorded": len(self._total_records),
                "avg_tick_ms": stats["total"]["avg_ms"],
                "min_tick_ms": stats["total"]["min_ms"],
                "max_tick_ms": stats["total"]["max_ms"],
                "last_tick_ms": stats["total"]["last_ms"],
            },
            "phases": {},
        }
        for phase in self.PHASE_NAMES:
            if phase in stats:
                report["phases"][phase] = {
                    "avg_ms": round(stats[phase]["avg_ms"], 3),
                    "min_ms": round(stats[phase]["min_ms"], 3),
                    "max_ms": round(stats[phase]["max_ms"], 3),
                    "last_ms": round(stats[phase]["last_ms"], 3),
                }
        return report

    def reset(self) -> None:
        """Clear all recorded statistics."""
        self._tick_start = None
        self._tick_end = None
        for phase in self._phase_records:
            self._phase_records[phase] = []
        self._total_records.clear()


def split_agents_into_chunks(
    agent_state,  # AgentState
    chunk_size: int = 5000,
) -> list[np.ndarray]:
    """Split alive agent indices into chunks for batch processing.

    Args:
        agent_state: AgentState instance.
        chunk_size: Maximum number of agents per chunk.

    Returns:
        List of numpy arrays, each containing a subset of alive indices.
    """
    alive_indices = np.flatnonzero(agent_state.alive)
    if len(alive_indices) == 0:
        return []
    return [
        alive_indices[i : i + chunk_size]
        for i in range(0, len(alive_indices), chunk_size)
    ]


def process_chunk(
    agent_state,  # AgentState
    chunk_indices: np.ndarray,
    world,  # World
    decisions: np.ndarray | None = None,
) -> dict:
    """Process a subset of agents for a single tick phase.

    This is a helper for chunk-based tick execution.
    It processes movement, energy, hunger, and death for the given chunk.

    Args:
        agent_state: AgentState instance.
        chunk_indices: Indices of agents in this chunk.
        world: World instance.
        decisions: Pre-computed action decisions (shape must match chunk size).

    Returns:
        Dict with counts of deaths, births, etc. in this chunk.
    """
    n = len(chunk_indices)
    if n == 0:
        return {"deaths": 0, "eaten": 0}

    alive_mask_chunk = agent_state.alive[chunk_indices]
    alive_in_chunk = chunk_indices[alive_mask_chunk]
    nc = len(alive_in_chunk)
    if nc == 0:
        return {"deaths": 0, "eaten": 0}

    # Movement for this chunk
    dx = np.random.randint(-1, 2, size=nc, dtype=np.int32)
    dy = np.random.randint(-1, 2, size=nc, dtype=np.int32)
    agent_state.position_x[alive_in_chunk] = (
        agent_state.position_x[alive_in_chunk] + dx
    ) % world.width
    agent_state.position_y[alive_in_chunk] = (
        agent_state.position_y[alive_in_chunk] + dy
    ) % world.height

    # Energy decay
    metabolism_multiplier = 0.7 + 0.6 * agent_state.genome_metabolism[alive_in_chunk]
    agent_state.energy[alive_in_chunk] = np.maximum(
        agent_state.energy[alive_in_chunk] - 0.5 * metabolism_multiplier, 0.0
    )

    # Hunger
    agent_state.hunger[alive_in_chunk] = np.minimum(
        agent_state.hunger[alive_in_chunk] + 0.3, 100.0
    )

    # Deaths
    resilience_buffer = 10.0 * agent_state.genome_resilience[alive_in_chunk]
    starved = agent_state.energy[alive_in_chunk] <= -resilience_buffer
    n_deaths = int(starved.sum())
    agent_state.alive[alive_in_chunk[starved]] = False

    # Eat (if decisions provided)
    n_eaten = 0
    if decisions is not None and len(decisions) == n:
        eat_mask = decisions == 0
        # Re-check alive after chunk alive mask application
        chunk_alive_mask = agent_state.alive[chunk_indices]
        eat_indices = chunk_indices[chunk_alive_mask & eat_mask]
        if len(eat_indices) > 0:
            eat_pos_x = agent_state.position_x[eat_indices]
            eat_pos_y = agent_state.position_y[eat_indices]
            available = world.resources[eat_pos_x, eat_pos_y]
            consumption = np.minimum(available, 0.3)
            world.resources[eat_pos_x, eat_pos_y] -= consumption
            metabolism_bonus = agent_state.genome_metabolism[eat_indices]
            energy_gain = consumption * 50.0 * (0.8 + 0.4 * metabolism_bonus)
            agent_state.energy[eat_indices] = np.clip(
                agent_state.energy[eat_indices] + energy_gain, 0.0, 100.0
            )
            agent_state.hunger[eat_indices] = np.maximum(
                agent_state.hunger[eat_indices] - 10.0, 0.0
            )
            n_eaten = len(eat_indices)

    return {"deaths": n_deaths, "eaten": n_eaten}
