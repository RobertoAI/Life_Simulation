"""Event system for world simulation -- storms, droughts, earthquakes, etc."""

import numpy as np
from typing import Optional

# Event type constants
EVENT_TYPES = ["storm", "drought", "abundance", "cold_wave", "heat_wave", "earthquake"]

# Event definitions: effect_type maps to how the event modifies world grids
EVENT_EFFECTS = {
    "storm": {
        "resource_modifier": -0.20,
        "humidity_modifier": 0.15,
        "temperature_modifier": -0.05,
        "duration": 5,
    },
    "drought": {
        "resource_modifier": -0.30,
        "humidity_modifier": -0.20,
        "temperature_modifier": 0.10,
        "duration": 15,
    },
    "abundance": {
        "resource_modifier": 0.20,
        "humidity_modifier": 0.0,
        "temperature_modifier": 0.0,
        "duration": 8,
    },
    "cold_wave": {
        "resource_modifier": 0.0,
        "humidity_modifier": 0.0,
        "temperature_modifier": -0.15,
        "duration": 10,
    },
    "heat_wave": {
        "resource_modifier": 0.0,
        "humidity_modifier": 0.0,
        "temperature_modifier": 0.15,
        "duration": 10,
    },
    "earthquake": {
        "resource_modifier": -0.10,
        "humidity_modifier": 0.0,
        "temperature_modifier": 0.0,
        "duration": 1,
        "terrain_damage": True,
    },
}


class ActiveEvent:
    """Represents a single active event affecting a circular area of the world."""

    def __init__(
        self,
        event_type: str,
        severity: float,
        center_x: int,
        center_y: int,
        radius: int,
        duration: int,
        effect_type: str,
    ):
        self.type = event_type
        self.severity = severity
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        self.duration = duration
        self.remaining = duration
        self.effect_type = effect_type

    def tick(self) -> bool:
        """Decay the event by one tick. Returns True if still active."""
        self.remaining -= 1
        return self.remaining > 0

    def to_dict(self) -> dict:
        """Serialize for API / WebSocket broadcast."""
        return {
            "type": self.type,
            "severity": float(self.severity),
            "center_x": int(self.center_x),
            "center_y": int(self.center_y),
            "radius": int(self.radius),
            "remaining": int(self.remaining),
            "duration": int(self.duration),
            "effect_type": self.effect_type,
        }


