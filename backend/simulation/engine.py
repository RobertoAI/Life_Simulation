"""Simulation engine - manages the tick loop and simulation state."""

import asyncio
from datetime import datetime, timezone

from backend.simulation.agent_state import AgentState
from backend.simulation.metrics import compute_tick_metrics
from backend.simulation.world import World


class SimulationEngine:
    """Main simulation engine that drives the world tick loop."""

    def __init__(self, config):
        """Initialize the engine with configuration.

        Args:
            config: Settings object with grid dimensions and timings.
        """
        self.world = World(width=config.grid_width, height=config.grid_height)
        self.world.generate()
        self._config = config
        self.agents = AgentState(max_capacity=config.max_agents)
        self.tick_count = 0
        self.status = "stopped"
        self.speed_multiplier = 1.0
        self.metrics_history: list = []
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the simulation, resetting tick count and spawning agents."""
        if self.status == "running":
            return
        self.status = "running"
        self.tick_count = 0
        self.agents.spawn_batch(
            self._config.initial_population,
            self.world.width,
            self.world.height,
        )
        self._task = asyncio.create_task(self.run_loop())

    async def stop(self) -> None:
        """Stop the simulation."""
        self.status = "stopped"
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def pause(self) -> None:
        """Pause the simulation."""
        if self.status == "running":
            self.status = "paused"
        elif self.status == "paused":
            self.status = "running"

    def set_speed(self, multiplier: float) -> None:
        """Set the simulation speed multiplier.

        Args:
            multiplier: Speed multiplier (0.5, 1.0, 2.0, 5.0, 10.0).
        """
        self.speed_multiplier = max(0.1, multiplier)

    async def tick(self) -> dict:
        """Execute one simulation tick.

        Returns:
            Dictionary with metrics for this tick.
        """
        self.tick_count += 1
        # Agent tick pipeline
        self.agents.tick_movement(self.world.width, self.world.height)
        self.agents.tick_energy()
        self.agents.tick_hunger()
        self.agents.check_deaths()
        self.agents.reproduce(self.world.width, self.world.height)
        # Regenerate world resources
        self.world.regenerate()
        # Compute and store metrics
        metrics = compute_tick_metrics(self.world, self.tick_count)
        self.metrics_history.append(metrics)
        # Keep only the last 100 metrics entries
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        return metrics

    async def run_loop(self) -> None:
        """Main async loop that executes ticks at the configured interval."""
        try:
            while self.status == "running":
                # Base interval is 50ms, adjusted by speed multiplier
                interval_s = 0.05 / self.speed_multiplier
                await self.tick()
                await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            pass

    def get_status(self) -> dict:
        """Return current simulation status information.

        Returns:
            Dictionary with tick count, status, speed, and population.
        """
        return {
            "tick": self.tick_count,
            "status": self.status,
            "speed": self.speed_multiplier,
            "grid_width": self.world.width,
            "grid_height": self.world.height,
            "population": self.agents.active_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_agents_page(self, page: int = 0, per_page: int = 50) -> dict:
        """Return a paginated view of alive agents.

        Args:
            page: Zero-based page number.
            per_page: Number of agents per page.

        Returns:
            Dict with ``page``, ``per_page``, ``total``, ``agents``.
        """
        return self.agents.get_alive_agents_for_api(page=page, per_page=per_page)

    def get_metrics(self) -> list:
        """Return the metrics history (last 100 ticks).

        Returns:
            List of metric dictionaries.
        """
        return self.metrics_history
