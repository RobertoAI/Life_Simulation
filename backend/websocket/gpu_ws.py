"""WebSocket endpoint for real-time GPU monitoring data."""

import asyncio
import logging

from fastapi import WebSocket

from backend.gpu_monitor import GPUMonitor, FallbackGPUMonitor


logger = logging.getLogger(__name__)


async def websocket_endpoint_gpu(
    websocket: WebSocket,
    gpu_monitor: GPUMonitor | FallbackGPUMonitor,
    config,
):
    """Accept a WebSocket connection and stream GPU readings periodically.

    Args:
        websocket: The WebSocket connection.
        gpu_monitor: An instance of GPUMonitor or FallbackGPUMonitor.
        config: Settings object with gpu_monitor_interval attribute.
    """
    await websocket.accept()
    interval = config.gpu_monitor_interval  # seconds

    try:
        while True:
            reading = gpu_monitor.get_current()
            if reading is not None:
                payload = reading.to_dict()
            else:
                payload = {
                    "gpu_utilization": None,
                    "vram_used": None,
                    "vram_total": None,
                    "temperature": None,
                    "power_draw": None,
                }

            payload["fallback"] = not gpu_monitor.has_gpu()

            await websocket.send_json({
                "type": "gpu",
                "data": payload,
            })

            await asyncio.sleep(interval)
    except Exception:
        # Client disconnected -- expected
        logger.debug("GPU WebSocket client disconnected")
        pass
