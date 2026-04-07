"""Benchmark suite for the life simulation engine.

Measures performance across different agent population sizes.
Returns structured reports suitable for analysis and comparison.
"""

import time
import json
import asyncio
from typing import List, Optional

import numpy as np

from backend.simulation.engine import SimulationEngine
from backend.config import Settings
from backend.simulation.agent_communication import PheromoneMap
from backend.simulation.decisions import decide


class BenchmarkSettings:
    """Configuration for a benchmark run."""

    def __init__(self, agent_count, ticks, enable_pheromones=False,
                 enable_advanced_behaviors=False, grid_width=200, grid_height=200):
        self.max_agents = int(agent_count * 1.2)  # 20% buffer for births
        self.initial_population = agent_count
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.enable_pheromones = enable_pheromones
        self.enable_advanced_behaviors = enable_advanced_behaviors


async def _run_async_benchmark(
    agent_count: int,
    ticks: int,
    enable_pheromones: bool = False,
    enable_advanced_behaviors: bool = False,
    grid_width: int = 200,
    grid_height: int = 200,
) -> dict:
    """Run benchmark using the full SimulationEngine async tick loop.

    Integrates pheromones and advanced behaviors directly into the tick.
    """
    config = BenchmarkSettings(
        agent_count, ticks, enable_pheromones, enable_advanced_behaviors,
        grid_width, grid_height
    )

    # Instantiate engine using Settings as base
    base = Settings()
    base.grid_width = config.grid_width
    base.grid_height = config.grid_height
    base.max_agents = config.max_agents

    engine = SimulationEngine(base)
    engine.agents.spawn_batch(config.initial_population, config.grid_width, config.grid_height)

    # Initialize pheromone map if enabled
    pheromones: Optional[PheromoneMap] = None
    if enable_pheromones:
        pheromones = PheromoneMap(config.grid_width, config.grid_height)
        engine.pheromones = pheromones  # Attach for reference

    # Metrics
    tick_times = []
    memory_usages = []
    per_tick_births = []
    per_tick_deaths = []

    for _ in range(ticks):
        start = time.perf_counter()
        pre_alive = engine.agents.active_count

        await engine.tick()
        elapsed = (time.perf_counter() - start) * 1000.0

        post_alive = engine.agents.active_count
        births = max(0, post_alive - pre_alive)
        deaths = max(0, pre_alive - post_alive)

        tick_times.append(elapsed)
        memory_usages.append(engine.agents.memory_usage_mb)
        per_tick_births.append(births)
        per_tick_deaths.append(deaths)

    return _compile_metrics(tick_times, memory_usages, per_tick_births,
                            per_tick_deaths, engine)


def _compile_metrics(tick_times, memory_usages, births, deaths, engine) -> dict:
    """Compile raw benchmark data into a metrics dict."""
    tt = np.array(tick_times)
    alive_at_end = engine.agents.active_count

    return {
        "tick_count": len(tick_times),
        "total_time_ms": float(np.sum(tt)),
        "mean_tick_ms": float(np.mean(tt)),
        "median_tick_ms": float(np.median(tt)),
        "std_tick_ms": float(np.std(tt)),
        "min_tick_ms": float(np.min(tt)),
        "max_tick_ms": float(np.max(tt)),
        "p95_tick_ms": float(np.percentile(tt, 95)),
        "p99_tick_ms": float(np.percentile(tt, 99)),
        "mean_memory_mb": float(np.mean(memory_usages)),
        "peak_memory_mb": float(np.max(memory_usages)),
        "total_births": int(np.sum(births)),
        "total_deaths": int(np.sum(deaths)),
        "final_population": int(alive_at_end),
        "ticks_per_second": float(len(tick_times) / (np.sum(tt) / 1000.0)) if np.sum(tt) > 0 else 0.0,
    }


