"""REST API routes for session management and interaction."""

import math

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel

from backend.sessions.session_manager import SessionManager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# SessionManager is attached at startup via init_router
_session_manager: SessionManager | None = None


def init_sessions_router(sm: SessionManager) -> None:
    """Attach the session manager to this router module."""
    global _session_manager
    _session_manager = sm


def _require_sm():
    if _session_manager is None:
        return None
    return _session_manager


def _get_engine(session_id: str):
    sm = _require_sm()
    if sm is None:
        return {"success": False, "error": "Session manager not initialized"}
    engine = sm.get_session(session_id)
    if engine is None:
        return {"success": False, "error": f"Session '{session_id}' not found"}
    return engine


# ----------------------------------------------------------------------- #
# Request / response models
# ----------------------------------------------------------------------- #

class CreateSessionPayload(BaseModel):
    name: str = "unnamed"
    config: dict = {}


class SpawnPayload(BaseModel):
    x: int = 0
    y: int = 0
    count: int = 10
    energy: float = 50.0


class KillAreaPayload(BaseModel):
    x: int = 0
    y: int = 0
    radius: float = 5.0


class EnergyBoostPayload(BaseModel):
    x: int = 0
    y: int = 0
    radius: float = 5.0
    amount: float = 30.0


# ----------------------------------------------------------------------- #
# Session lifecycle endpoints
# ----------------------------------------------------------------------- #


@router.post("/create")
async def create_session(payload: CreateSessionPayload):
    """Create a new simulation session."""
    if _session_manager is None:
        return {"success": False, "error": "Session manager not initialized"}

    from backend.config import Settings
    config = Settings

    # Allow overriding config values from the payload
    if payload.config:
        # Create a simple mutable config from Settings class, then override
        class DynConfig:
            pass
        dc = DynConfig()
        for key in dir(Settings):
            if not key.startswith("_") and not callable(getattr(Settings, key)):
                setattr(dc, key, getattr(Settings, key))
        for k, v in payload.config.items():
            if hasattr(dc, k):
                setattr(dc, k, v)
        config = dc

    session_id = _session_manager.create_session(payload.name, config)
    return {"success": True, "session_id": session_id}


@router.post("/{session_id}/delete")
async def delete_session(session_id: str):
    """Delete a simulation session."""
    if _session_manager is None:
        return {"success": False, "error": "Session manager not initialized"}
    result = _session_manager.delete_session(session_id)
    if result:
        return {"success": True, "session_id": session_id}
    return {"success": False, "error": f"Session '{session_id}' not found"}


@router.get("/list")
async def list_sessions():
    """List all active sessions."""
    if _session_manager is None:
        return {"sessions": []}
    return {"sessions": _session_manager.list_sessions()}


@router.get("/{session_id}/status")
async def session_status(session_id: str):
    """Get status of a specific session."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result
    return result.get_status()


@router.post("/{session_id}/start")
async def session_start(session_id: str):
    """Start a session's simulation."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result
    await result.start()
    return {"success": True}


@router.post("/{session_id}/stop")
async def session_stop(session_id: str):
    """Stop a session's simulation."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result
    await result.stop()
    return {"success": True}


@router.post("/{session_id}/pause")
async def session_pause(session_id: str):
    """Pause/resume a session's simulation."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result
    await result.pause()
    return {"success": True}


