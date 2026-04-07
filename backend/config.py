"""Dynamic configuration for the AI Life Simulator."""


class Settings:
    """Global simulation settings.

    Usage:
        Settings.grid_width            # class-level default (backwards compat)
        Settings(initial_population=50) # mutable instance with overrides
    """

    grid_width: int = 200
    grid_height: int = 200
    tick_interval_ms: int = 50
    ws_interval_ms: int = 200
    initial_population: int = 1000
    max_agents: int = 10000
    stress_test_agents: int = 50000
    snapshot_interval: int = 100
    gpu_monitor_interval: int = 1
    db_path: str = "data/simulation.db"

    def __new__(cls, **kwargs):
        """Allow instantiation with optional overrides while keeping class-level defaults."""
        if not kwargs:
            return cls  # return the class itself for backwards compatibility
        # Create a mutable instance with defaults
        instance = super().__new__(cls)
        instance.__dict__.update({
            "grid_width": cls.grid_width,
            "grid_height": cls.grid_height,
            "tick_interval_ms": cls.tick_interval_ms,
            "ws_interval_ms": cls.ws_interval_ms,
            "initial_population": cls.initial_population,
            "max_agents": cls.max_agents,
            "stress_test_agents": cls.stress_test_agents,
            "snapshot_interval": cls.snapshot_interval,
            "gpu_monitor_interval": cls.gpu_monitor_interval,
            "db_path": cls.db_path,
        })
        for k, v in kwargs.items():
            if hasattr(instance, k):
                setattr(instance, k, v)
        return instance

    @classmethod
    def to_dict(cls) -> dict:
        """Return settings as a dictionary for serialization."""
        return {
            "grid_width": cls.grid_width,
            "grid_height": cls.grid_height,
            "tick_interval_ms": cls.tick_interval_ms,
            "ws_interval_ms": cls.ws_interval_ms,
            "initial_population": cls.initial_population,
            "max_agents": cls.max_agents,
            "stress_test_agents": cls.stress_test_agents,
            "snapshot_interval": cls.snapshot_interval,
            "gpu_monitor_interval": cls.gpu_monitor_interval,
            "db_path": cls.db_path,
        }