class EventSystem:
    """Manages random environmental events that affect the world grid."""

    def __init__(self, grid_width: int, grid_height: int):
        self.grid_width = grid_width
        self.grid_height = grid_height
        self._active_events: list[ActiveEvent] = []
        self._next_event_tick = self._schedule_next_event()

    def _schedule_next_event(self) -> int:
        """Schedule the next event to fire between 100-300 ticks from now."""
        current_tick = max(
            (e.remaining for e in self._active_events), default=0
        )
        return current_tick + np.random.randint(100, 301)

    def _generate_event(self, tick_count: int) -> Optional[ActiveEvent]:
        """Randomly create an event with a random type and parameters."""
        event_type = np.random.choice(EVENT_TYPES)
        severity = float(np.random.uniform(0.2, 1.0))

        # Event center: random position in grid
        center_x = int(np.random.randint(0, self.grid_width))
        center_y = int(np.random.randint(0, self.grid_height))

        # Radius scales with severity (10-50 cells)
        radius = int(10 + severity * 40)

        effect_def = EVENT_EFFECTS[event_type]
        duration = effect_def["duration"]

        # Earthquake has instantaneous effect
        if event_type == "earthquake":
            duration = 1

        return ActiveEvent(
            event_type=event_type,
            severity=severity,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            duration=duration,
            effect_type=event_type,
        )

    def _get_circular_mask(
        self, center_x: int, center_y: int, radius: int
    ) -> np.ndarray:
        """Create a boolean mask for a circular area centered at (cx, cy)."""
        y_coords, x_coords = np.ogrid[
            0 : self.grid_height, 0 : self.grid_width
        ]
        dist_sq = (x_coords - center_x) ** 2 + (y_coords - center_y) ** 2
        return dist_sq <= radius**2

    def process(
        self,
        grid: np.ndarray,
        temperature: np.ndarray,
        humidity: np.ndarray,
        resources: np.ndarray,
        tick_count: int,
    ) -> list[ActiveEvent]:
        """Process event lifecycle for this tick.

        Updates active events, applies effects to world grids,
        and generates new events when appropriate.

        Args:
            grid: 2D terrain type grid (int).
            temperature: 2D temperature grid (float, 0-1).
            humidity: 2D humidity grid (float, 0-1).
            resources: 2D resource grid (float, 0-1).
            tick_count: Current simulation tick.

        Returns:
            List of currently active events.
        """
        # First, tick down all active events
        self._active_events = [e for e in self._active_events if e.tick()]

        # Check if it's time to generate a new event
        if tick_count >= self._next_event_tick:
            new_event = self._generate_event(tick_count)
            if new_event is not None:
                self._active_events.append(new_event)
                self._next_event_tick = self._schedule_next_event()

        # Apply effects of active events to the world grids
        for event in self._active_events:
            self._apply_event_effects(event, grid, temperature, humidity, resources)

        return self._active_events

    def _apply_event_effects(
        self,
        event: ActiveEvent,
        grid: np.ndarray,
        temperature: np.ndarray,
        humidity: np.ndarray,
        resources: np.ndarray,
    ) -> None:
        """Apply the effects of a single event to the affected area."""
        mask = self._get_circular_mask(
            event.center_x, event.center_y, event.radius
        )
        effect = EVENT_EFFECTS.get(event.type)
        if effect is None:
            return

        severity_factor = event.severity

        # Resource modifier
        res_mod = effect.get("resource_modifier", 0.0)
        if res_mod != 0.0:
            resources[mask] = np.clip(
                resources[mask] + res_mod * severity_factor, 0.0, 1.0
            )

        # Humidity modifier
        humid_mod = effect.get("humidity_modifier", 0.0)
        if humid_mod != 0.0:
            humidity[mask] = np.clip(
                humidity[mask] + humid_mod * severity_factor, 0.0, 1.0
            )

        # Temperature modifier
        temp_mod = effect.get("temperature_modifier", 0.0)
        if temp_mod != 0.0:
            temperature[mask] = np.clip(
                temperature[mask] + temp_mod * severity_factor, 0.0, 1.0
            )

        # Earthquake terrain damage
        if effect.get("terrain_damage", False):
            self._apply_terrain_damage(grid, mask, event.severity)

    def _apply_terrain_damage(
        self, grid: np.ndarray, mask: np.ndarray, severity: float
    ) -> None:
        """Randomly change terrain types in earthquake-affected areas.

        mountain -> plains, forest -> plains, with probability based on severity.
        Other terrain types are unaffected.
        """
        affected = np.flatnonzero(mask)
        if len(affected) == 0:
            return

        # Probability of terrain change per cell scales with severity
        damage_chance = severity * 0.4
        roll = np.random.random(len(affected))
        damaged = affected[roll < damage_chance]

        if len(damaged) == 0:
            return

        # Convert flat indices back to 2D
        y_coords = damaged // self.grid_width
        x_coords = damaged % self.grid_width

        terrain_values = grid[x_coords, y_coords]

        # mountain (3) -> plains (1)
        mountain_mask = terrain_values == 3
        x_m = x_coords[mountain_mask]
        y_m = y_coords[mountain_mask]
        if len(x_m) > 0:
            grid[x_m, y_m] = 1  # plains

        # forest (2) -> plains (1)
        forest_mask = terrain_values == 2
        x_f = x_coords[forest_mask]
        y_f = y_coords[forest_mask]
        if len(x_f) > 0:
            grid[x_f, y_f] = 1  # plains

    def get_active_events(self) -> list[dict]:
        """Return active events as a list of dicts for API / WebSocket."""
        return [e.to_dict() for e in self._active_events]