@router.post("/{session_id}/speed")
async def session_speed(session_id: str, speed: float = 1.0):
    """Set simulation speed for a session."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result
    result.set_speed(speed)
    return {"success": True, "speed": speed}


# ----------------------------------------------------------------------- #
# Interaction endpoints (user -> agents)
# ----------------------------------------------------------------------- #


@router.post("/{session_id}/interact/spawn")
async def interact_spawn(session_id: str, payload: SpawnPayload):
    """Spawn agents at a location."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result

    engine = result
    agents = engine.agents
    w, h = engine.world.width, engine.world.height

    # Clamp coordinates
    x = max(0, min(payload.x, w - 1))
    y = max(0, min(payload.y, h - 1))

    from backend.simulation.genome import random_genome
    from backend.simulation.personality import random_personality
    from datetime import datetime, timezone

    alive = agents.alive
    count = min(payload.count, agents.capacity - int(alive.sum()))
    if count <= 0:
        return {"success": False, "error": "No free agent slots", "spawned": 0}

    free_indices = np.flatnonzero(~alive)[:count]

    # Pre-generate positions
    offsets_x = np.random.randint(-2, 3, size=count)
    offsets_y = np.random.randint(-2, 3, size=count)
    pos_x = np.clip(x + offsets_x, 0, w - 1).astype(np.int32)
    pos_y = np.clip(y + offsets_y, 0, h - 1).astype(np.int32)

    # Generate genomes and personalities in batch
    genomes = [random_genome() for _ in range(count)]
    personalities = [random_personality() for _ in range(count)]

    # Batch assign
    agents.alive[free_indices] = True
    agents.position_x[free_indices] = pos_x
    agents.position_y[free_indices] = pos_y
    agents.energy[free_indices] = payload.energy
    agents.hunger[free_indices] = 0.0
    agents.health[free_indices] = 100.0
    agents.age[free_indices] = 0
    agents.agent_ids[free_indices] = np.arange(
        agents._next_id, agents._next_id + count, dtype=np.int32
    )
    agents._next_id += count
    agents.parent_ids[free_indices] = -1
    agents.generation[free_indices] = 0

    agents.genome_speed[free_indices] = [g.speed for g in genomes]
    agents.genome_metabolism[free_indices] = [g.metabolism for g in genomes]
    agents.genome_fertility[free_indices] = [g.fertility for g in genomes]
    agents.genome_resilience[free_indices] = [g.resilience for g in genomes]
    agents.genome_aggression[free_indices] = [g.aggression for g in genomes]
    agents.genome_intelligence[free_indices] = [g.intelligence for g in genomes]
    agents.genome_size[free_indices] = [g.size for g in genomes]
    agents.genome_vision[free_indices] = [g.vision for g in genomes]

    agents.personality_openness[free_indices] = [p.openness for p in personalities]
    agents.personality_conscientiousness[free_indices] = [p.conscientiousness for p in personalities]
    agents.personality_extraversion[free_indices] = [p.extraversion for p in personalities]
    agents.personality_agreeableness[free_indices] = [p.agreeableness for p in personalities]
    agents.personality_neuroticism[free_indices] = [p.neuroticism for p in personalities]

    return {"success": True, "spawned": count, "x": x, "y": y}


@router.post("/{session_id}/interact/kill_area")
async def interact_kill_area(session_id: str, payload: KillAreaPayload):
    """Create a 'disaster' that kills agents within a radius."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result

    engine = result
    agents = engine.agents
    w, h = engine.world.width, engine.world.height

    x = max(0, min(payload.x, w - 1))
    y = max(0, min(payload.y, h - 1))
    radius_sq = payload.radius ** 2

    alive_mask = agents.alive
    alive_indices = np.flatnonzero(alive_mask)

    dx = agents.position_x[alive_indices] - x
    dy = agents.position_y[alive_indices] - y
    dist_sq = dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2

    in_radius = alive_indices[dist_sq <= radius_sq]
    killed = len(in_radius)
    if killed > 0:
        agents.alive[in_radius] = False

    return {"success": True, "killed": killed, "x": x, "y": y, "radius": payload.radius}


@router.post("/{session_id}/interact/energy_boost")
async def interact_energy_boost(session_id: str, payload: EnergyBoostPayload):
    """Create 'abundance' that boosts agent energy within a radius."""
    result = _get_engine(session_id)
    if isinstance(result, dict) and "error" in result:
        return result

    engine = result
    agents = engine.agents
    w, h = engine.world.width, engine.world.height

    x = max(0, min(payload.x, w - 1))
    y = max(0, min(payload.y, h - 1))
    radius_sq = payload.radius ** 2

    alive_mask = agents.alive
    alive_indices = np.flatnonzero(alive_mask)

    dx = agents.position_x[alive_indices] - x
    dy = agents.position_y[alive_indices] - y
    dist_sq = dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2

    in_radius = alive_indices[dist_sq <= radius_sq]
    boosted = len(in_radius)
    if boosted > 0:
        agents.energy[in_radius] = np.clip(
            agents.energy[in_radius] + payload.amount, 0.0, 100.0
        )

    return {"success": True, "boosted": boosted, "x": x, "y": y, "amount": payload.amount}
