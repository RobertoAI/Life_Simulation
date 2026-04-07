"""WebSocket endpoint for real-time simulation updates."""

import asyncio
from fastapi import WebSocket

from backend.simulation.engine import SimulationEngine


async def websocket_endpoint_simulation(
    websocket: WebSocket, engine: SimulationEngine, ws_interval_ms: int = 200
):
    """WebSocket handler that broadcasts simulation state at regular intervals.

    Args:
        websocket: The WebSocket connection.
        engine: The simulation engine instance.
        ws_interval_ms: Milliseconds between broadcasts.
    """
    await websocket.accept()
    interval_s = ws_interval_ms / 1000.0

    try:
        while True:
            # Build the status payload
            status = engine.get_status()
            metrics = engine.get_metrics()[-1] if engine.get_metrics() else {}

            message = {
                "type": "tick",
                "data": status,
                "metrics": metrics,
            }

            await websocket.send_json(message)
            await asyncio.sleep(interval_s)
    except Exception:
        # Client disconnected or error occurred
        pass
