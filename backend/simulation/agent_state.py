"""Agent state management using Structure-of-Arrays (SoA) backed by NumPy for high-performance batch operations."""

import numpy as np
from typing import NamedTuple

from backend.simulation.genome import random_genome
from backend.simulation.personality import random_personality

# Maximum number of agents that can be returned in a single WebSocket broadcast.
_MAX_WS_AGENTS = 500


class AgentState:
    """Structure-of-Arrays container for all agent attributes.

    Each attribute is a flat 1D NumPy array indexed by agent ID (0..capacity-1).
    The ``alive`` mask indicates which slots currently hold a living agent.
    All tick-level operations are fully vectorised -- no Python-level loops over
    individuals.
    """

    def __init__(self, max_capacity: int) -> None:
        self.capacity = max_capacity

        # -- SoA arrays --
        # 1 = alive, 0 = dead / unused
        self.alive: np.ndarray = np.zeros(max_capacity, dtype=bool)

        # Position (grid coordinates)
        self.position_x: np.ndarray = np.zeros(max_capacity, dtype=np.int32)
        self.position_y: np.ndarray = np.zeros(max_capacity, dtype=np.int32)

        # Vital stats
        self.energy: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.hunger: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.health: np.ndarray = np.zeros(max_capacity, dtype=np.float32)

        self.age: np.ndarray = np.zeros(max_capacity, dtype=np.int32)

        # Lineage / identity
        self.agent_ids: np.ndarray = np.zeros(max_capacity, dtype=np.int32)
        self.parent_ids: np.ndarray = np.full(max_capacity, -1, dtype=np.int32)
        self.generation: np.ndarray = np.zeros(max_capacity, dtype=np.int32)

        # -- Genome arrays (7 float genes + 1 int gene) --
        self.genome_speed: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_metabolism: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_fertility: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_resilience: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_aggression: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_intelligence: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_size: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.genome_vision: np.ndarray = np.zeros(max_capacity, dtype=np.int32)

        # -- Personality arrays (Big Five) --
        self.personality_openness: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.personality_conscientiousness: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.personality_extraversion: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.personality_agreeableness: np.ndarray = np.zeros(max_capacity, dtype=np.float32)
        self.personality_neuroticism: np.ndarray = np.zeros(max_capacity, dtype=np.float32)

        # Simple monotonic counter for assigning unique agent_ids
        self._next_id = 0

    # ------------------------------------------------------------------
    # Read-only helpers
    # ------------------------------------------------------------------

    @property
    def active_count(self) -> int:
        """Number of currently living agents."""
        return int(np.count_nonzero(self.alive))

    @property
    def memory_usage_mb(self) -> float:
        """Estimate total memory used by all numpy arrays in megabytes."""
        total_bytes = sum(
            arr.nbytes for arr in [
                self.alive,
                self.position_x,
                self.position_y,
                self.energy,
                self.hunger,
                self.health,
                self.age,
                self.agent_ids,
                self.parent_ids,
                self.generation,
                self.genome_speed,
                self.genome_metabolism,
                self.genome_fertility,
                self.genome_resilience,
                self.genome_aggression,
                self.genome_intelligence,
                self.genome_size,
                self.genome_vision,
                self.personality_openness,
                self.personality_conscientiousness,
                self.personality_extraversion,
                self.personality_agreeableness,
                self.personality_neuroticism,
            ]
        )
        return total_bytes / (1024.0 * 1024.0)

    @property
    def free_slots(self) -> int:
        return self.capacity - self.active_count

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def spawn(
        self,
        x: int,
        y: int,
        energy: float = 100.0,
        parent_id: int = -1,
        generation: int = 0,
        genome: dict | None = None,
        personality: dict | None = None,
    ) -> int:
        """Place a single agent in the next free slot.

        If *genome* and *personality* are not provided, random defaults
        are generated.

        Returns the assigned ``agent_id``, or ``-1`` if the capacity is full.
        """
        if self.active_count >= self.capacity:
            return -1

        # Generate random genome/personality if not provided
        if genome is None:
            genome = random_genome(1)
        if personality is None:
            personality = random_personality(1)

        idx = int(np.argmax(~self.alive))  # first dead slot
        return self._populate(
            idx, x, y, energy, parent_id, generation, genome, personality
        )

    def spawn_batch(
        self,
        count: int,
        world_width: int,
        world_height: int,
    ) -> int:
        """Randomly spawn *count* agents onto the grid.

        Generates random genomes and personalities for all spawned agents.

        Returns the number of agents actually spawned (may be less than
        *count* if capacity is nearly full).
        """
        available = self.free_slots
        n = min(count, available)
        if n == 0:
            return 0

        dead_mask = ~self.alive
        indices = np.flatnonzero(dead_mask)[:n]

        self.position_x[indices] = np.random.randint(0, world_width, n)
        self.position_y[indices] = np.random.randint(0, world_height, n)
        self.energy[indices] = 100.0
        self.hunger[indices] = 0.0
        self.health[indices] = 100.0
        self.age[indices] = 0
        self.parent_ids[indices] = -1
        self.generation[indices] = 0

        # Generate random genomes for all new agents
        gen = random_genome(n)
        self.genome_speed[indices] = gen["speed"]
        self.genome_metabolism[indices] = gen["metabolism"]
        self.genome_fertility[indices] = gen["fertility"]
        self.genome_resilience[indices] = gen["resilience"]
        self.genome_aggression[indices] = gen["aggression"]
        self.genome_intelligence[indices] = gen["intelligence"]
        self.genome_size[indices] = gen["size"]
        self.genome_vision[indices] = gen["vision_range"]

        # Generate random personalities for all new agents
        pers = random_personality(n)
        self.personality_openness[indices] = pers["openness"]
        self.personality_conscientiousness[indices] = pers["conscientiousness"]
        self.personality_extraversion[indices] = pers["extraversion"]
        self.personality_agreeableness[indices] = pers["agreeableness"]
        self.personality_neuroticism[indices] = pers["neuroticism"]

        ids = np.arange(self._next_id, self._next_id + n, dtype=np.int32)
        self.agent_ids[indices] = ids
        self._next_id += n
        self.alive[indices] = True
        return n

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _populate(
        self,
        idx: int,
        x: int,
        y: int,
        energy: float,
        parent_id: int,
        generation: int,
        genome: dict,
        personality: dict,
    ) -> int:
        agent_id = self._next_id
        self._next_id += 1

        self.alive[idx] = True
        self.position_x[idx] = x
        self.position_y[idx] = y
        self.energy[idx] = energy
        self.hunger[idx] = 0.0
        self.health[idx] = 100.0
        self.age[idx] = 0
        self.parent_ids[idx] = parent_id
        self.generation[idx] = generation
        self.agent_ids[idx] = agent_id

        # Assign genome
        self.genome_speed[idx] = genome["speed"]
        self.genome_metabolism[idx] = genome["metabolism"]
        self.genome_fertility[idx] = genome["fertility"]
        self.genome_resilience[idx] = genome["resilience"]
        self.genome_aggression[idx] = genome["aggression"]
        self.genome_intelligence[idx] = genome["intelligence"]
        self.genome_size[idx] = genome["size"]
        self.genome_vision[idx] = genome["vision_range"]

        # Assign personality
        self.personality_openness[idx] = personality["openness"]
        self.personality_conscientiousness[idx] = personality["conscientiousness"]
        self.personality_extraversion[idx] = personality["extraversion"]
        self.personality_agreeableness[idx] = personality["agreeableness"]
        self.personality_neuroticism[idx] = personality["neuroticism"]
        return agent_id

    # ------------------------------------------------------------------
    # Genome / Personality accessors
    # ------------------------------------------------------------------

    def get_agent_genome(self, idx: int) -> dict:
        """Return genome dict for a single agent slot."""
        return {
            "speed": float(self.genome_speed[idx]),
            "metabolism": float(self.genome_metabolism[idx]),
            "fertility": float(self.genome_fertility[idx]),
            "resilience": float(self.genome_resilience[idx]),
            "aggression": float(self.genome_aggression[idx]),
            "intelligence": float(self.genome_intelligence[idx]),
            "size": float(self.genome_size[idx]),
            "vision_range": int(self.genome_vision[idx]),
        }

    def get_agent_personality(self, idx: int) -> dict:
        """Return personality dict for a single agent slot."""
        return {
            "openness": float(self.personality_openness[idx]),
            "conscientiousness": float(self.personality_conscientiousness[idx]),
            "extraversion": float(self.personality_extraversion[idx]),
            "agreeableness": float(self.personality_agreeableness[idx]),
            "neuroticism": float(self.personality_neuroticism[idx]),
        }

    def get_genome_diversity(self) -> float:
        """Return average std-dev across all genome arrays for alive agents.

        A higher value indicates more genetic diversity in the population.
        Only float genes are included (vision_range excluded).
        """
        alive = self.alive
        if alive.sum() < 2:
            return 0.0
        float_genes = [
            self.genome_speed,
            self.genome_metabolism,
            self.genome_fertility,
            self.genome_resilience,
            self.genome_aggression,
            self.genome_intelligence,
            self.genome_size,
        ]
        std_devs = []
        for gene in float_genes:
            alive_values = gene[alive]
            if len(alive_values) >= 2:
                std_devs.append(float(np.std(alive_values)))
        if not std_devs:
            return 0.0
        return float(np.mean(std_devs))

    # ------------------------------------------------------------------
    # Killing
    # ------------------------------------------------------------------

    def kill(self, idx: int) -> None:
        """Mark a single slot as dead."""
        self.alive[idx] = False

    # ------------------------------------------------------------------
    # Tick functions (fully vectorised)
    # ------------------------------------------------------------------

    def tick_movement(self, world_width: int, world_height: int) -> None:
        """Move every alive agent by a random delta of -1/0/+1 per axis,
        wrapping at world boundaries."""
        alive_mask = self.alive
        n = int(alive_mask.sum())
        if n == 0:
            return
        dx = np.random.randint(-1, 2, size=n, dtype=np.int32)
        dy = np.random.randint(-1, 2, size=n, dtype=np.int32)
        alive_indices = np.flatnonzero(alive_mask)
        self.position_x[alive_indices] = (
            self.position_x[alive_indices] + dx
        ) % world_width
        self.position_y[alive_indices] = (
            self.position_y[alive_indices] + dy
        ) % world_height

    def tick_energy(self, energy_cost: float = 0.5) -> None:
        """Decrease energy for all alive agents.

        Energy drain is modulated by genome_metabolism:
        higher metabolism = faster energy drain.
        """
        alive_mask = self.alive
        # metabolism in [0,1]: multiplier [0.7, 1.3]
        metabolism_multiplier = 0.7 + 0.6 * self.genome_metabolism[alive_mask]
        self.energy[alive_mask] = np.maximum(
            self.energy[alive_mask] - energy_cost * metabolism_multiplier, 0.0
        )

    def tick_hunger(self, hunger_gain: float = 0.3) -> None:
        """Increase hunger for all alive agents."""
        alive_mask = self.alive
        self.hunger[alive_mask] = np.minimum(
            self.hunger[alive_mask] + hunger_gain, 100.0
        )

    def check_deaths(self) -> int:
        """Kill agents whose energy <= 0.

        Genome resilience delays death: resilient agents survive slightly
        longer after energy hits zero (they get a small energy buffer).

        Returns the number killed.
        """
        alive_mask = self.alive
        # Resilience gives a bonus: energy must drop below -resilience*10
        resilience_buffer = 10.0 * self.genome_resilience[alive_mask]
        starved = self.energy[alive_mask] <= -resilience_buffer
        n = int(starved.sum())
        self.alive[alive_mask.copy()[np.flatnonzero(alive_mask)[starved]]] = False
        # Simpler: compute which alive indices are starved
        alive_indices = np.flatnonzero(alive_mask)
        self.alive[alive_indices[starved]] = False
        return n

    def reproduce(
        self,
        world_width: int,
        world_height: int,
        energy_threshold: float = 80.0,
    ) -> int:
        """Agents above *energy_threshold* spawn one offspring nearby.

        Parent loses half its energy. Offspring starts with that energy.
        Offspring inherits crossed-over genome from two random parents,
        with mutation applied.

        Fully vectorised. For >1000 reproducing agents, uses batch processing.

        Returns number of offspring created.
        """
        can_breed = self.alive & (self.energy >= energy_threshold)
        parent_indices = np.flatnonzero(can_breed)
        n_parents = len(parent_indices)
        if n_parents == 0:
            return 0

        # Need enough free slots
        free_mask = ~self.alive
        free_indices = np.flatnonzero(free_mask)
        n_offspring = min(n_parents, len(free_indices))
        if n_offspring == 0:
            return 0

        parent_indices = parent_indices[:n_offspring]
        child_indices = free_indices[:n_offspring]

        # Select crossover partners: pair each parent with the next one (wrapping)
        partner_indices = parent_indices[(np.arange(n_offspring) + 1) % n_offspring]

        # Crossover: for each gene, randomly pick from parent or partner
        # Batch all gene attributes using stacked arrays for >1000 agents
        if n_offspring > 1000:
            # Batch processing: stack all float genome arrays for vectorized crossover
            float_gene_attrs = [
                "genome_speed", "genome_metabolism", "genome_fertility",
                "genome_resilience", "genome_aggression", "genome_intelligence", "genome_size",
            ]
            parent_float = np.stack([getattr(self, attr)[parent_indices] for attr in float_gene_attrs], axis=0)  # (7, n)
            partner_float = np.stack([getattr(self, attr)[partner_indices] for attr in float_gene_attrs], axis=0)  # (7, n)
            allele_choice = np.random.random((len(float_gene_attrs), n_offspring)) < 0.5
            child_genomes = np.where(allele_choice, parent_float, partner_float)
            mutation_mask = np.random.random((len(float_gene_attrs), n_offspring)) < 0.05
            mutation_delta = np.random.uniform(-0.1, 0.1, (len(float_gene_attrs), n_offspring))
            child_genomes = np.where(mutation_mask, np.clip(child_genomes + mutation_delta, 0.0, 1.0), child_genomes)
            for i, attr in enumerate(float_gene_attrs):
                getattr(self, attr)[child_indices] = child_genomes[i]
        else:
            genes = ["speed", "metabolism", "fertility", "resilience",
                     "aggression", "intelligence", "size"]
            gene_attrs = [
                "genome_speed", "genome_metabolism", "genome_fertility",
                "genome_resilience", "genome_aggression", "genome_intelligence", "genome_size",
            ]

            for attr in gene_attrs:
                parent_values = getattr(self, attr)[parent_indices]
                partner_values = getattr(self, attr)[partner_indices]
                # Random boolean mask: True = take from parent, False = from partner
                allele_choice = np.random.random(n_offspring) < 0.5
                child_genome = np.where(allele_choice, parent_values, partner_values)

                # Apply mutation: ~5% chance per gene, magnitude ~10%
                mutation_mask = np.random.random(n_offspring) < 0.05
                mutation_delta = np.random.uniform(-0.1, 0.1, n_offspring)
                child_genome = np.where(mutation_mask,
                                        np.clip(child_genome + mutation_delta, 0.0, 1.0),
                                        child_genome)

                getattr(self, attr)[child_indices] = child_genome

        # Vision range crossover (integer gene)
        p1_vision = self.genome_vision[parent_indices]
        p2_vision = self.genome_vision[partner_indices]
        child_vision = np.where(np.random.random(n_offspring) < 0.5, p1_vision, p2_vision)
        # Small chance of vision mutation (±1)
        vision_mutate = np.random.random(n_offspring) < 0.05
        child_vision = np.where(vision_mutate,
                                np.clip(child_vision + np.random.randint(-1, 2, n_offspring), 1, 10),
                                child_vision)
        self.genome_vision[child_indices] = child_vision

        # Personality inheritance (average of parents + small noise)
        p_traits = ["personality_openness", "personality_conscientiousness",
                     "personality_extraversion", "personality_agreeableness",
                     "personality_neuroticism"]
        for trait_attr in p_traits:
            p1_vals = getattr(self, trait_attr)[parent_indices]
            p2_vals = getattr(self, trait_attr)[partner_indices]
            child_vals = 0.5 * (p1_vals + p2_vals)
            child_vals = np.clip(child_vals + np.random.normal(0, 0.05, n_offspring), 0.0, 1.0)
            getattr(self, trait_attr)[child_indices] = child_vals

        # Parents lose half energy and hunger increases
        self.energy[parent_indices] *= 0.5
        self.hunger[parent_indices] = np.minimum(
            self.hunger[parent_indices] + 5.0, 100.0
        )

        # Offspring inherit position with jitter
        self.position_x[child_indices] = np.clip(
            self.position_x[parent_indices] + np.random.randint(-1, 2, n_offspring, dtype=np.int32),
            0,
            world_width - 1,
        )
        self.position_y[child_indices] = np.clip(
            self.position_y[parent_indices] + np.random.randint(-1, 2, n_offspring, dtype=np.int32),
            0,
            world_height - 1,
        )
        inherit = self.energy[parent_indices].copy()
        self.energy[child_indices] = inherit
        self.hunger[child_indices] = 0.0
        self.health[child_indices] = 100.0
        self.age[child_indices] = 0
        self.parent_ids[child_indices] = self.agent_ids[parent_indices]
        self.generation[child_indices] = self.generation[parent_indices] + 1
        new_ids = np.arange(self._next_id, self._next_id + n_offspring, dtype=np.int32)
        self.agent_ids[child_indices] = new_ids
        self._next_id += n_offspring
        self.alive[child_indices] = True

        return n_offspring

    # ------------------------------------------------------------------
    # Memory optimization
    # ------------------------------------------------------------------

    def compact_dead_slots(self) -> int:
        """Remove gaps in the SoA by shifting alive agents to fill dead slots.

        Over time, as agents die and new ones are born in free slots, the
        array becomes fragmented with dead slots scattered throughout.
        Compaction moves all alive agents to the front of the arrays,
        improving cache locality for subsequent vectorized operations.

        Returns the number of agents that were moved.
        """
        alive_indices = np.flatnonzero(self.alive)
        n_alive = len(alive_indices)
        if n_alive == 0:
            return 0

        # Check if there are gaps (dead slots before the last alive index)
        last_alive = int(alive_indices[-1])
        if last_alive == n_alive - 1:
            # Already compact, no gaps
            return 0

        # Compact all arrays: move alive agents to slots 0..n_alive-1
        target_indices = np.arange(n_alive, dtype=np.int64)

        # Move all SoA arrays
        self.alive[:] = False
        self.position_x[target_indices] = self.position_x[alive_indices]
        self.position_y[target_indices] = self.position_y[alive_indices]
        self.energy[target_indices] = self.energy[alive_indices]
        self.hunger[target_indices] = self.hunger[alive_indices]
        self.health[target_indices] = self.health[alive_indices]
        self.age[target_indices] = self.age[alive_indices]
        self.agent_ids[target_indices] = self.agent_ids[alive_indices]
        self.parent_ids[target_indices] = self.parent_ids[alive_indices]
        self.generation[target_indices] = self.generation[alive_indices]

        # Genome arrays
        self.genome_speed[target_indices] = self.genome_speed[alive_indices]
        self.genome_metabolism[target_indices] = self.genome_metabolism[alive_indices]
        self.genome_fertility[target_indices] = self.genome_fertility[alive_indices]
        self.genome_resilience[target_indices] = self.genome_resilience[alive_indices]
        self.genome_aggression[target_indices] = self.genome_aggression[alive_indices]
        self.genome_intelligence[target_indices] = self.genome_intelligence[alive_indices]
        self.genome_size[target_indices] = self.genome_size[alive_indices]
        self.genome_vision[target_indices] = self.genome_vision[alive_indices]

        # Personality arrays
        self.personality_openness[target_indices] = self.personality_openness[alive_indices]
        self.personality_conscientiousness[target_indices] = self.personality_conscientiousness[alive_indices]
        self.personality_extraversion[target_indices] = self.personality_extraversion[alive_indices]
        self.personality_agreeableness[target_indices] = self.personality_agreeableness[alive_indices]
        self.personality_neuroticism[target_indices] = self.personality_neuroticism[alive_indices]

        # Mark compacted slots as alive
        self.alive[target_indices] = True

        # Clear data in the old dead slots (slots n_alive to last_alive)
        old_dead_range = slice(n_alive, last_alive + 1)
        self.position_x[old_dead_range] = 0
        self.position_y[old_dead_range] = 0
        self.energy[old_dead_range] = 0.0
        self.hunger[old_dead_range] = 0.0
        self.health[old_dead_range] = 0.0
        self.age[old_dead_range] = 0
        self.parent_ids[old_dead_range] = -1

        return n_alive

    # ------------------------------------------------------------------
    # Data access for WebSocket / API
    # ------------------------------------------------------------------

    def get_alive_positions(self) -> np.ndarray:
        """Return (x, y) int32 array of shape (alive_count, 2)."""
        m = self.alive
        return np.column_stack((self.position_x[m], self.position_y[m]))

    def get_alive_agents_for_ws(self, max_count: int = _MAX_WS_AGENTS) -> list[dict]:
        """Return up to *max_count* alive agents as plain dicts for WS broadcast."""
        alive_indices = np.flatnonzero(self.alive)
        if len(alive_indices) == 0:
            return []
        if len(alive_indices) > max_count:
            alive_indices = np.random.choice(alive_indices, max_count, replace=False)

        results = []
        for idx in alive_indices:
            results.append({
                "id": int(self.agent_ids[idx]),
                "x": int(self.position_x[idx]),
                "y": int(self.position_y[idx]),
                "energy": float(self.energy[idx]),
                "health": int(self.health[idx]),
                "age": int(self.age[idx]),
                "generation": int(self.generation[idx]),
            })
        return results

    def get_alive_agents_for_api(self, page: int = 0, per_page: int = 50) -> dict:
        """Paginated view of alive agents for the REST API.

        Returns a dict with ``page``, ``per_page``, ``total``, ``agents``.
        """
        alive_indices = np.flatnonzero(self.alive)
        total = len(alive_indices)
        start = page * per_page
        end = start + per_page
        page_indices = alive_indices[start:end]

        agents = []
        for idx in page_indices:
            agents.append({
                "id": int(self.agent_ids[idx]),
                "x": int(self.position_x[idx]),
                "y": int(self.position_y[idx]),
                "energy": float(self.energy[idx]),
                "health": int(self.health[idx]),
                "age": int(self.age[idx]),
                "generation": int(self.generation[idx]),
                "parent_id": int(self.parent_ids[idx]),
            })

        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "agents": agents,
        }

    def get_agent_by_id(self, agent_id: int) -> dict | None:
        """Look up a single agent by its unique ID.

        Returns a dict or ``None`` if not found / dead.
        """
        # Find slots matching this agent_id among alive
        matches = np.flatnonzero(self.alive & (self.agent_ids == agent_id))
        if len(matches) == 0:
            return None
        idx = matches[0]
        return {
            "id": int(self.agent_ids[idx]),
            "x": int(self.position_x[idx]),
            "y": int(self.position_y[idx]),
            "energy": float(self.energy[idx]),
            "hunger": float(self.hunger[idx]),
            "health": int(self.health[idx]),
            "age": int(self.age[idx]),
            "generation": int(self.generation[idx]),
            "parent_id": int(self.parent_ids[idx]),
        }
