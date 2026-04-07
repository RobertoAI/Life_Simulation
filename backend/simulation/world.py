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

    def _gaussian_blur(self, arr: np.ndarray, kernel: int = 3) -> np.ndarray:
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

    def get_terrain_distribution(self) -> dict:
        """Return the distribution of terrain types as percentages.

        Returns:
            Dict mapping terrain type name to percentage (0-100).
        """
        total = self.width * self.height
        counts = np.bincount(self.grid.ravel(), minlength=5)
        return {
            name: float(counts[tid]) / total * 100.0
            for tid, name in self.TERRAIN_TYPES.items()
        }

    # --- Environmental stress and agent query methods ---

    def compute_agent_environmental_stress(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        temperature_grid: np.ndarray,
        humidity_grid: np.ndarray,
    ) -> np.ndarray:
        """Compute environmental stress for each agent position (0-1).

        Stress sources:
        - Too hot: temperature (0-1 scale mapped to -10..50C) above ~35C
        - Too cold: temperature below ~5C
        - Too dry: humidity below 0.2 (20%)

        Args:
            positions_x: X coordinates of agents (1D array).
            positions_y: Y coordinates of agents (1D array).
            temperature_grid: 2D temperature grid (0-1 scale).
            humidity_grid: 2D humidity grid (0-1 scale).

        Returns:
            1D array of stress values (0-1) per agent.
        """
        # Clamp positions to valid range
        px = np.clip(positions_x, 0, self.width - 1).astype(np.int32)
        py = np.clip(positions_y, 0, self.height - 1).astype(np.int32)

        # Sample temperature and humidity at agent positions
        temp_at_pos = temperature_grid[px, py].astype(np.float32)
        humid_at_pos = humidity_grid[px, py].astype(np.float32)

        # Map temperature from 0-1 to Celsius: -10 to 50
        temp_celsius = temp_at_pos * 60.0 - 10.0

        stress = np.zeros(len(positions_x), dtype=np.float32)

        # Heat stress (>35C: linear ramp to max at 50C)
        heat_mask = temp_celsius > 35.0
        heat_stress = np.minimum((temp_celsius - 35.0) / 15.0, 1.0)
        stress[heat_mask] = heat_stress[heat_mask]

        # Cold stress (<5C: linear ramp to max at -10C)
        cold_mask = temp_celsius < 5.0
        cold_stress = np.minimum((5.0 - temp_celsius) / 15.0, 1.0)
        cold_stress_idx = np.maximum(stress, cold_stress)
        stress = np.where(cold_mask, cold_stress_idx, stress)

        # Drought stress (humidity < 0.2: linear ramp to max at 0)
        dry_mask = humid_at_pos < 0.2
        dry_stress = np.maximum(0.0, 1.0 - humid_at_pos / 0.2)
        dry_stress[dry_mask == False] = 0.0

        # Combine: take the maximum of heat/cold stress and dry stress
        stress = np.maximum(stress, dry_stress)

        return np.clip(stress, 0.0, 1.0)

    def get_resource_at_positions(
        self, positions_x: np.ndarray, positions_y: np.ndarray
    ) -> np.ndarray:
        """Return resource values at given agent positions.

        Args:
            positions_x: X coordinates of agents (1D array).
            positions_y: Y coordinates of agents (1D array).

        Returns:
            1D array of resource values at each position.
        """
        px = np.clip(positions_x, 0, self.width - 1).astype(np.int32)
        py = np.clip(positions_y, 0, self.height - 1).astype(np.int32)
        return self.resources[px, py].copy()

    def get_nearest_agents(
        self,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        radius: float,
        world_width: float,
        world_height: float,
    ) -> np.ndarray:
        """Find which agents are within radius of each other.

        Uses pairwise distance for a fully vectorized approach.

        Args:
            positions_x: X coordinates of agents (1D array, shape (N,)).
            positions_y: Y coordinates of agents (1D array, shape (N,)).
            radius: Maximum distance for "nearby" classification.
            world_width: World width for distance normalization (unused, kept for API compat).
            world_height: World height for distance normalization (unused, kept for API compat).

        Returns:
            Boolean matrix of shape (N, N) where True[i,j] means agent j
            is within radius of agent i. Diagonal is excluded (self).
        """
        n = len(positions_x)
        if n == 0:
            return np.zeros((0, 0), dtype=bool)

        # Compute pairwise distances using broadcasting
        dx = positions_x[np.newaxis, :] - positions_x[:, np.newaxis]
        dy = positions_y[np.newaxis, :] - positions_y[:, np.newaxis]
        dist = np.sqrt(dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2)

        within = dist <= radius

        # Exclude self
        np.fill_diagonal(within, False)

        return within

    def get_threat_map(self) -> np.ndarray:
        """Return a 2D array where threatening cells are marked.

        A cell is threatening if:
        - Resources are very low (<0.15)
        - Temperature is extreme (>0.85 or <0.1, roughly >41C or <-4C in our mapping)

        Returns:
            2D int array of shape (width, height):
            0 = safe, 1 = low resources, 2 = extreme temperature, 3 = both.
        """
        threat = np.zeros((self.width, self.height), dtype=np.int8)

        low_resource = self.resources < 0.15
        extreme_temp = (self.temperature > 0.85) | (self.temperature < 0.1)

        threat[low_resource] = 1
        threat[extreme_temp] |= 2

        return threat

    def apply_event_effects_to_agents(
        self,
        events: list,
        positions_x: np.ndarray,
        positions_y: np.ndarray,
        resilience: np.ndarray,
    ) -> tuple:
        """Compute event-based penalties for agents in event areas.

        Agents in event zones take energy and health penalties,
        mitigated by their resilience (0-1, where 1 = fully resistant).

        Args:
            events: List of ActiveEvent objects.
            positions_x: X coordinates of agents (1D array).
            positions_y: Y coordinates of agents (1D array).
            resilience: 1D array of resilience values (0-1) per agent.

        Returns:
            Tuple of (energy_penalty, health_penalty) as 1D arrays.
        """
        energy_penalty = np.zeros(len(positions_x), dtype=np.float32)
        health_penalty = np.zeros(len(positions_x), dtype=np.float32)

        if len(positions_x) == 0:
            return energy_penalty, health_penalty

        px = positions_x.astype(np.int32)
        py = positions_y.astype(np.int32)

        # Penalty scales based on event type
        event_severity_map = {
            "storm": {"energy": 3.0, "health": 2.0},
            "drought": {"energy": 5.0, "health": 4.0},
            "cold_wave": {"energy": 6.0, "health": 5.0},
            "heat_wave": {"energy": 6.0, "health": 5.0},
            "earthquake": {"energy": 4.0, "health": 6.0},
            "abundance": {"energy": -1.0, "health": 1.0},  # abundance gives energy
        }

        for event in events:
            # Handle both ActiveEvent objects and dicts (from get_active_events)
            if isinstance(event, dict):
                center_x = event["center_x"]
                center_y = event["center_y"]
                radius = event["radius"]
                severity_factor = event["severity"]
                event_type = event["type"]
            else:
                center_x = event.center_x
                center_y = event.center_y
                radius = event.radius
                severity_factor = event.severity
                event_type = event.type

            # Circular area mask for each agent
            dx = px - center_x
            dy = py - center_y
            dist_sq = dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2
            in_event = dist_sq <= radius ** 2

            if not np.any(in_event):
                continue

            penalties = event_severity_map.get(event_type, {"energy": 2.0, "health": 2.0})

            # Penalty reduced by resilience
            mitigation = 1.0 - resilience[in_event]

            energy_penalty[in_event] += penalties["energy"] * severity_factor * mitigation
            health_penalty[in_event] += penalties["health"] * severity_factor * mitigation

        return energy_penalty, health_penalty
