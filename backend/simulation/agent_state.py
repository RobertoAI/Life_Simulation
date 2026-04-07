"""Agent state management using Structure-of-Arrays (SoA) backed by NumPy for high-performance batch operations."""

import numpy as np
from typing import NamedTuple

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
    ) -> int:
        """Place a single agent in the next free slot.

        Returns the assigned ``agent_id``, or ``-1`` if the capacity is full.
        """
        if self.active_count >= self.capacity:
            return -1

        idx = int(np.argmax(~self.alive))  # first dead slot
        return self._populate(
            idx, x, y, energy, parent_id, generation
        )

    def spawn_batch(
        self,
        count: int,
        world_width: int,
        world_height: int,
    ) -> int:
        """Randomly spawn *count* agents onto the grid.

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
        return agent_id

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
        """Decrease energy for all alive agents."""
        alive_mask = self.alive
        self.energy[alive_mask] = np.maximum(
            self.energy[alive_mask] - energy_cost, 0.0
        )

    def tick_hunger(self, hunger_gain: float = 0.3) -> None:
        """Increase hunger for all alive agents."""
        alive_mask = self.alive
        self.hunger[alive_mask] = np.minimum(
            self.hunger[alive_mask] + hunger_gain, 100.0
        )

    def check_deaths(self) -> int:
        """Kill agents whose energy <= 0.

        Returns the number killed.
        """
        starved = self.alive & (self.energy <= 0.0)
        n = int(starved.sum())
        self.alive[starved] = False
        return n

    def reproduce(
        self,
        world_width: int,
        world_height: int,
        energy_threshold: float = 80.0,
    ) -> int:
        """Agents above *energy_threshold* spawn one offspring nearby.

        Parent loses half its energy.  Offspring starts with that energy.
        Fully vectorised.

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
