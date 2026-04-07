"""World grid - 2D terrain, resources, temperature, humidity."""

import numpy as np


class World:
    """Represents the 2D simulation world grid."""

    # Terrain type constants
    TERRAIN_TYPES = {0: "water", 1: "plains", 2: "forest", 3: "mountain", 4: "desert"}

    # Terrain colors as RGBA tuples for frontend rendering
    TERRAIN_COLORS = {
        "water": (26, 58, 92, 255),
        "plains": (74, 124, 63, 255),
        "forest": (45, 90, 30, 255),
        "mountain": (139, 125, 107, 255),
        "desert": (212, 164, 86, 255),
    }

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # Grid: integer terrain types
        self.grid = np.zeros((width, height), dtype=np.int32)
        # Resources: float values 0.0 - 1.0
        self.resources = np.zeros((width, height), dtype=np.float32)
        # Temperature: float values
        self.temperature = np.zeros((width, height), dtype=np.float32)
        # Humidity: float values 0.0 - 1.0
        self.humidity = np.zeros((width, height), dtype=np.float32)

    def generate(self) -> None:
        """Generate the world terrain with noise-based distribution.

        Distribution targets: 15% water, 35% plains, 25% forest, 15% mountain, 10% desert.
        Uses random noise with Gaussian blur for natural-looking clusters.
        """
        # Step 1: Generate raw noise
        noise = np.random.normal(0, 1, (self.width, self.height)).astype(np.float32)

        # Step 2: Smooth with Gaussian-like kernel (simple box blur, applied twice for gaussian effect)
        noise = self._gaussian_blur(noise, kernel=3)
        noise = self._gaussian_blur(noise, kernel=3)

        # Step 3: Normalize to 0..1
        noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-8)

        # Step 4: Map to terrain types using cumulative distribution thresholds
        # water=0: 0-0.15, plains=1: 0.15-0.50, forest=2: 0.50-0.75, mountain=3: 0.75-0.90, desert=4: 0.90-1.0
        self.grid = np.where(noise < 0.15, 0, self.grid)  # water
        self.grid = np.where((noise >= 0.15) & (noise < 0.50), 1, self.grid)  # plains
        self.grid = np.where((noise >= 0.50) & (noise < 0.75), 2, self.grid)  # forest
        self.grid = np.where((noise >= 0.75) & (noise < 0.90), 3, self.grid)  # mountain
        self.grid = np.where(noise >= 0.90, 4, self.grid)  # desert
        self.grid = self.grid.astype(np.int32)

        # Step 5: Initialize resources based on terrain type
        self._init_resources(noise)

        # Step 6: Initialize temperature and humidity based on terrain
        self._init_climate(noise)

    def regenerate(self) -> None:
        """Regenerate resources for this tick, respecting per-terrain caps."""
        resource_caps = {0: 0.1, 1: 0.8, 2: 0.9, 3: 0.3, 4: 0.2}
        regen_rates = {0: 0.0, 1: 0.02, 2: 0.015, 3: 0.005, 4: 0.008}

        for terrain_id, (cap, rate) in zip(
            resource_caps.keys(), zip(resource_caps.values(), regen_rates.values())
        ):
            mask = self.grid == terrain_id
            self.resources[mask] = np.minimum(
                self.resources[mask] + rate, cap
            )

    def get_map_data(self) -> list:
        """Return terrain grid as a nested list for the frontend.

        Returns:
            List of lists with integer terrain types.
        """
        return self.grid.tolist()

    def get_resource_map(self) -> list:
        """Return resource grid as a nested list for the heatmap.

        Returns:
            List of lists with float resource values (0-1).
        """
        return self.resources.tolist()

    def get_terrain_color_grid(self) -> np.ndarray:
        """Return RGBA color grid for the entire terrain.

        Returns:
            numpy array of shape [width, height, 4] with RGBA values.
        """
        # Build color lookup table
        lut = np.array(
            [
                self.TERRAIN_COLORS["water"],      # 0
                self.TERRAIN_COLORS["plains"],     # 1
                self.TERRAIN_COLORS["forest"],     # 2
                self.TERRAIN_COLORS["mountain"],   # 3
                self.TERRAIN_COLORS["desert"],     # 4
            ],
            dtype=np.uint8,
        )

        # Map grid values to colors via lookup table
        color_grid = lut[self.grid]
        return color_grid  # shape: [width, height, 4]

    # --- Methods not used directly but useful for climate/resource logic ---

    def _init_resources(self, noise: np.ndarray) -> None:
        """Set initial resource amounts based on terrain type."""
        resource_amounts = {0: 0.1, 1: 0.5, 2: 0.7, 3: 0.2, 4: 0.15}
        for terrain_id, amount in resource_amounts.items():
            mask = self.grid == terrain_id
            # Add some random variation
            variation = np.random.uniform(-0.1, 0.1, mask.sum())
            self.resources[mask] = np.clip(amount + variation, 0.0, 1.0)

    def _init_climate(self, noise: np.ndarray) -> None:
        """Set temperature and humidity based on terrain type."""
        # Temperature: water and mountain are cooler, desert is hotter
        temp_map = {0: 0.3, 1: 0.6, 2: 0.5, 3: 0.2, 4: 0.9}
        # Humidity: water is wet, desert is dry
        humid_map = {0: 0.9, 1: 0.6, 2: 0.7, 3: 0.3, 4: 0.1}

        for terrain_id in self.TERRAIN_TYPES:
            mask = self.grid == terrain_id
            variation = np.random.uniform(-0.05, 0.05, mask.sum())
            self.temperature[mask] = np.clip(
                temp_map[terrain_id] + variation, 0.0, 1.0
            ).astype(np.float32)
            self.humidity[mask] = np.clip(
                humid_map[terrain_id] + variation, 0.0, 1.0
            ).astype(np.float32)

    @staticmethod
    def _gaussian_blur(arr: np.ndarray, kernel: int = 3) -> np.ndarray:
        """Apply a simple box blur as approximation of Gaussian blur."""
        k = kernel
        pad = k // 2
        padded = np.pad(arr, pad, mode="edge")
        result = np.zeros_like(arr)
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                result[i, j] = np.mean(
                    padded[i : i + k, j : j + k]
                )
        return result
