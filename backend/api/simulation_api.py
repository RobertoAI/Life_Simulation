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


# --- session-aware engine resolver ------------------------------------------

def _resolve_engine(session: str | None = None):
    """Return the SimulationEngine for the given session, defaulting to 'main'.

    Falls back to the legacy _engine global if the session manager is not yet
    wired up (important for backwards compatibility and unit tests).
    """
    if session and session != "main" and _session_mgr is not None:
        eng = _session_mgr.get_session(session)
        if eng is not None:
            return eng
    # default: use the legacy _engine or resolve "main" from session mgr
    if _engine is not None:
        return _engine
    if _session_mgr is not None:
        return _session_mgr.get_session("main")
    return None


_session_mgr = None


def set_session_manager(sm) -> None:
    """Wire the session manager into this router (called from main.py)."""
    global _session_mgr
    _session_mgr = sm


# ----------------------------------------------------------------------- #

@router.get("/status")
async def get_status(session: str | None = None):
    """Get current simulation status.

    Args:
        session: Optional session id (defaults to 'main' / _engine for backwards compatibility).
    """
    eng = _resolve_engine(session)
    if eng is None:
        return {"error": "Engine not initialized"}
    return eng.get_status()


@router.post("/start")
async def start_simulation(session: str | None = None):
    """Start the simulation."""
    eng = _resolve_engine(session)
    if eng is None:
        return {"success": False, "error": "Engine not initialized"}
    await eng.start()
    return {"success": True}


@router.post("/stop")
async def stop_simulation(session: str | None = None):
    """Stop the simulation."""
    eng = _resolve_engine(session)
    if eng is None:
        return {"success": False, "error": "Engine not initialized"}
    await eng.stop()
    return {"success": True}


@router.post("/pause")
async def pause_simulation(session: str | None = None):
    """Pause the simulation."""
    eng = _resolve_engine(session)
    if eng is None:
        return {"success": False, "error": "Engine not initialized"}
    await eng.pause()
    return {"success": True}


@router.post("/speed")
async def set_speed(speed: float = 1.0, session: str | None = None):
    """Set simulation speed multiplier.

    Args:
        speed: Speed multiplier (0.5, 1.0, 2.0, 5.0, 10.0).
        session: Optional session id (defaults to 'main').
    """
    eng = _resolve_engine(session)
    if eng is None:
        return {"success": False, "error": "Engine not initialized"}
    eng.set_speed(speed)
    return {"success": True, "speed": speed}


@router.get("/map")
async def get_map(session: str | None = None):
    """Get current terrain and resource map data.

    Returns terrain types as 2D array of ints and resources as 2D array of floats.
    """
    eng = _resolve_engine(session)
    if eng is None:
        return {"error": "Engine not initialized"}
    return {
        "width": eng.world.width,
        "height": eng.world.height,
        "terrain": eng.world.get_map_data(),
        "resources": eng.world.get_resource_map(),
    }


@router.get("/agents")
async def get_agents(page: int = 1, per_page: int = 20, session: str | None = None):
    """Get paginated list of alive agents.

    Args:
        page: Page number (1-indexed, default 1).
        per_page: Number of agents per page (default 20).
        session: Optional session id (defaults to 'main').
    """
    eng = _resolve_engine(session)
    if eng is None:
        return {"error": "Engine not initialized"}
    return eng.get_agents_page(page=page - 1, per_page=per_page)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: int, session: str | None = None):
    """Get a single agent by ID.

    Args:
        agent_id: Unique agent identifier.
        session: Optional session id (defaults to 'main').
    """
    eng = _resolve_engine(session)
    if eng is None:
        return {"error": "Engine not initialized"}
    agent = eng.agents.get_agent_by_id(agent_id)
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
