"""Metrics computation for each simulation tick."""

import numpy as np
from datetime import datetime, timezone

from backend.simulation.world import World


def compute_tick_metrics(world: World, tick_count: int) -> dict:
    """Compute aggregate metrics for the current world state.

    Args:
        world: The World instance.
        tick_count: Current tick number.

    Returns:
        Dictionary with aggregated metrics.
    """
    terrain_dist = {}
    for tid, name in World.TERRAIN_TYPES.items():
        count = int(np.sum(world.grid == tid))
        terrain_dist[name] = count

    return {
        "tick": tick_count,
        "total_cells": int(world.width * world.height),
        "avg_resources": float(np.mean(world.resources)),
        "max_resources": float(np.max(world.resources)),
        "min_resources": float(np.min(world.resources)),
        "terrain_distribution": terrain_dist,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
