"""Simulation engine - manages the tick loop and simulation state."""

import asyncio
import time
from datetime import datetime, timezone

import numpy as np

from backend.simulation.agent_state import AgentState
from backend.simulation.decisions import decide
from backend.simulation.metrics import compute_tick_metrics
from backend.simulation.world import World
from backend.simulation.engine_optimizer import SimulationProfiler
from backend.simulation.auto_balance import AutoBalancer

# Optional advanced feature imports
try:
    from backend.simulation.agent_communication import PheromoneMap
    PHEROMONES_AVAILABLE = True
except ImportError:
    PHEROMONES_AVAILABLE = False

try:
    from backend.simulation import advanced_behaviors as adv
    ADVANCED_BEHAVIORS_AVAILABLE = True
except ImportError:
    ADVANCED_BEHAVIORS_AVAILABLE = False


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
        self._original_max_agents = config.max_agents
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
        # Profiler for per-phase timing
        self.profiler = SimulationProfiler()
        # Tick history: stores (tick_number, duration_ms, agent_count, births, deaths) last 1000
        self.tick_history: list = []

        # Auto-Balance system
        self.auto_balancer = AutoBalancer(config)

        # --- Advanced Features (opt-in, disabled by default) ---
        self._enable_pheromones = getattr(config, "enable_pheromones", False)
        self._enable_advanced_behaviors = getattr(config, "enable_advanced_behaviors", False)

        self.pheromones = None
        if self._enable_pheromones and PHEROMONES_AVAILABLE:
            self.pheromones = PheromoneMap(self.world.width, self.world.height)

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
        """Execute one simulation tick with per-phase profiling.

        Returns:
            Dictionary with metrics for this tick.
        """
        self.tick_count += 1
        agents = self.agents

        # Start profiler for this tick
        self.profiler.start_tick()

        # Pre-allocate resting mask once
        if self._resting_mask is None:
            self._resting_mask = np.zeros(agents.capacity, dtype=bool)
        self._resting_mask[:] = False

        # Track births/deaths for tick history
        pre_alive_count = agents.active_count
        births = 0
        deaths = 0

        # ---- Phase 1: Movement ----
        t0 = time.perf_counter()
        alive_mask = agents.alive
        alive_indices = np.flatnonzero(alive_mask)
        n_alive = len(alive_indices)
        if n_alive > 0:
            agents.tick_movement(self.world.width, self.world.height)

            # ---- Phase 1.5: Pheromone trails (after movement) ----
            if self._enable_pheromones and self.pheromones is not None:
                self.pheromones.deposit_pheromones(
                    agents.position_x[alive_indices].astype(np.int32),
                    agents.position_y[alive_indices].astype(np.int32),
                    PheromoneMap.FOOD_FOUND,
                    intensity=0.08,
                )

        t1 = time.perf_counter()
        self.profiler.record_phase("movement", (t1 - t0) * 1000.0)

        # ---- Phase 2: Decision making ----
        t0 = time.perf_counter()
        if n_alive > 0:
            perception = self._compute_perception(agents)

            # Augment perception with pheromone signals
            if self._enable_pheromones and self.pheromones is not None:
                pheromone_sense = self.pheromones.get_all_type_sense(
                    agents.position_x[alive_indices].astype(np.int32),
                    agents.position_y[alive_indices].astype(np.int32),
                    radius=3,
                )
                perception["pheromone_food"] = pheromone_sense["food_found"]
                perception["pheromone_danger"] = pheromone_sense["danger"]
                perception["pheromone_mates"] = pheromone_sense["mate_signal"]
            else:
                perception["pheromone_food"] = np.zeros(n_alive, dtype=np.float32)
                perception["pheromone_danger"] = np.zeros(n_alive, dtype=np.float32)
                perception["pheromone_mates"] = np.zeros(n_alive, dtype=np.float32)

            # ---- Advanced behaviors: modify perception for decisions ----
            if self._enable_advanced_behaviors and ADVANCED_BEHAVIORS_AVAILABLE:
                # Pack behavior: nearby mates boosted by agreeableness
                pack_boost = agents.personality_agreeableness[alive_indices] * agents.personality_extraversion[alive_indices]
                perception["nearby_mates"] = np.clip(
                    perception["nearby_mates"] + 0.3 * pack_boost, 0.0, 1.0
                )

            hunger = agents.hunger[alive_indices]
            energy = agents.energy[alive_indices]
            fertility = agents.genome_fertility[alive_indices]
            nearby_food = perception["nearby_food"]
            nearby_mates = perception["nearby_mates"]
            threat = perception["threat"]
            p_openness = agents.personality_openness[alive_indices]
            p_conscientiousness = agents.personality_conscientiousness[alive_indices]
            p_extraversion = agents.personality_extraversion[alive_indices]
            p_agreeableness = agents.personality_agreeableness[alive_indices]
            p_neuroticism = agents.personality_neuroticism[alive_indices]
            intelligence = agents.genome_intelligence[alive_indices]
            agent_pos_x = agents.position_x[alive_indices].astype(np.float32)
            agent_pos_y = agents.position_y[alive_indices].astype(np.float32)

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
        else:
            actions = np.array([], dtype=np.int32)
        t1 = time.perf_counter()
        self.profiler.record_phase("decisions", (t1 - t0) * 1000.0)

        # ---- Phase 3: Apply decisions (vectorized, no Python loops) ----
        # Start profiler for reproduction tracking separately
        t0 = time.perf_counter()
        if n_alive > 0:
            # Action 0: eat - consume resources, gain energy
            eat_mask = actions == 0
            eat_indices = alive_indices[eat_mask]
            if len(eat_indices) > 0:
                eat_pos_x = agents.position_x[eat_indices]
                eat_pos_y = agents.position_y[eat_indices]
                available = self.world.resources[eat_pos_x, eat_pos_y]
                consumption = np.minimum(available, 0.3)
                self.world.resources[eat_pos_x, eat_pos_y] -= consumption
                metabolism_bonus = agents.genome_metabolism[eat_indices]
                energy_gain = consumption * 50.0 * (0.8 + 0.4 * metabolism_bonus)
                agents.energy[eat_indices] = np.clip(
                    agents.energy[eat_indices] + energy_gain, 0.0, 100.0
                )
                agents.hunger[eat_indices] = np.maximum(
                    agents.hunger[eat_indices] - 10.0, 0.0
                )

            # Action 2: reproduce - batch spawn (vectorized)
            reproduce_mask = actions == 2
            reproduce_and_eligible = reproduce_mask & (agents.energy[alive_indices] >= 80.0)
            reproduce_indices = alive_indices[reproduce_and_eligible]
            if len(reproduce_indices) > 0:
                free_mask = ~agents.alive
                free_indices = np.flatnonzero(free_mask)
                n_off = min(len(reproduce_indices), len(free_indices))
                if n_off > 0:
                    reproduce_indices = reproduce_indices[:n_off]
                    child_indices = free_indices[:n_off]
                    births = n_off

                    # Vectorized crossover for all genes at once
                    partner_indices = reproduce_indices[(np.arange(n_off) + 1) % n_off]
                    gene_attrs = [
                        "genome_speed", "genome_metabolism", "genome_fertility",
                        "genome_resilience", "genome_aggression",
                        "genome_intelligence", "genome_size",
                    ]
                    for attr in gene_attrs:
                        p1_vals = getattr(agents, attr)[reproduce_indices]
                        p2_vals = getattr(agents, attr)[partner_indices]
                        allele_choice = np.random.random(n_off) < 0.5
                        child_genome = np.where(allele_choice, p1_vals, p2_vals)
                        mutation_mask = np.random.random(n_off) < 0.05
                        mutation_delta = np.random.uniform(-0.1, 0.1, n_off)
                        child_genome = np.where(
                            mutation_mask,
                            np.clip(child_genome + mutation_delta, 0.0, 1.0),
                            child_genome,
                        )
                        getattr(agents, attr)[child_indices] = child_genome

                    # Vision range
                    p1_v = agents.genome_vision[reproduce_indices]
                    p2_v = agents.genome_vision[partner_indices]
                    child_v = np.where(np.random.random(n_off) < 0.5, p1_v, p2_v)
                    v_mut = np.random.random(n_off) < 0.05
                    child_v = np.where(
                        v_mut,
                        np.clip(child_v + np.random.randint(-1, 2, n_off), 1, 10),
                        child_v,
                    )
                    agents.genome_vision[child_indices] = child_v

                    # Personality inheritance
                    p_traits = [
                        "personality_openness", "personality_conscientiousness",
                        "personality_extraversion", "personality_agreeableness",
                        "personality_neuroticism",
                    ]
                    for trait_attr in p_traits:
                        t1_vals = getattr(agents, trait_attr)[reproduce_indices]
                        t2_vals = getattr(agents, trait_attr)[partner_indices]
                        child_trait = np.clip(
                            0.5 * (t1_vals + t2_vals) + np.random.normal(0, 0.05, n_off),
                            0.0, 1.0,
                        )
                        getattr(agents, trait_attr)[child_indices] = child_trait

                    # Parent energy & offspring setup (all vectorized)
                    parents_energy = agents.energy[reproduce_indices].copy()
                    agents.energy[reproduce_indices] *= 0.5
                    agents.hunger[reproduce_indices] = np.minimum(
                        agents.hunger[reproduce_indices] + 5.0, 100.0
                    )
                    agents.position_x[child_indices] = np.clip(
                        agents.position_x[reproduce_indices]
                        + np.random.randint(-1, 2, n_off, dtype=np.int32),
                        0, self.world.width - 1,
                    )
                    agents.position_y[child_indices] = np.clip(
                        agents.position_y[reproduce_indices]
                        + np.random.randint(-1, 2, n_off, dtype=np.int32),
                        0, self.world.height - 1,
                    )
                    agents.energy[child_indices] = parents_energy
                    agents.hunger[child_indices] = 0.0
                    agents.health[child_indices] = 100.0
                    agents.age[child_indices] = 0
                    agents.parent_ids[child_indices] = agents.agent_ids[reproduce_indices]
                    agents.generation[child_indices] = (
                        agents.generation[reproduce_indices] + 1
                    )
                    new_ids = np.arange(
                        agents._next_id, agents._next_id + n_off, dtype=np.int32
                    )
                    agents.agent_ids[child_indices] = new_ids
                    agents._next_id += n_off
                    agents.alive[child_indices] = True

            # Action 3: rest
            rest_mask = actions == 3
            rest_indices = alive_indices[rest_mask]
            if len(rest_indices) > 0:
                self._resting_mask[rest_indices] = True
                recovery = 2.0 + 1.0 * agents.genome_resilience[rest_indices]
                agents.energy[rest_indices] = np.clip(
                    agents.energy[rest_indices] + recovery, 0.0, 100.0
                )

            # Action 4: flee
            flee_mask = actions == 4
            flee_indices = alive_indices[flee_mask]
            if len(flee_indices) > 0:
                threat_dir_x = np.random.choice(
                    [-1, 1], size=len(flee_indices)
                )
                threat_dir_y = np.random.choice(
                    [-1, 1], size=len(flee_indices)
                )
                flee_distance = np.random.randint(2, 4, size=len(flee_indices))
                agents.position_x[flee_indices] = np.clip(
                    agents.position_x[flee_indices] + threat_dir_x * flee_distance,
                    0, self.world.width - 1,
                )
                agents.position_y[flee_indices] = np.clip(
                    agents.position_y[flee_indices] + threat_dir_y * flee_distance,
                    0, self.world.height - 1,
                )
        t1 = time.perf_counter()
        self.profiler.record_phase("reproduction", (t1 - t0) * 1000.0)

        # ---- Phase 4: Energy decay ----
        t0 = time.perf_counter()
        if n_alive > 0:
            agents.tick_energy()
        t1 = time.perf_counter()
        self.profiler.record_phase("energy", (t1 - t0) * 1000.0)

        # ---- Phase 5: Hunger ----
        t0 = time.perf_counter()
        if n_alive > 0:
            agents.tick_hunger()
        t1 = time.perf_counter()
        self.profiler.record_phase("hunger", (t1 - t0) * 1000.0)

        # ---- Phase 6: Deaths ----
        t0 = time.perf_counter()
        if n_alive > 0:
            deaths = agents.check_deaths()
            # Compact dead slots periodically to reduce fragmentation
            if self.tick_count % 50 == 0:
                agents.compact_dead_slots()
        t1 = time.perf_counter()
        self.profiler.record_phase("death", (t1 - t0) * 1000.0)

        # ---- Phase 7: World regeneration ----
        t0 = time.perf_counter()
        self.world.regenerate()
        t1 = time.perf_counter()
        self.profiler.record_phase("world", (t1 - t0) * 1000.0)

        # ---- Phase 8: Pheromone decay ----
        if self._enable_pheromones and self.pheromones is not None:
            self.pheromones.decay(decay_rate=0.05)

        # ---- Phase 9: Advanced behaviors (post-decision effects) ----
        if self._enable_advanced_behaviors and ADVANCED_BEHAVIORS_AVAILABLE and n_alive > 0:
            try:
                self._apply_advanced_behaviors(alive_indices)
            except Exception:
                # Fallback gracefully: don't crash the simulation
                pass

        # Record total tick time (was started at top of tick)
        self.profiler.end_tick()

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
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]

        # Record tick history (last 1000 ticks)
        post_alive_count = agents.active_count
        current_duration_ms = self.profiler.get_stats()["total"]["last_ms"]
        self.tick_history.append(
            (self.tick_count, current_duration_ms, post_alive_count, births, deaths)
        )
        if len(self.tick_history) > 1000:
            self.tick_history = self.tick_history[-1000:]

        # Check notification triggers
        self._check_notification_triggers(post_alive_count, len(balance_events))

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

    def get_profile_report(self) -> dict:
        """Return the profiler report with per-phase timing stats.

        Returns:
            Dict with summary and per-phase timing information.
        """
        return self.profiler.get_report()

    def profile_report(self) -> dict:
        """Alias for get_profile_report()."""
        return self.get_profile_report()

    def enable_stress_test(self, agent_count: int) -> None:
        """Enable stress test mode by setting max_agents and spawning agents.

        Args:
            agent_count: Number of agents to spawn for stress testing.
        """
        self._original_max_agents = self._config.max_agents
        self._config.max_agents = agent_count
        # Recreate agent state with new capacity
        self.agents = AgentState(max_capacity=agent_count)
        self.profiler.reset()
        self.tick_history.clear()
        self._resting_mask = np.zeros(agent_count, dtype=bool)
        self.agents.spawn_batch(
            agent_count,
            self.world.width,
            self.world.height,
        )

    def disable_stress_test(self) -> None:
        """Disable stress test mode and reset to normal configuration."""
        self._config.max_agents = self._original_max_agents
        self.agents = AgentState(max_capacity=self._original_max_agents)
        self.profiler.reset()
        self.tick_history.clear()
        self._resting_mask = np.zeros(self._original_max_agents, dtype=bool)

    # ------------------------------------------------------------------
    # Advanced behavior integration
    # ------------------------------------------------------------------

    def _apply_advanced_behaviors(self, alive_indices: np.ndarray) -> None:
        """Apply advanced behaviors to currently alive agents.

        Called as part of the tick loop when advanced_behaviors is enabled.
        """
        agents = self.agents
        w = self.world.width
        h = self.world.height
        ai = alive_indices

        px = agents.position_x[ai].astype(np.int32)
        py = agents.position_y[ai].astype(np.int32)

        # --- Pack movement: high agreeableness + extraversion cluster ---
        pack_mask, cx, cy = adv.compute_pack_affinity(
            px, py,
            agents.personality_agreeableness[ai],
            agents.personality_extraversion[ai],
            pack_threshold=0.65,
        )
        if np.any(pack_mask) and len(cx) > 0:
            new_px, new_py = adv.apply_pack_movement(
                agents.position_x[ai],
                agents.position_y[ai],
                pack_mask, cx, cy, w, h,
                pack_strength=0.15,
            )
            agents.position_x[ai] = new_px
            agents.position_y[ai] = new_py

        # --- Territorial behavior: aggressive agents penalize intruders ---
        territory_result = adv.apply_territorial_behavior(
            px, py,
            agents.genome_aggression[ai],
            agents.energy[ai],
            w, h,
        )
        penalties = territory_result["intruder_penalties"]
        if np.any(penalties > 0):
            intruders = ai[penalties > 0]
            agents.energy[intruders] = np.maximum(
                agents.energy[intruders] - penalties[penalties > 0], 0.0
            )

        # --- Migration: move toward better resource areas ---
        local_res = self.world.resources[px, py]
        mig_mask, mig_dx, mig_dy = adv.compute_migration_direction(
            px, py, local_res, self.world.resources, w, h,
            migration_threshold=0.15, search_range=12,
        )
        if np.any(mig_mask):
            new_mx, new_my = adv.apply_migration(
                agents.position_x[ai],
                agents.position_y[ai],
                mig_mask, mig_dx, mig_dy, w, h, speed=1,
            )
            agents.position_x[ai] = new_mx
            agents.position_y[ai] = new_my

        # --- Hibernation: rest in cold areas ---
        local_temp = self.world.temperature[px, py]
        hib_prob = adv.compute_hibernation_prob(
            local_temp,
            agents.energy[ai],
            agents.genome_metabolism[ai],
            cold_threshold=0.3,
        )
        hibernating = np.random.random(len(hib_prob)) < hib_prob
        if np.any(hibernating):
            hib_idx = ai[hibernating]
            agents.energy[hib_idx] = np.clip(
                agents.energy[hib_idx] + 2.0, 0.0, 100.0
            )

    def get_stress_test_metrics(self) -> dict:
        """Return aggregated stress test metrics from tick history.

        Returns:
            Dict with avg_tick_ms, p50, p95, p99, max, min, total_ticks.
        """
        if not self.tick_history:
            return {
                "avg_tick_ms": 0.0,
                "p50_tick_ms": 0.0,
                "p95_tick_ms": 0.0,
                "p99_tick_ms": 0.0,
                "max_tick_ms": 0.0,
                "min_tick_ms": 0.0,
                "total_ticks": 0,
            }

        durations = np.array([entry[1] for entry in self.tick_history], dtype=np.float32)
        total_ticks = len(durations)

        return {
            "avg_tick_ms": float(np.mean(durations)),
            "p50_tick_ms": float(np.percentile(durations, 50)),
            "p95_tick_ms": float(np.percentile(durations, 95)),
            "p99_tick_ms": float(np.percentile(durations, 99)),
            "max_tick_ms": float(np.max(durations)),
            "min_tick_ms": float(np.min(durations)),
            "total_ticks": total_ticks,
        }

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

    # ------------------------------------------------------------------
    # Notification triggers
    # ------------------------------------------------------------------

    def _check_notification_triggers(
        self, population: int, balance_event_count: int
    ) -> None:
        """Check conditions and send push notifications with rate limiting.

        Called once per tick. Uses rate limiting per event type: max 1 per
        5 minutes.
        """
        try:
            from backend.api.push import send_notification

            now = time.time()
            rate_window = 300  # 5 minutes

            if not hasattr(self, "_notif_last_times"):
                self._notif_last_times: dict[str, float] = {}

            initial_pop = self.auto_balancer._initial_population if hasattr(self, "auto_balancer") else self._original_max_agents

            # 1. Ecosystem collapsing: population < 10% of starting
            last = self._notif_last_times.get("ecosystem_collapse", 0)
            if population < initial_pop * 0.10 and (now - last) >= rate_window:
                self._notif_last_times["ecosystem_collapse"] = now
                asyncio.create_task(
                    send_notification(
                        "ecosystem_collapse",
                        "Ecosystem collapsing!",
                        f"Population: {population}",
                    )
                )

            # 2. Population surge: population > 90% of max
            if population > self._config.max_agents * 0.90:
                last = self._notif_last_times.get("population_surge", 0)
                if (now - last) >= rate_window:
                    self._notif_last_times["population_surge"] = now
                    asyncio.create_task(
                        send_notification(
                            "population_surge",
                            "Population surge!",
                            f"{population} agents",
                        )
                    )

            # 3. GPU temperature critical: > 85C
            # Try to read temperature from gpu_history in DB as fallback
            if hasattr(self, "_config") and hasattr(self._config, "db_path"):
                try:
                    from backend.database.db import get_connection, get_db_path
                    from backend.main import gpu_monitor
                    temp: float | None = None
                    if gpu_monitor is not None and hasattr(gpu_monitor, "get_latest"):
                        latest = gpu_monitor.get_latest()
                        if latest:
                            temp = latest.get("temperature")
                    if temp and temp > 85:
                        last = self._notif_last_times.get("gpu_temperature", 0)
                        if (now - last) >= rate_window:
                            self._notif_last_times["gpu_temperature"] = now
                            asyncio.create_task(
                                send_notification(
                                    "gpu_temperature",
                                    "GPU temperature critical!",
                                    f"GPU temperature: {temp}C",
                                )
                            )
                except Exception:
                    pass  # Gracefully degrade

            # 4. Auto-balance adjustment made
            if balance_event_count > 0:
                last = self._notif_last_times.get("auto_balance", 0)
                if (now - last) >= rate_window:
                    self._notif_last_times["auto_balance"] = now
                    # balance_event_count at this point is actually the count (int)
                    # We'll just report that an adjustment was made
                    asyncio.create_task(
                        send_notification(
                            "auto_balance",
                            "Auto-balance adjustment",
                            f"Simulation parameters adjusted to stabilize ecosystem",
                        )
                    )

        except Exception:
            # Notification system must never crash the simulation
            import logging
            logging.getLogger(__name__).warning(
                "Failed to check notification triggers", exc_info=True
            )

