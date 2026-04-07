"""Auto-Balance system that prevents ecosystem collapse with rollback support.

The AutoBalancer monitors ecosystem health metrics (population trends, birth/death
ratios, genetic diversity, resource levels) and applies gradual adjustments to
simulation parameters to steer the ecosystem toward stability.

Each adjustment is trackable, logged, and revertible.
"""

from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger()


class Adjustment:
    """Represents a single parameter adjustment made by the AutoBalancer."""

    def __init__(self, parameter: str, old_value: float, new_value: float,
                 reason: str, revertible: bool = True):
        self.parameter = parameter
        self.old_value = old_value
        self.new_value = new_value
        self.reason = reason
        self.revertible = revertible
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "parameter": self.parameter,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "reason": self.reason,
            "revertible": self.revertible,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        return (f"Adjustment({self.parameter}: {self.old_value:.4f} -> "
                f"{self.new_value:.4f}, reason='{self.reason}')")


class AutoBalancer:
    """Monitors ecosystem health and applies automatic parameter adjustments.

    Tracks: population trend, birth/death ratio, genetic diversity, resource
    levels. Applies gradual, reversible adjustments to prevent ecosystem
    collapse or runaway growth.
    """

    # Default config values
    DEFAULT_RESOURCE_REGENERATION_MULTIPLIER = 1.0
    DEFAULT_REPRODUCTION_CHANCE_MULTIPLIER = 1.0
    DEFAULT_METABOLISM_MULTIPLIER = 1.0
    DEFAULT_MUTATION_RATE = 0.05
    MAX_MUTATION_RATE = 0.15

    def __init__(self, config):
        """Initialize the AutoBalancer with configuration.

        Args:
            config: Settings object used for baseline values.
        """
        self._enabled = True
        self._config = config

        # Current override multipliers
        self._resource_regeneration_multiplier = self.DEFAULT_RESOURCE_REGENERATION_MULTIPLIER
        self._reproduction_chance_multiplier = self.DEFAULT_REPRODUCTION_CHANCE_MULTIPLIER
        self._metabolism_multiplier = self.DEFAULT_METABOLISM_MULTIPLIER
        self._mutation_rate_override = self.DEFAULT_MUTATION_RATE

        # Tracking state
        self._adjustment_history: list[Adjustment] = []
        self._initial_population: int = getattr(config, 'initial_population', 1000)
        self._max_agents: int = getattr(config, 'max_agents', 10000)

        # For tracking trends across ticks
        self._prev_population: Optional[int] = None
        self._population_history: list[int] = []
        self._prev_births: int = 0
        self._prev_deaths: int = 0
        self._total_births: int = 0
        self._total_deaths: int = 0

        # Cooldown tracking to prevent rapid-fire adjustments
        self._last_adjustment_tick: int = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        logger.info("autobalance_enabled")

    def disable(self) -> None:
        self._enabled = False
        logger.info("autobalance_disabled")

    def check(self, state, world, tick) -> list[dict]:
        """Evaluate ecosystem health and apply adjustments if needed.

        Args:
            state: AgentState instance for population/genetic data.
            world: World instance for resource data.
            tick: Current simulation tick number.

        Returns:
            List of adjustment dicts applied this check.
        """
        if not self._enabled:
            return []

        # Prevent checking too often
        if tick - self._last_adjustment_tick < 50:
            return []

        adjustments_made: list[Adjustment] = []

        current_pop = state.active_count
        self._population_history.append(current_pop)

        # Update population trend tracking
        if self._prev_population is not None:
            delta = current_pop - self._prev_population
            deaths_this_tick = max(
                self._prev_population - current_pop,
                0
            )
            self._total_deaths += deaths_this_tick
        self._prev_population = current_pop

        # --- Threshold: Population crash ---
        if current_pop < 0.20 * self._initial_population:
            adj = self._apply_adjustment(
                "resource_regeneration_multiplier",
                "boost resources",
                lambda: self._resource_regeneration_multiplier * 2.0,
                f"Population crash: {current_pop} < 20% of starting ({self._initial_population})",
                tick
            )
            if adj:
                adjustments_made.append(adj)

            adj2 = self._apply_adjustment(
                "reproduction_chance_multiplier",
                "increase reproduction",
                lambda: min(self._reproduction_chance_multiplier * 1.3, 3.0),
                f"Population crash: boosting reproduction at pop={current_pop}",
                tick
            )
            if adj2:
                adjustments_made.append(adj2)

        # --- Threshold: Population explosion ---
        if current_pop > 0.90 * self._max_agents:
            adj = self._apply_adjustment(
                "metabolism_multiplier",
                "increase metabolism by 20%",
                lambda: self._metabolism_multiplier * 1.2,
                f"Population explosion: {current_pop} > 90% of max ({self._max_agents})",
                tick
            )
            if adj:
                adjustments_made.append(adj)

            adj2 = self._apply_adjustment(
                "reproduction_chance_multiplier",
                "decrease reproduction by 50%",
                lambda: max(self._reproduction_chance_multiplier * 0.5, 0.1),
                f"Population explosion: reducing reproduction at pop={current_pop}",
                tick
            )
            if adj2:
                adjustments_made.append(adj2)

        # --- Threshold: Genetic diversity low ---
        genetic_diversity = self._compute_genetic_diversity(state)
        if genetic_diversity < 0.1:
            new_mutation = min(
                self._mutation_rate_override * 1.5,
                self.MAX_MUTATION_RATE
            )
            if new_mutation > self._mutation_rate_override:
                adj = self._apply_adjustment_direct(
                    "mutation_rate_override",
                    genetic_diversity,
                    new_mutation,
                    f"Low genetic diversity ({genetic_diversity:.4f}), increasing mutation rate",
                    tick
                )
                if adj:
                    adjustments_made.append(adj)

        # --- Threshold: Resources depleted ---
        avg_resources = float(__import__('numpy').mean(world.resources))
        if avg_resources < 0.3:
            adj = self._apply_adjustment(
                "resource_regeneration_multiplier",
                "increase regeneration by 50%",
                lambda: self._resource_regeneration_multiplier * 1.5,
                f"Resources depleted: avg={avg_resources:.4f} < 0.3",
                tick
            )
            if adj:
                adjustments_made.append(adj)

        # --- Threshold: Resources overflowing ---
        if avg_resources > 0.8:
            adj = self._apply_adjustment(
                "resource_regeneration_multiplier",
                "decrease regeneration to prevent boom-bust",
                lambda: max(self._resource_regeneration_multiplier * 0.7, 0.5),
                f"Resources overflowing: avg={avg_resources:.4f} > 0.8",
                tick
            )
            if adj:
                adjustments_made.append(adj)

        # --- Threshold: Birth/death ratio too high ---
        bd_ratio = 0.0
        if self._total_deaths > 0:
            bd_ratio = self._total_births / max(self._total_deaths, 1)
            if bd_ratio > 3.0:
                adj = self._apply_adjustment(
                    "reproduction_chance_multiplier",
                    "reduce reproduction by 30%",
                    lambda: max(self._reproduction_chance_multiplier * 0.7, 0.1),
                    f"Birth/death ratio too high ({bd_ratio:.2f}), reducing reproduction",
                    tick
                )
                if adj:
                    adjustments_made.append(adj)

        # --- Threshold: Birth/death ratio too low (extinction risk) ---
        if self._total_deaths > 0 and bd_ratio < 0.3:
            adj = self._apply_adjustment(
                "reproduction_chance_multiplier",
                "increase reproduction by 30%",
                lambda: min(self._reproduction_chance_multiplier * 1.3, 3.0),
                f"Birth/death ratio too low ({bd_ratio:.2f}), extinction risk",
                tick
            )
            if adj:
                adjustments_made.append(adj)

        if self._total_births == 0 and self._total_deaths == 0 and current_pop < self._initial_population * 0.5:
            # Haven't observed enough data yet, give reproduction a boost
            adj = self._apply_adjustment(
                "reproduction_chance_multiplier",
                "increase reproduction by 30%",
                lambda: min(self._reproduction_chance_multiplier * 1.3, 3.0),
                f"No births observed, population declining: {current_pop}",
                tick
            )
            if adj:
                adjustments_made.append(adj)

        # Record births/deaths for ratio tracking
        if self._prev_population is not None and len(self._population_history) >= 2:
            pop_diff = current_pop - self._population_history[-2] if len(self._population_history) >= 2 else 0
            if pop_diff > 0:
                self._total_births += pop_diff
            # Deaths tracked above in the population delta check

        if adjustments_made:
            self._last_adjustment_tick = tick
            for adj in adjustments_made:
                logger.info(
                    "autobalance_adjustment",
                    parameter=adj.parameter,
                    old_value=adj.old_value,
                    new_value=adj.new_value,
                    reason=adj.reason
                )

        return [a.to_dict() for a in adjustments_made]

    def _apply_adjustment(self, parameter: str, action_desc: str,
                          value_fn, reason: str, tick: int) -> Optional[Adjustment]:
        """Apply an adjustment if the value actually changes.

        Args:
            parameter: Name of the parameter to adjust.
            action_desc: Short description of the action.
            value_fn: Callable that returns the new value.
            reason: Detailed reason string for logging.
            tick: Current tick number.

        Returns:
            The Adjustment if applied, None otherwise.
        """
        current_val, attr_name = self._get_parameter_state(parameter)
        new_val = value_fn()

        # Check if value would actually change significantly (5% threshold)
        if parameter == "mutation_rate_override":
            if abs(new_val - current_val) < 0.001:
                return None
        else:
            if abs(new_val - current_val) / max(current_val, 0.001) < 0.01:
                return None

        old_val = current_val
        setattr(self, attr_name, new_val)

        adj = Adjustment(parameter, old_val, new_val, reason)
        self._adjustment_history.append(adj)

        return adj

    def _apply_adjustment_direct(self, parameter: str, old_val_key: float,
                                 new_val: float, reason: str,
                                 tick: int) -> Optional[Adjustment]:
        """Apply adjustment with explicit old/new values (for mutation rate)."""
        if abs(new_val - self._mutation_rate_override) < 0.001:
            return None

        old_val = self._mutation_rate_override
        self._mutation_rate_override = new_val

        adj = Adjustment(parameter, old_val, new_val, reason)
        self._adjustment_history.append(adj)
        return adj

    def _get_parameter_state(self, parameter: str) -> tuple[float, str]:
        """Get current value and attribute name for a parameter.

        Returns:
            Tuple of (current_value, attribute_name).
        """
        mapping = {
            "resource_regeneration_multiplier": (self._resource_regeneration_multiplier,
                                                  "_resource_regeneration_multiplier"),
            "reproduction_chance_multiplier": (self._reproduction_chance_multiplier,
                                                "_reproduction_chance_multiplier"),
            "metabolism_multiplier": (self._metabolism_multiplier,
                                       "_metabolism_multiplier"),
            "mutation_rate_override": (self._mutation_rate_override,
                                        "_mutation_rate_override"),
        }
        return mapping[parameter]

    def _compute_genetic_diversity(self, state) -> float:
        """Compute a simple genetic diversity metric across alive agents.

        Uses standard deviation of genome traits as a proxy for diversity.

        Args:
            state: AgentState instance.

        Returns:
            Float between 0 and ~1 representing diversity.
        """
        import numpy as np

        alive_mask = state.alive
        if not np.any(alive_mask):
            return 0.0

        alive_count = int(np.sum(alive_mask))
        if alive_count < 5:
            # Too few agents for meaningful diversity calculation
            return 0.0

        # Sample a few genome traits and compute their coefficients of variation
        traits = []
        for attr in ["genome_speed", "genome_metabolism", "genome_fertility",
                      "genome_resilience", "genome_aggression"]:
            vals = getattr(state, attr)[alive_mask]
            mean_val = np.mean(vals)
            std_val = np.std(vals)
            if mean_val > 0.001:
                cv = std_val / mean_val  # coefficient of variation
                traits.append(cv)
            else:
                traits.append(std_val)  # fallback to raw std

        if not traits:
            return 0.0

        # Normalize: typical CV ranges from ~0.0 to ~0.6
        avg_cv = np.mean(traits)
        diversity = min(avg_cv / 0.6, 1.0)
        return float(diversity)

    def get_adjustment_history(self) -> list[dict]:
        """Return complete history of all adjustments made.

        Returns:
            List of adjustment dicts.
        """
        return [a.to_dict() for a in self._adjustment_history]

    def get_current_config_overrides(self) -> dict:
        """Return current active configuration overrides.

        Returns:
            Dict with current override values.
        """
        return {
            "resource_regeneration_multiplier": self._resource_regeneration_multiplier,
            "reproduction_chance_multiplier": self._reproduction_chance_multiplier,
            "metabolism_multiplier": self._metabolism_multiplier,
            "mutation_rate_override": self._mutation_rate_override,
        }

    def revert_last_adjustment(self) -> Optional[dict]:
        """Revert the most recent reversible adjustment.

        Returns:
            Dict of the reverted adjustment, or None if nothing to revert.
        """
        # Find most recent revertible adjustment
        for i in range(len(self._adjustment_history) - 1, -1, -1):
            adj = self._adjustment_history[i]
            if adj.revertible:
                old_value = adj.old_value
                new_value = adj.new_value
                parameter = adj.parameter

                # Restore old value
                _, attr_name = self._get_parameter_state(parameter)
                setattr(self, attr_name, old_value)

                # Create revert record
                revert_adj = Adjustment(
                    parameter, new_value, old_value,
                    f"Reverted: {adj.reason}",
                    revertible=False
                )
                self._adjustment_history.append(revert_adj)

                logger.info(
                    "autobalance_revert",
                    parameter=parameter,
                    restored_value=old_value,
                    previous_value=new_value
                )

                return revert_adj.to_dict()

        return None

    def reset(self) -> None:
        """Clear history and restore all defaults."""
        self._resource_regeneration_multiplier = self.DEFAULT_RESOURCE_REGENERATION_MULTIPLIER
        self._reproduction_chance_multiplier = self.DEFAULT_REPRODUCTION_CHANCE_MULTIPLIER
        self._metabolism_multiplier = self.DEFAULT_METABOLISM_MULTIPLIER
        self._mutation_rate_override = self.DEFAULT_MUTATION_RATE
        self._adjustment_history.clear()
        self._prev_population = None
        self._population_history.clear()
        self._total_births = 0
        self._total_deaths = 0
        self._last_adjustment_tick = 0

    def set_births_this_tick(self, count: int) -> None:
        """Record number of births in the current tick.

        Args:
            count: Number of new agents born.
        """
        self._total_births += count

    def set_deaths_this_tick(self, count: int) -> None:
        """Record number of deaths in the current tick.

        Args:
            count: Number of agents that died.
        """
        self._total_deaths += count
