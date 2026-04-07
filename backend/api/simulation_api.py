"""REST API routes for simulation control and data."""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.simulation.engine import SimulationEngine


router = APIRouter(prefix="/api/simulation", tags=["simulation"])

# Engine is attached at startup; we use a global reference for route access
_engine: SimulationEngine | None = None

# Reference to config Settings class for map endpoint
_config_class = None


def init_router(engine: SimulationEngine, config_class) -> None:
    """Initialize router with engine and config references.

    Args:
        engine: The simulation engine instance.
        config_class: The Settings class for config access.
    """
    global _engine, _config_class
    _engine = engine
    _config_class = config_class


@router.get("/status")
async def get_status():
    """Get current simulation status."""
    if _engine is None:
        return {"error": "Engine not initialized"}
    return _engine.get_status()


@router.post("/start")
async def start_simulation():
    """Start the simulation."""
    if _engine is None:
        return {"success": False, "error": "Engine not initialized"}
    await _engine.start()
    return {"success": True}


@router.post("/stop")
async def stop_simulation():
    """Stop the simulation."""
    if _engine is None:
        return {"success": False, "error": "Engine not initialized"}
    await _engine.stop()
    return {"success": True}


@router.post("/pause")
async def pause_simulation():
    """Pause the simulation."""
    if _engine is None:
        return {"success": False, "error": "Engine not initialized"}
    await _engine.pause()
    return {"success": True}


@router.post("/speed")
async def set_speed(speed: float = 1.0):
    """Set simulation speed multiplier.

    Args:
        speed: Speed multiplier (0.5, 1.0, 2.0, 5.0, 10.0).
    """
    if _engine is None:
        return {"success": False, "error": "Engine not initialized"}
    _engine.set_speed(speed)
    return {"success": True, "speed": speed}


@router.get("/map")
async def get_map():
    """Get current terrain and resource map data.

    Returns terrain types as 2D array of ints and resources as 2D array of floats.
    """
    if _engine is None:
        return {"error": "Engine not initialized"}
    return {
        "width": _engine.world.width,
        "height": _engine.world.height,
        "terrain": _engine.world.get_map_data(),
        "resources": _engine.world.get_resource_map(),
    }


@router.get("/agents")
async def get_agents(page: int = 1, per_page: int = 20):
    """Get paginated list of alive agents.

    Args:
        page: Page number (1-indexed, default 1).
        per_page: Number of agents per page (default 20).
    """
    if _engine is None:
        return {"error": "Engine not initialized"}
    return _engine.get_agents_page(page=page - 1, per_page=per_page)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: int):
    """Get a single agent by ID.

    Args:
        agent_id: Unique agent identifier.
    """
    if _engine is None:
        return {"error": "Engine not initialized"}
    agent = _engine.agents.get_agent_by_id(agent_id)
    if agent is None:
        return {"error": f"Agent {agent_id} not found"}
    return agent


# ----------------------------------------------------------------------- #
# Configuration endpoints
# ----------------------------------------------------------------------- #


class SimulationConfig(BaseModel):
    grid_width: int
    grid_height: int
    tick_interval_ms: int
    ws_interval_ms: int
    initial_population: int
    max_agents: int
    stress_test_agents: int
    snapshot_interval: int
    gpu_monitor_interval: int
    db_path: str


@router.get("/config")
async def get_config():
    """Get current simulation configuration."""
    if _config_class is None:
        return {"error": "Config not initialized"}
    return _config_class.to_dict()


@router.put("/config")
async def update_config(config: SimulationConfig):
    """Update simulation configuration."""
    if _config_class is None:
        return {"success": False, "error": "Config not initialized"}

    try:
        data = config.model_dump()
    except AttributeError:
        data = config.dict()

    for key, value in data.items():
        setattr(_config_class, key, value)

    return {"success": True}
