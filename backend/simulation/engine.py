"""Simulation engine - manages the tick loop and simulation state."""

import asyncio
from datetime import datetime, timezone

import numpy as np

from backend.simulation.agent_state import AgentState
from backend.simulation.decisions import decide
from backend.simulation.metrics import compute_tick_metrics
from backend.simulation.world import World
from backend.simulation.auto_balance import AutoBalancer


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
        self._balance_events: list = []
        self._balance_history: list = []
        # Track agents who chose to rest this tick (skip movement)
        self._resting_mask: np.ndarray | None = None

        # Auto-Balance system
        self.auto_balancer = AutoBalancer(config)

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

    def _compute_perception(self, agents: AgentState) -> dict:
        """Compute perception vectors for alive agents (vectorised).

        Returns a dict with nearby_food, nearby_mates, threat levels.
        Uses a simple grid-based approximation for efficiency.
        """
        alive_mask = agents.alive
        alive_indices = np.flatnonzero(alive_mask)
        n = len(alive_indices)

        if n == 0:
            return {
                "nearby_food": np.array([], dtype=np.float32),
                "nearby_mates": np.array([], dtype=np.float32),
                "threat": np.array([], dtype=np.float32),
            }

        ax = agents.position_x[alive_indices]
        ay = agents.position_y[alive_indices]
        vision = agents.genome_vision[alive_indices].astype(np.float32)

        # Average resource level within vision radius
        # Sample the world resources at each agent's position
        # (vectorized sampling)
        food_at_pos = self.world.resources[ax, ay]
        # Normalize to [0,1] - already the case for world resources

        # Nearby food: resource level at position scaled by vision
        nearby_food = food_at_pos * (vision / 5.0)

        # Count nearby mates (agents within vision range) using a coarse estimate
        # Density-based: population / world_area * vision_area
        world_area = self.world.width * self.world.height
        density = n / max(world_area, 1)
        vision_area = np.pi * vision * vision
        nearby_mates = np.clip(density * vision_area, 0.0, 1.0)

        # Threat: inverse of local resources (depleted area = dangerous)
        threat = np.clip(1.0 - food_at_pos, 0.0, 1.0)

        return {
            "nearby_food": nearby_food.astype(np.float32),
            "nearby_mates": nearby_mates.astype(np.float32),
            "threat": threat.astype(np.float32),
        }

    async def tick(self) -> dict:
        """Execute one simulation tick.

        Returns:
            Dictionary with metrics for this tick.
        """
        self.tick_count += 1
        agents = self.agents
        alive_mask = agents.alive
        alive_indices = np.flatnonzero(alive_mask)
        n_alive = len(alive_indices)

        # Phase 1: Movement
        reset_rest = True
        if not hasattr(self, '_resting_mask') or self._resting_mask is None:
            self._resting_mask = np.zeros(agents.capacity, dtype=bool)
        
        # Reset resting mask from previous tick
        self._resting_mask[:] = False
        
        if n_alive > 0:
            agents.tick_movement(self.world.width, self.world.height)

            # Phase 2: Decision making
            perception = self._compute_perception(agents)
            
            # Gather all decision inputs for alive agents
            hunger = agents.hunger[alive_indices]
            energy = agents.energy[alive_indices]
            fertility = agents.genome_fertility[alive_indices]
            nearby_food = perception["nearby_food"]
            nearby_mates = perception["nearby_mates"]
            threat = perception["threat"]
            
            # Personality traits
            p_openness = agents.personality_openness[alive_indices]
            p_conscientiousness = agents.personality_conscientiousness[alive_indices]
            p_extraversion = agents.personality_extraversion[alive_indices]
            p_agreeableness = agents.personality_agreeableness[alive_indices]
            p_neuroticism = agents.personality_neuroticism[alive_indices]
            intelligence = agents.genome_intelligence[alive_indices]

            # Get positions for distance calculation
            agent_pos_x = agents.position_x[alive_indices].astype(np.float32)
            agent_pos_y = agents.position_y[alive_indices].astype(np.float32)

            # Compute decisions
            actions = decide(
                hunger=hunger,
                energy=energy,
                fertility=fertility,
                nearby_food=nearby_food,
                nearby_mates=nearby_mates,
                threat=threat,
                p_openness=p_openness,
                p_conscientiousness=p_conscientiousness,
                p_extraversion=p_extraversion,
                p_agreeableness=p_agreeableness,
                p_neuroticism=p_neuroticism,
                intelligence=intelligence,
                agent_x=agent_pos_x,
                agent_y=agent_pos_y,
            )

            # Phase 3: Apply decisions to alive agents
            # Action 0: eat - consume resources, gain energy
            eat_mask = actions == 0
            eat_indices = alive_indices[eat_mask]
            if len(eat_indices) > 0:
                eat_pos_x = agents.position_x[eat_indices]
                eat_pos_y = agents.position_y[eat_indices]
                # Consume resources from world
                available = self.world.resources[eat_pos_x, eat_pos_y]
                consumption = np.minimum(available, 0.3)
                self.world.resources[eat_pos_x, eat_pos_y] -= consumption
                # Gain energy proportional to metabolism efficiency
                metabolism_bonus = agents.genome_metabolism[eat_indices]
                energy_gain = consumption * 50.0 * (0.8 + 0.4 * metabolism_bonus)
                agents.energy[eat_indices] = np.clip(
                    agents.energy[eat_indices] + energy_gain, 0.0, 100.0
                )
                # Reduce hunger
                agents.hunger[eat_indices] = np.maximum(
                    agents.hunger[eat_indices] - 10.0, 0.0
                )

            # Action 1: move - already handled by tick_movement, but use genome_speed
            # (movement speed is used for distance, already in tick_movement)
            
            # Action 2: reproduce - use decision instead of random chance
            reproduce_mask = actions == 2
            # Only allow reproduction if energy is above threshold
            reproduce_and_eligible = reproduce_mask & (agents.energy[alive_indices] >= 80.0)
            reproduce_indices = alive_indices[reproduce_and_eligible]
            if len(reproduce_indices) > 0:
                # Check free slots
                free_mask = ~agents.alive
                free_indices = np.flatnonzero(free_mask)
                n_off = min(len(reproduce_indices), len(free_indices))
                if n_off > 0:
                    reproduce_indices = reproduce_indices[:n_off]
                    child_indices = free_indices[:n_off]
                    
                    # Crossover partner selection
                    partner_indices = reproduce_indices[(np.arange(n_off) + 1) % n_off]
                    
                    genes = ["speed", "metabolism", "fertility", "resilience",
                             "aggression", "intelligence", "size"]
                    gene_attrs = [
                        "genome_speed", "genome_metabolism", "genome_fertility",
                        "genome_resilience", "genome_aggression", "genome_intelligence", "genome_size",
                    ]
                    for attr in gene_attrs:
                        p1_vals = getattr(agents, attr)[reproduce_indices]
                        p2_vals = getattr(agents, attr)[partner_indices]
                        allele_choice = np.random.random(n_off) < 0.5
                        child_genome = np.where(allele_choice, p1_vals, p2_vals)
                        mutation_mask = np.random.random(n_off) < 0.05
                        mutation_delta = np.random.uniform(-0.1, 0.1, n_off)
                        child_genome = np.where(mutation_mask,
                                                np.clip(child_genome + mutation_delta, 0.0, 1.0),
                                                child_genome)
                        getattr(agents, attr)[child_indices] = child_genome

                    # Vision range
                    p1_v = agents.genome_vision[reproduce_indices]
                    p2_v = agents.genome_vision[partner_indices]
                    child_v = np.where(np.random.random(n_off) < 0.5, p1_v, p2_v)
                    v_mut = np.random.random(n_off) < 0.05
                    child_v = np.where(v_mut,
                                       np.clip(child_v + np.random.randint(-1, 2, n_off), 1, 10),
                                       child_v)
                    agents.genome_vision[child_indices] = child_v
                    
                    # Personality inheritance
                    p_traits = ["personality_openness", "personality_conscientiousness",
                                "personality_extraversion", "personality_agreeableness",
                                "personality_neuroticism"]
                    for trait_attr in p_traits:
                        t1 = getattr(agents, trait_attr)[reproduce_indices]
                        t2 = getattr(agents, trait_attr)[partner_indices]
                        child_trait = np.clip(0.5 * (t1 + t2) + np.random.normal(0, 0.05, n_off), 0.0, 1.0)
                        getattr(agents, trait_attr)[child_indices] = child_trait
                    
                    parents_energy = agents.energy[reproduce_indices].copy()
                    agents.energy[reproduce_indices] *= 0.5
                    agents.hunger[reproduce_indices] = np.minimum(
                        agents.hunger[reproduce_indices] + 5.0, 100.0
                    )
                    agents.position_x[child_indices] = np.clip(
                        agents.position_x[reproduce_indices] + np.random.randint(-1, 2, n_off, dtype=np.int32),
                        0, self.world.width - 1,
                    )
                    agents.position_y[child_indices] = np.clip(
                        agents.position_y[reproduce_indices] + np.random.randint(-1, 2, n_off, dtype=np.int32),
                        0, self.world.height - 1,
                    )
                    agents.energy[child_indices] = parents_energy
                    agents.hunger[child_indices] = 0.0
                    agents.health[child_indices] = 100.0
                    agents.age[child_indices] = 0
                    agents.parent_ids[child_indices] = agents.agent_ids[reproduce_indices]
                    agents.generation[child_indices] = agents.generation[reproduce_indices] + 1
                    new_ids = np.arange(agents._next_id, agents._next_id + n_off, dtype=np.int32)
                    agents.agent_ids[child_indices] = new_ids
                    agents._next_id += n_off
                    agents.alive[child_indices] = True

            # Action 3: rest - skip movement next tick, recover small energy
            rest_mask = actions == 3
            rest_indices = alive_indices[rest_mask]
            if len(rest_indices) > 0:
                self._resting_mask[rest_indices] = True
                # Recover small energy
                recovery = 2.0 + 1.0 * agents.genome_resilience[rest_indices]
                agents.energy[rest_indices] = np.clip(
                    agents.energy[rest_indices] + recovery, 0.0, 100.0
                )

            # Action 4: flee - move 2-3 cells away from threat
            flee_mask = actions == 4
            flee_indices = alive_indices[flee_mask]
            if len(flee_indices) > 0:
                # Flee direction: away from current position threat source
                # Use nearest resource-depleted cell as threat proxy
                threat_dir_x = np.random.choice([-1, 1], size=len(flee_indices))
                threat_dir_y = np.random.choice([-1, 1], size=len(flee_indices))
                flee_distance = np.random.randint(2, 4, size=len(flee_indices))
                agents.position_x[flee_indices] = np.clip(
                    agents.position_x[flee_indices] + threat_dir_x * flee_distance,
                    0, self.world.width - 1,
                )
                agents.position_y[flee_indices] = np.clip(
                    agents.position_y[flee_indices] + threat_dir_y * flee_distance,
                    0, self.world.height - 1,
                )

            # Action 5: idle - do nothing extra (costs only energy)

            # Phase 4: Energy decay (genome_metabolism aware)
            agents.tick_energy()

            # Phase 5: Hunger
            agents.tick_hunger()

            # Phase 6: Deaths (genome_resilience aware)
            agents.check_deaths()

        # Phase 7: Regenerate world resources
        self.world.regenerate()

        # Phase 8: Auto-Balance check (every 50 ticks)
        balance_events = []
        if self.tick_count % 50 == 0:
            balance_events = self.auto_balancer.check(self.agents, self.world, self.tick_count)
            if balance_events:
                self._balance_events.extend(balance_events)
                self._balance_history.extend(balance_events)
                # Keep only last 100 balance events in current batch
                if len(self._balance_events) > 100:
                    self._balance_events = self._balance_events[-100:]
                # Apply active overrides to simulation
                self._apply_balance_overrides()

        # Compute and store metrics
        metrics = compute_tick_metrics(self.world, self.tick_count)
        metrics["balance_events"] = balance_events
        metrics["balance_overrides"] = self.auto_balancer.get_current_config_overrides()
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

    def _apply_balance_overrides(self) -> None:
        """Apply active auto-balance overrides to the world and agent parameters.

        This is called by the AutoBalancer to apply its adjustments.
        """
        overrides = self.auto_balancer.get_current_config_overrides()

        # Apply regeneration multiplier by adjusting world regeneration rates
        # The world's regenerate() will be called next tick, so we don't
        # directly modify world resources here. Instead, the multiplier is
        # passed to the world when regenerate() is called.
        # For now, we store the multiplier for the world to use.
        regen_multiplier = overrides["resource_regeneration_multiplier"]
        if regen_multiplier != 1.0:
            self.world._regen_multiplier = regen_multiplier

        # Store metabolism and reproduction multipliers as engine-level attrs
        self._metabolism_multiplier = overrides["metabolism_multiplier"]
        self._reproduction_multiplier = overrides["reproduction_chance_multiplier"]
        self._mutation_rate = overrides["mutation_rate_override"]

    def get_balance_history(self) -> list:
        """Return the full history of auto-balance adjustments.

        Returns:
            List of adjustment dicts.
        """
        return self.auto_balancer.get_adjustment_history()

    def get_balance_config(self) -> dict:
        """Return current auto-balance configuration overrides.

        Returns:
            Dict with current override values.
        """
        return self.auto_balancer.get_current_config_overrides()

    def revert_last_balance_adjustment(self) -> dict | None:
        """Revert the most recent auto-balance adjustment.

        Returns:
            Dict of the reverted adjustment, or None if nothing to revert.
        """
        result = self.auto_balancer.revert_last_adjustment()
        if result is not None:
            # Re-apply remaining overrides after revert
            self._apply_balance_overrides()
        return result
