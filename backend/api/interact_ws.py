"""Interaction WebSocket /ws/interact/{session_id}.

Allows users to send real-time interaction commands (spawn, kill_area, energy_boost)
to simulation engines and broadcasts those interactions to all viewers.
"""

import asyncio
from fastapi import WebSocket, WebSocketDisconnect

from backend.simulation.engine import SimulationEngine
from backend.sessions.session_manager import SessionManager


async def websocket_endpoint_interact(
    websocket: WebSocket,
    session_id: str,
    session_manager: SessionManager,
):
    """WebSocket handler for user interactions with a simulation session.

    Users can send JSON messages like:
      {"action": "spawn", "x": 10, "y": 10, "count": 10}
      {"action": "kill_area", "x": 10, "y": 10, "radius": 5}
      {"action": "energy_boost", "x": 10, "y": 10, "radius": 5, "amount": 30}

    All connected clients receive broadcasts of every interaction.
    """
    await websocket.accept()
    engine = session_manager.get_session(session_id)
    if engine is None:
        await websocket.send_json({
            "type": "error",
            "message": f"Session '{session_id}' not found",
        })
        await websocket.close(code=1008, reason="Session not found")
        return

    # Track this connection
    session_manager.increment_viewers(session_id)

    # Register this websocket for broadcast
    _clients = _get_or_create_clients(session_id, session_manager)
    _clients.add(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "")
            user = data.get("user", "anonymous")

            result = await _handle_action(engine, action, data)

            # Broadcast the interaction to all viewers
            broadcast_msg = {
                "type": "interaction",
                "user": user,
                "action": action,
                "x": data.get("x", 0),
                "y": data.get("y", 0),
                "result": result,
            }
            await _broadcast(_clients, broadcast_msg, exclude=websocket)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        session_manager.decrement_viewers(session_id)
        _clients.discard(websocket)


# ----------------------------------------------------------------------- #
# helpers
# ----------------------------------------------------------------------- #

# Per-session set of connected WS clients for interaction broadcasts
_interact_clients: dict[str, set] = {}


def _get_or_create_clients(session_id: str, session_manager) -> set:
    """Return (and memoise) the set of WS clients for a session."""
    if session_id not in _interact_clients:
        _interact_clients[session_id] = set()
    return _interact_clients[session_id]


async def _broadcast(clients: set, msg: dict, exclude: WebSocket | None = None):
    """Send *msg* to all clients in *clients*, optionally skipping *exclude*."""
    for ws in set(clients):
        try:
            if ws is not exclude:
                await ws.send_json(msg)
        except Exception:
            pass


async def _handle_action(engine: SimulationEngine, action: str, data: dict) -> dict:
    """Execute an interaction action on the engine."""
    import numpy as np
    agents = engine.agents
    w, h = engine.world.width, engine.world.height

    if action == "spawn":
        x = max(0, min(int(data.get("x", 0)), w - 1))
        y = max(0, min(int(data.get("y", 0)), h - 1))
        count = min(int(data.get("count", 10)), agents.capacity - int(agents.alive.sum()))
        energy = float(data.get("energy", 50))

        if count <= 0:
            return {"spawned": 0, "error": "No free slots"}

        from backend.simulation.genome import random_genome
        from backend.simulation.personality import random_personality

        free_indices = np.flatnonzero(~agents.alive)[:count]

        offsets_x = np.random.randint(-2, 3, size=count)
        offsets_y = np.random.randint(-2, 3, size=count)
        pos_x = np.clip(x + offsets_x, 0, w - 1).astype(np.int32)
        pos_y = np.clip(y + offsets_y, 0, h - 1).astype(np.int32)

        genomes = [random_genome() for _ in range(count)]
        personalities = [random_personality() for _ in range(count)]

        agents.alive[free_indices] = True
        agents.position_x[free_indices] = pos_x
        agents.position_y[free_indices] = pos_y
        agents.energy[free_indices] = energy
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

        return {"spawned": count, "x": int(x), "y": int(y)}

    elif action == "kill_area":
        x = max(0, min(int(data.get("x", 0)), w - 1))
        y = max(0, min(int(data.get("y", 0)), h - 1))
        radius = float(data.get("radius", 5))
        radius_sq = radius ** 2

        alive_mask = agents.alive
        alive_indices = np.flatnonzero(alive_mask)
        dx = agents.position_x[alive_indices] - x
        dy = agents.position_y[alive_indices] - y
        dist_sq = dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2
        in_radius = alive_indices[dist_sq <= radius_sq]
        killed = len(in_radius)
        if killed > 0:
            agents.alive[in_radius] = False

        return {"killed": killed, "x": int(x), "y": int(y), "radius": radius}

    elif action == "energy_boost":
        x = max(0, min(int(data.get("x", 0)), w - 1))
        y = max(0, min(int(data.get("y", 0)), h - 1))
        radius = float(data.get("radius", 5))
        amount = float(data.get("amount", 30))
        radius_sq = radius ** 2

        alive_mask = agents.alive
        alive_indices = np.flatnonzero(alive_mask)
        dx = agents.position_x[alive_indices] - x
        dy = agents.position_y[alive_indices] - y
        dist_sq = dx.astype(np.float32) ** 2 + dy.astype(np.float32) ** 2
        in_radius = alive_indices[dist_sq <= radius_sq]
        boosted = len(in_radius)
        if boosted > 0:
            agents.energy[in_radius] = np.clip(
                agents.energy[in_radius] + amount, 0.0, 100.0
            )

        return {"boosted": boosted, "x": int(x), "y": int(y), "amount": amount}

    else:
        return {"error": f"Unknown action: {action}"}


def cleanup_session_clients(session_id: str):
    """Remove all WS client references for a deleted session."""
    _interact_clients.pop(session_id, None)