def run_benchmark_sync(
    agent_count: int,
    ticks: int = 100,
    enable_pheromones: bool = False,
    enable_advanced_behaviors: bool = False,
    grid_width: int = 200,
    grid_height: int = 200,
) -> dict:
    """Run a single benchmark synchronously.

    Handles the engine tick loop directly, integrating pheromones
    and advanced behaviors at each step. This is the synchronous
    version used by the CLI and test harness.
    """
    base = Settings()
    base.grid_width = grid_width
    base.grid_height = grid_height
    base.max_agents = int(agent_count * 1.2)

    engine = SimulationEngine(base)
    engine.agents.spawn_batch(agent_count, grid_width, grid_height)

    # Initialize pheromones
    pheromones: Optional[PheromoneMap] = None
    if enable_pheromones:
        pheromones = PheromoneMap(grid_width, grid_height)

    # Metrics
    tick_times = []
    memory_usages = []
    per_tick_births = []
    per_tick_deaths = []

    pre_alive = agent_count

    for _ in range(ticks):
        start = time.perf_counter()
        n_alive = engine.agents.active_count

        # --- Movement ---
        alive_mask = engine.agents.alive
        alive_indices = np.flatnonzero(alive_mask)
        if n_alive > 0:
            engine.agents.tick_movement(grid_width, grid_height)

        # --- Perception ---
        if n_alive > 0 and alive_indices.size > 0:
            perception = engine._compute_perception(engine.agents)
            ai = alive_indices  # alias

            # Pheromone deposit
            if pheromones is not None:
                pos_x = engine.agents.position_x[ai].astype(np.int32)
                pos_y = engine.agents.position_y[ai].astype(np.int32)
                # Agents near food drop food_found pheromones
                local_res = engine.world.resources[pos_x, pos_y]
                high_res_mask = local_res > 0.5
                if np.any(high_res_mask):
                    pheromones.deposit_pheromones(
                        pos_x[high_res_mask], pos_y[high_res_mask],
                        PheromoneMap.FOOD_FOUND, intensity=0.15
                    )
                # Agents fleeing drop danger pheromones
                threat_vals = perception["threat"]
                danger_mask = threat_vals > 0.6
                if np.any(danger_mask):
                    pheromones.deposit_pheromones(
                        pos_x[danger_mask], pos_y[danger_mask],
                        PheromoneMap.DANGER, intensity=0.2
                    )
                # Agents with high fertility drop mate_signal
                fer = engine.agents.genome_fertility[ai]
                mate_mask = fer > 0.7
                if np.any(mate_mask):
                    pheromones.deposit_pheromones(
                        pos_x[mate_mask], pos_y[mate_mask],
                        PheromoneMap.MATE_SIGNAL, intensity=0.1
                    )

            # Advanced behaviors
            if enable_advanced_behaviors:
                from backend.simulation.advanced_behaviors import (
                    compute_pack_affinity,
                    compute_migration_direction,
                    apply_migration,
                    compute_hibernation_prob,
                    apply_hibernation,
                )

                px = engine.agents.position_x[ai].astype(np.int32)
                py = engine.agents.position_y[ai].astype(np.int32)
                energy = engine.agents.energy[ai].copy()
                local_temp = engine.world.temperature[px, py]
                local_res = engine.world.resources[px, py]

                # Migration: move toward better resources
                mig_mask, mig_dx, mig_dy = compute_migration_direction(
                    px, py, local_res, engine.world.resources,
                    grid_width, grid_height, migration_threshold=0.15,
                    search_range=10
                )
                if np.any(mig_mask):
                    new_px, new_py = apply_migration(
                        engine.agents.position_x[ai],
                        engine.agents.position_y[ai],
                        mig_mask, mig_dx, mig_dy,
                        grid_width, grid_height, speed=1
                    )
                    engine.agents.position_x[ai] = new_px
                    engine.agents.position_y[ai] = new_py

                # Hibernation: rest in cold
                hibernation_prob = compute_hibernation_prob(
                    local_temp, energy, engine.agents.genome_metabolism[ai]
                )
                hibernating = np.random.random(len(hibernation_prob)) < hibernation_prob
                if np.any(hibernating):
                    hib_idx = ai[hibernating]
                    engine.agents.energy[hib_idx] = np.clip(
                        engine.agents.energy[hib_idx] + 1.5, 0, 100
                    )

        # --- Energy decay ---
        if n_alive > 0:
            engine.agents.tick_energy()

        # --- Hunger ---
        if n_alive > 0:
            engine.agents.tick_hunger()

        # --- Deaths ---
        deaths_count = 0
        if n_alive > 0:
            deaths_count = engine.agents.check_deaths()

        # --- World regeneration ---
        engine.world.regenerate()

        # --- Pheromone decay ---
        if pheromones is not None:
            pheromones.decay(decay_rate=0.05)

        elapsed = (time.perf_counter() - start) * 1000.0
        post_alive = engine.agents.active_count
        births_count = max(0, post_alive - pre_alive)
        actual_deaths = max(deaths_count, pre_alive - post_alive)

        tick_times.append(elapsed)
        memory_usages.append(engine.agents.memory_usage_mb)
        per_tick_births.append(births_count)
        per_tick_deaths.append(actual_deaths)

        pre_alive = post_alive

    return _compile_metrics(tick_times, memory_usages, per_tick_births,
                            per_tick_deaths, engine)


def run_benchmark(
    agent_counts: List[int] = None,
    ticks: int = 100,
    enable_pheromones: bool = False,
    enable_advanced_behaviors: bool = False,
    verbose: bool = False,
) -> dict:
    """Run benchmark suites across multiple agent counts.

    Args:
        agent_counts: List of population sizes to test.
        ticks: Number of simulation ticks per test.
        enable_pheromones: Toggle pheromone system.
        enable_advanced_behaviors: Toggle advanced behaviors.
        verbose: Print progress messages.

    Returns:
        Dict with config, results (per population dict), and summary.
    """
    if agent_counts is None:
        agent_counts = [1000, 5000, 10000, 25000, 50000]

    results = {}

    for count in agent_counts:
        if verbose:
            print(f"  [{count} agents x {ticks} ticks] ...", end="", flush=True)

        metrics = run_benchmark_sync(
            count, ticks, enable_pheromones, enable_advanced_behaviors
        )
        results[count] = metrics

        if verbose:
            tps = metrics["ticks_per_second"]
            print(f" {tps:.1f} ticks/s, mean {metrics['mean_tick_ms']:.1f}ms")

    summary = {
        "populations_tested": sorted(results.keys()),
        "total_benchmarks": len(results),
        "tps_by_population": {
            k: v["ticks_per_second"] for k, v in results.items()
        },
        "mean_tick_ms_by_population": {
            k: v["mean_tick_ms"] for k, v in results.items()
        },
    }

    return {
        "config": {
            "agent_counts": agent_counts,
            "ticks": ticks,
            "enable_pheromones": enable_pheromones,
            "enable_advanced_behaviors": enable_advanced_behaviors,
        },
        "results": results,
        "summary": summary,
    }


def save_report(report: dict, filepath: str) -> None:
    """Save benchmark report as JSON."""
    def _walk(o):
        if isinstance(o, dict):
            return {k: _walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_walk(i) for i in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return o

    json.dump(_walk(report), open(filepath, "w"), indent=2)
