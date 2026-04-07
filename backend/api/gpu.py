"""REST API endpoints for GPU monitoring data."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from backend.gpu_monitor import GPUMonitor, FallbackGPUMonitor
from backend.database.db import get_connection
from backend.config import Settings


router = APIRouter(prefix="/api/gpu", tags=["GPU Monitor"])


# ----------------------------------------------------------------------- #
# Module-level reference -- set during app startup
# ----------------------------------------------------------------------- #
_gpu_monitor: GPUMonitor | FallbackGPUMonitor | None = None


def init_gpu_router(monitor):
    """Store the GPU monitor instance so endpoints can query it."""
    global _gpu_monitor
    _gpu_monitor = monitor


# ----------------------------------------------------------------------- #
# Endpoints
# ----------------------------------------------------------------------- #


@router.get("/current")
async def get_gpu_current():
    """Latest GPU reading."""
    fallback = False
    data = {}

    if _gpu_monitor is not None:
        fallback = not _gpu_monitor.has_gpu()
        reading = _gpu_monitor.get_current()
        if reading is not None:
            data = reading.to_dict()
        else:
            data = {
                "gpu_utilization": None,
                "vram_used": None,
                "vram_total": None,
                "temperature": None,
                "power_draw": None,
            }
    else:
        data = {
            "gpu_utilization": "no_monitor",
            "vram_used": None,
            "vram_total": None,
            "temperature": None,
            "power_draw": None,
        }

    data["fallback"] = fallback
    return data


@router.get("/history")
async def get_gpu_history(minutes: int = 5):
    """Return GPU history for the last N minutes.

    Combines SQLite gpu_history rows with the in-memory ring buffer.
    """
    fallback = False
    readings = []

    if _gpu_monitor is not None:
        fallback = not _gpu_monitor.has_gpu()
        mem = _gpu_monitor.get_history(300)
        readings = [r.to_dict() for r in mem]

    # If the DB has gpu_history records, append them
    db_path = Settings.db_path
    try:
        conn = get_connection(db_path)
        cursor = conn.execute(
            "SELECT gpu_util, vram_used, vram_total, temperature, power_draw "
            "FROM gpu_history "
            "ORDER BY timestamp DESC "
            "LIMIT ?",
            (minutes * 60,),
        )
        for row in cursor.fetchall():
            readings.insert(
                0,
                {
                    "gpu_utilization": row[0],
                    "vram_used": row[1],
                    "vram_total": row[2],
                    "temperature": row[3],
                    "power_draw": row[4],
                },
            )
        conn.close()
    except Exception:
        # Table may not exist yet; ignore gracefully
        pass

    data = {"fallback": fallback, "minutes": minutes, "readings": readings}
    return data
