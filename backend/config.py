"""Dynamic configuration for the AI Life Simulator."""


class Settings:
    """Global simulation settings."""

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
