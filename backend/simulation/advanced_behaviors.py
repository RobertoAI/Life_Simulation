"""Advanced agent behaviors driven by personality and environment.

All functions operate on vectorized numpy arrays and follow the same
structure as the existing decision system.

Implemented behaviors:
    - Pack formation: high agreeableness + extraversion agents cluster
    - Territorial defense: aggressive agents defend their area
    - Migration: agents move toward better resource areas when local resources depleted
    - Hibernation: agents rest longer in cold environments

Each behavior can integrate with the decision system by modifying
action choices or providing behavioral overrides.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Pack Behavior
# ---------------------------------------------------------------------------

def compute_pack_affinity(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    agreeableness: np.ndarray,
    extraversion: np.ndarray,
    pack_threshold: float = 0.6,
) -> tuple:
    """Identify agents that should form packs and their group centers.

    Agents with high agreeableness AND high extraversion tend to cluster.
    Returns a membership mask and group center positions.

    Args:
        positions_x: X coordinates (1D array).
        positions_y: Y coordinates (1D array).
        agreeableness: Agreeableness values [0, 1].
        extraversion: Extraversion values [0, 1].
        pack_threshold: Minimum combined score to qualify for pack behavior.

    Returns:
        Tuple of (pack_mask, group_center_x, group_center_y) where pack_mask
        is a boolean array and centers are mean positions of pack members.
    """
    n = len(positions_x)
    if n == 0:
        return np.zeros(0, dtype=bool), np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    # Pack affinity score
    pack_score = 0.5 * agreeableness + 0.5 * extraversion
    pack_mask = pack_score >= pack_threshold

    if not np.any(pack_mask):
        return pack_mask, np.array([], dtype=np.float32), np.array([], dtype=np.float32)

    # Compute group center (mean position of pack members)
    group_center_x = np.mean(positions_x[pack_mask])
    group_center_y = np.mean(positions_y[pack_mask])

    return pack_mask, np.array([group_center_x], dtype=np.float32), np.array([group_center_y], dtype=np.float32)


# --- Alias for test compatibility ---

def apply_pack_behavior(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    agreeableness: np.ndarray,
    extraversion: np.ndarray,
    world_width: int,
    world_height: int,
    pack_threshold: float = 0.6,
    pack_strength: float = 0.3,
) -> tuple:
    """Convenience wrapper: computes pack affinity and applies movement in one call.

    Args:
        positions_x: X coordinates (1D array).
        positions_y: Y coordinates (1D array).
        agreeableness: Values [0, 1].
        extraversion: Values [0, 1].
        world_width: Grid width.
        world_height: Grid height.
        pack_threshold: Minimum combined score to join pack.
        pack_strength: Movement strength toward group center.

    Returns:
        Tuple of (new_positions_x, new_positions_y).
    """
    pack_mask, cx, cy = compute_pack_affinity(
        positions_x, positions_y, agreeableness, extraversion, pack_threshold
    )
    return apply_pack_movement(
        positions_x, positions_y, pack_mask, cx, cy,
        world_width, world_height, pack_strength,
    )


def apply_pack_movement(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    pack_mask: np.ndarray,
    group_center_x: np.ndarray,
    group_center_y: np.ndarray,
    world_width: int,
    world_height: int,
    pack_strength: float = 0.3,
) -> tuple:
    """Move pack members toward their group center.

    Args:
        positions_x: Current X positions.
        positions_y: Current Y positions.
        pack_mask: Boolean mask of pack members.
        group_center_x: X coordinate of pack center (scalar or 1D).
        group_center_y: Y coordinate of pack center (scalar or 1D).
        world_width: World width for wrapping.
        world_height: World height for wrapping.
        pack_strength: How strongly pack members move toward center.

    Returns:
        New (positions_x, positions_y) with pack adjustments applied.
    """
    if len(pack_mask) == 0 or not np.any(pack_mask):
        return positions_x.copy(), positions_y.copy()

    new_x = positions_x.copy()
    new_y = positions_y.copy()

    cx = float(np.mean(group_center_x))
    cy = float(np.mean(group_center_y))

    pack_indices = np.flatnonzero(pack_mask)

    # Vector toward center
    dx = cx - new_x[pack_indices]
    dy = cy - new_y[pack_indices]

    # Move fraction toward center
    new_x[pack_indices] = np.clip(
        new_x[pack_indices] + dx * pack_strength,
        0, world_width - 1
    ).astype(np.int32)

    new_y[pack_indices] = np.clip(
        new_y[pack_indices] + dy * pack_strength,
        0, world_height - 1
    ).astype(np.int32)

    return new_x, new_y


# ---------------------------------------------------------------------------
# Territorial Behavior
# ---------------------------------------------------------------------------

# Territory records: {agent_index: (territory_center_x, territory_center_y, territory_radius)}
_territory_map: dict = {}


def apply_territorial_behavior(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    aggression: np.ndarray,
    energy: np.ndarray,
    world_width: int,
    world_height: int,
    aggression_threshold: float = 0.7,
    territory_radius: int = 8,
    defense_radius: int = 5,
) -> dict:
    """Apply territorial behavior to aggressive agents.

    Aggressive agents claim territory and defend it against intruders.
    Intruders within territory take energy penalty.

    Args:
        positions_x: X positions.
        positions_y: Y positions.
        aggression: Aggression genomes [0, 1].
        energy: Energy levels [0, 100].
        world_width: World width.
        world_height: World height.
        aggression_threshold: Minimum aggression to claim territory.
        territory_radius: Size of claimed territory.
        defense_radius: Radius at which territory owner attacks intruders.

    Returns:
        Dict with 'territory_owners', 'intruder_penalties', 'confrontations'.
    """
    n = len(positions_x)
    territory_owners = np.zeros(n, dtype=bool)
    intruder_penalty = np.zeros(n, dtype=np.float32)
    confrontations = 0

    # Identify territory owners
    owner_mask = aggression >= aggression_threshold
    owner_indices = np.flatnonzero(owner_mask)

    for oid in owner_indices:
        ox = positions_x[oid]
        oy = positions_y[oid]

        # Find nearby non-owner agents (potential intruders)
        dx = positions_x - ox
        dy = positions_y - oy
        dist_sq = dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2

        # Mark territory owner
        territory_owners[oid] = True

        # Detect intruders within territory (but not self)
        in_range = (dist_sq <= territory_radius ** 2) & ~owner_mask & (dist_sq > 0)
        intruder_indices = np.flatnonzero(in_range)

        if len(intruder_indices) == 0:
            continue

        # In defense radius: stronger penalty (confrontation)
        in_defense = dist_sq[intruder_indices] <= defense_radius ** 2
        confrontations += int(np.sum(in_defense))

        # Penalty scales with distance (closer = worse) and owner aggression
        dists = np.sqrt(dist_sq[intruder_indices])
        penalty_factor = aggression[oid] * (1.0 - dists / territory_radius)
        intruder_penalty[intruder_indices] += penalty_factor * 5.0

    return {
        "territory_owners": territory_owners,
        "intruder_penalties": intruder_penalty,
        "confrontations": confrontations,
    }


# ---------------------------------------------------------------------------
# Migration Behavior
# ---------------------------------------------------------------------------

def compute_migration_direction(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    local_resources: np.ndarray,
    resource_grid: np.ndarray,
    world_width: int,
    world_height: int,
    migration_threshold: float = 0.2,
    search_range: int = 20,
) -> tuple:
    """Compute migration direction toward better resource areas.

    When an agent's local resource is below threshold, it looks for
    better areas further away.

    Args:
        positions_x: X positions.
        positions_y: Y positions.
        local_resources: Resource values at agent positions.
        resource_grid: Full 2D resource grid.
        world_width: World width.
        world_height: World height.
        migration_threshold: Resource level below which agents consider migrating.
        search_range: How far to look for better resources.

    Returns:
        Tuple of (migration_mask, dir_x, dir_y) where migration_mask indicates
        agents that should migrate, and dir_x/dir_y are movement vectors.
    """
    n = len(positions_x)
    migration_mask = local_resources < migration_threshold

    dir_x = np.zeros(n, dtype=np.float32)
    dir_y = np.zeros(n, dtype=np.float32)

    if not np.any(migration_mask):
        return migration_mask, dir_x, dir_y

    mig_indices = np.flatnonzero(migration_mask)

    # For each migrating agent, find direction of best resources within range
    for idx in mig_indices:
        px = int(positions_x[idx])
        py = int(positions_y[idx])

        # Search window (bounded by world limits)
        x_min = max(0, px - search_range)
        x_max = min(world_width - 1, px + search_range)
        y_min = max(0, py - search_range)
        y_max = min(world_height - 1, py + search_range)

        # Get resource patch
        patch = resource_grid[x_min:x_max+1, y_min:y_max+1]

        # Find best cell in patch
        best = np.unravel_index(np.argmax(patch), patch.shape)
        best_abs_x = x_min + best[0]
        best_abs_y = y_min + best[1]

        # Direction vector
        delta_x = best_abs_x - px
        delta_y = best_abs_y - py
        dist = max(np.sqrt(delta_x**2 + delta_y**2), 1.0)

        dir_x[idx] = delta_x / dist
        dir_y[idx] = delta_y / dist

    return migration_mask, dir_x, dir_y


def apply_migration(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    migration_mask: np.ndarray,
    dir_x: np.ndarray,
    dir_y: np.ndarray,
    world_width: int,
    world_height: int,
    speed: int = 2,
) -> tuple:
    """Apply migration movement to agents flagged for migration.

    Args:
        positions_x: Current X positions.
        positions_y: Current Y positions.
        migration_mask: Boolean mask of migrating agents.
        dir_x: Direction X components.
        dir_y: Direction Y components.
        world_width: World width.
        world_height: World height.
        speed: Migration speed (cells per tick).

    Returns:
        New (positions_x, positions_y) after migration.
    """
    new_x = positions_x.copy()
    new_y = positions_y.copy()

    mig_indices = np.flatnonzero(migration_mask)

    if len(mig_indices) == 0:
        return new_x, new_y

    new_x[mig_indices] = np.clip(
        new_x[mig_indices] + (dir_x[mig_indices] * speed).astype(np.int32),
        0, world_width - 1
    )

    new_y[mig_indices] = np.clip(
        new_y[mig_indices] + (dir_y[mig_indices] * speed).astype(np.int32),
        0, world_height - 1
    )

    return new_x, new_y


# ---------------------------------------------------------------------------
# Hibernation Behavior
# ---------------------------------------------------------------------------

def compute_hibernation_prob(
    local_temperature: np.ndarray,
    energy: np.ndarray,
    metabolism: np.ndarray,
    cold_threshold: float = 0.3,
) -> np.ndarray:
    """Compute probability of hibernation for each agent.

    Agents hibernate when temperature is below threshold and energy is
    sufficient to survive rest. Higher metabolism reduces hibernation chance.

    Args:
        local_temperature: Temperature at agent positions [0, 1].
        energy: Energy levels [0, 100].
        metabolism: Genome metabolism [0, 1].
        cold_threshold: Temperature below which agents consider hibernation.

    Returns:
        Array of hibernation probabilities [0, 1] per agent.
    """
    # Cold factor: how cold is it relative to threshold
    cold_factor = np.maximum(0.0, (cold_threshold - local_temperature) / cold_threshold)

    # Energy factor: need enough energy to hibernate
    energy_factor = np.clip((energy - 30.0) / 70.0, 0.0, 1.0)

    # Metabolism reduction: high metabolism agents hibernate less
    metabolism_penalty = 1.0 - metabolism * 0.5

    hibernation_prob = cold_factor * energy_factor * metabolism_penalty

    return np.clip(hibernation_prob, 0.0, 1.0).astype(np.float32)


def apply_hibernation(
    positions_x: np.ndarray,
    positions_y: np.ndarray,
    energy: np.ndarray,
    hunger: np.ndarray,
    hibernation_mask: np.ndarray,
    energy_recovery_rate: float = 3.0,
    hunger_slowdown: float = 0.3,
) -> dict:
    """Apply hibernation effects to sleeping agents.

    Agents gain energy slowly and hunger increases slowly while hibernating.

    Args:
        positions_x: X positions (unchanged during hibernation).
        positions_y: Y positions (unchanged).
        energy: Energy array (modified in place for hibernating agents).
        hunger: Hunger array (modified in place).
        hibernation_mask: Boolean mask of hibernating agents.
        energy_recovery_rate: Energy gained per tick while hibernating.
        hunger_slowdown: Fraction of normal hunger increase.

    Returns:
        Dict with 'hibernation_count' and 'should_awake_mask'.
    """
    hibernating = np.flatnonzero(hibernation_mask)

    if len(hibernating) == 0:
        return {"hibernation_count": 0, "should_awake_mask": np.zeros_like(hibernation_mask)}

    # Energy recovery (slow)
    energy[hibernating] = np.clip(
        energy[hibernating] + energy_recovery_rate,
        0.0, 100.0
    )

    # Hunger still increases but much slower
    # (this would be applied INSTEAD of normal hunger for hibernating agents)
    # We flag this in hunger array but caller should adjust tick_hunger
    hunger[hibernating] = np.maximum(
        hunger[hibernating] - hunger_slowdown, 0.0
    )

    # Awake condition: full energy or hunger too high
    should_awake_mask = np.zeros(len(hibernation_mask), dtype=bool)
    full_energy = energy[hibernating] >= 95.0
    too_hungry = hunger[hibernating] >= 80.0
    awake = full_energy | too_hungry
    should_awake_mask[hibernating[awake]] = True

    return {
        "hibernation_count": len(hibernating),
        "should_awake_mask": should_awake_mask,
    }
