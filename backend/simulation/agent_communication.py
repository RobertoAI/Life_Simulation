"""Agent communication system: pheromone trails on the simulation grid.

All agents can deposit and sense pheromones as they move across the world.
Pheromones decay over time, creating scent trails that influence
agent decision-making.

Pheromone types:
    0 = food_found    -- deposited near food sources
    1 = danger        -- deposited when fleeing or in dangerous areas
    2 = mate_signal   -- deposited when seeking a mate

Vectorized implementation using numpy grid arrays.
"""

import numpy as np


class PheromoneMap:
    """Grid of pheromone data: (type, intensity, age) per cell.

    Uses separate numpy arrays for each attribute to keep operations
    fully vectorized and memory-efficient.
    """

    # Pheromone type constants
    FOOD_FOUND = 0
    DANGER = 1
    MATE_SIGNAL = 2
    TYPE_COUNT = 3

    def __init__(self, width: int, height: int):
        """Create an empty pheromone map.

        Args:
            width: Grid width in cells.
            height: Grid height in cells.
        """
        self.width = width
        self.height = height

        # Pheromone intensity grid per type: shape (TYPE_COUNT, width, height)
        self.intensity: np.ndarray = np.zeros(
            (self.TYPE_COUNT, width, height), dtype=np.float32
        )

        # Age grid: tracks how many ticks since last deposit for each type
        # shape (TYPE_COUNT, width, height)
        self.age: np.ndarray = np.zeros(
            (self.TYPE_COUNT, width, height), dtype=np.float32
        )

        # Whether a cell has any pheromone for fast emptiness check
        self._has_pheromone: np.ndarray = np.zeros(
            (width, height), dtype=bool
        )

    def deposit_pheromones(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        pheromone_type: int,
        intensity: float = 0.5,
    ) -> None:
        """Deposit pheromones at agent positions.

        This is called when agents move, eat, find danger, etc.

        Args:
            positions_x: X coordinates of agents (1D numpy array).
            positions_y: Y coordinates of agents (1D numpy array).
            pheromone_type: One of FOOD_FOUND, DANGER, MATE_SIGNAL.
            intensity: Intensity of the deposited pheromone (0.0 - 1.0).
        """
        if len(positions_x) == 0:
            return

        # Clamp positions to valid range
        px = np.clip(positions_x, 0, self.width - 1).astype(np.int32)
        py = np.clip(positions_y, 0, self.height - 1).astype(np.int32)

        # Add intensity (accumulates up to 1.0)
        type_grid = self.intensity[pheromone_type]
        type_grid[px, py] = np.minimum(type_grid[px, py] + intensity, 1.0)

        # Reset age for those cells
        self.age[pheromone_type, px, py] = 0.0

        # Update has_pheromone flag
        self._has_pheromone = np.any(self.intensity > 0.01, axis=0)

    def deposit_around(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        pheromone_type: int,
        intensity: float = 0.5,
        radius: int = 2,
    ) -> None:
        """Deposit pheromones in a radius around positions.

        Useful for creating broader scent trails rather than point deposits.

        Args:
            positions_x: X coordinates (1D array).
            positions_y: Y coordinates (1D array).
            pheromone_type: Pheromone type.
            intensity: Base intensity at center.
            radius: How many cells around to spread.
        """
        if len(positions_x) == 0 or radius <= 0:
            return

        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                dist = abs(dx) + abs(dy)  # Manhattan distance
                if dist > radius:
                    continue
                falloff = 1.0 - (dist / (radius + 1))
                self.deposit_pheromones(
                    positions_x + dx,
                    positions_y + dy,
                    pheromone_type,
                    intensity * falloff,
                )

    def decay(self, decay_rate: float = 0.05) -> None:
        """Apply decay to all pheromone grids.

        Each tick, pheromone intensity decreases by decay_rate.
        Very low intensity pheromones are zeroed out.

        Args:
            decay_rate: Fraction of intensity lost per tick (0.0 - 1.0).
        """
        # Decay intensities
        self.intensity *= (1.0 - decay_rate)

        # Zero out very weak pheromones
        self.intensity[self.intensity < 0.001] = 0.0

        # Age increases by 1 for any non-zero cell
        self.age += 1.0
        self.age[self.intensity < 0.001] = 0.0

        # Update has_pheromone
        self._has_pheromone = np.any(self.intensity > 0.01, axis=0)

    def sense_pheromones(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        pheromone_type: int,
        radius: int = 3,
    ) -> np.ndarray:
        """Sense pheromone intensity around agent positions.

        Returns the sum of detected pheromone intensity within radius.

        Args:
            positions_x: X coordinates (1D array).
            positions_y: Y coordinates (1D array).
            pheromone_type: Which pheromone type to sense.
            radius: Sensing radius.

        Returns:
            1D array of sensed intensity per agent.
        """
        n = len(positions_x)
        if n == 0:
            return np.zeros(0, dtype=np.float32)

        px = np.clip(positions_x, 0, self.width - 1).astype(np.int32)
        py = np.clip(positions_y, 0, self.height - 1).astype(np.int32)

        type_grid = self.intensity[pheromone_type]

        # Sample at exact position
        sensed = type_grid[px, py].copy()

        # Add contributions from neighbors within radius
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                dist = abs(dx) + abs(dy)
                if dist == 0 or dist > radius:
                    continue
                weight = 1.0 / (dist + 1)
                sx = np.clip(px + dx, 0, self.width - 1)
                sy = np.clip(py + dy, 0, self.height - 1)
                sensed += type_grid[sx, sy] * weight

        return sensed.astype(np.float32)

    def get_all_type_sense(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        radius: int = 3,
    ) -> dict:
        """Sense all pheromone types at once.

        Args:
            positions_x: X coordinates (1D array).
            positions_y: Y coordinates (1D array).
            radius: Sensing radius.

        Returns:
            Dict with 'food_found', 'danger', 'mate_signal' sensed values.
        """
        return {
            "food_found": self.sense_pheromones(
                positions_x, positions_y, self.FOOD_FOUND, radius
            ),
            "danger": self.sense_pheromones(
                positions_x, positions_y, self.DANGER, radius
            ),
            "mate_signal": self.sense_pheromones(
                positions_x, positions_y, self.MATE_SIGNAL, radius
            ),
        }

    def get_pheromone_direction(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        pheromone_type: int,
        radius: int = 5,
    ) -> tuple:
        """Find the direction of strongest pheromone signal.

        Returns a unit vector pointing toward the highest intensity.

        Args:
            positions_x: X positions (1D array).
            positions_y: Y positions (1D array).
            pheromone_type: Which pheromone type.
            radius: Search radius.

        Returns:
            Tuple of (dir_x, dir_y) arrays as floating point unit vectors.
        """
        n = len(positions_x)
        if n == 0:
            return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)

        # Sample pheromone in all directions
        max_intensity = np.zeros(n, dtype=np.float32)
        dir_x = np.zeros(n, dtype=np.float32)
        dir_y = np.zeros(n, dtype=np.float32)

        px = np.clip(positions_x, 0, self.width - 1).astype(np.int32)
        py = np.clip(positions_y, 0, self.height - 1).astype(np.int32)

        type_grid = self.intensity[pheromone_type]

        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                dist = abs(dx) + abs(dy)
                if dist == 0 or dist > radius:
                    continue
                sx = np.clip(px + dx, 0, self.width - 1)
                sy = np.clip(py + dy, 0, self.height - 1)
                val = type_grid[sx, sy] / (dist + 1)

                update = val > max_intensity
                max_intensity[update] = val[update]
                dx_float = float(dx) / max(dist, 1)
                dy_float = float(dy) / max(dist, 1)
                dir_x[update] = dx_float
                dir_y[update] = dy_float

        return dir_x, dir_y

    def clear(self) -> None:
        """Reset all pheromone data."""
        self.intensity[:] = 0.0
        self.age[:] = 0.0
        self._has_pheromone[:] = False

    def get_grid_view(self) -> np.ndarray:
        """Return a combined pheromone intensity grid for visualization.

        Returns:
            2D array of shape (width, height) with summed intensities.
        """
        return self.intensity.sum(axis=0)
