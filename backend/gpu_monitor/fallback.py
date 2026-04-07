"""Fallback GPU monitor that generates realistic simulated data."""

import asyncio
import datetime
import logging
import math
import random
import time
from collections import deque
from typing import Optional

from backend.gpu_monitor.monitor import GPUReading


logger = logging.getLogger(__name__)

# Log that fallback mode is active
logger.warning(
    "GPU Fallback Mode Active -- simulating GPU metrics "
    "(no nvidia-smi / NVIDIA GPU detected)"
)


class FallbackGPUMonitor:
    """Simulated GPU monitor matching the GPUMonitor interface.

    Generates realistic-feeling metrics via random walks so the frontend and
    dashboard still have meaningful data to display.
    """

    MAX_SAMPLES = 300

    # Simulation parameters
    VRAM_TOTAL = 32768  # Simulating RTX 5090 32GB

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._buffer: deque[GPUReading] = deque(maxlen=self.MAX_SAMPLES)
        self._task: Optional[asyncio.Task] = None
        self._stopped = False

        # Internal random-walk state -- seeded at init
        self._util = random.uniform(20.0, 50.0)
        self._temp = random.uniform(55.0, 65.0)
        self._power = random.uniform(90.0, 180.0)
        self._vram = random.uniform(2048.0, 4096.0)
        self._start_time = time.time()

    # ------------------------------------------------------------------ #
    # Public API (matches GPUMonitor)
    # ------------------------------------------------------------------ #

    def start(self) -> asyncio.Task:
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._poll_loop())
        return self._task

    async def stop(self):
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_current(self) -> Optional[GPUReading]:
        if self._buffer:
            return self._buffer[-1]
        return None

    def get_history(self, n: int = 300) -> list[GPUReading]:
        return list(self._buffer)[-n:]

    def has_gpu(self) -> bool:
        # Falls back, so no real GPU
        return False

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _poll_loop(self):
        """Generate a simulated reading every *interval* seconds."""
        while not self._stopped:
            reading = self._generate_reading()
            self._buffer.append(reading)
            await asyncio.sleep(self.interval)

    def _generate_reading(self) -> GPUReading:
        """Produce one correlated simulated reading."""

        # Slow upward drift over time to mimic warm-up
        elapsed = time.time() - self._start_time
        warmup = min(1.0, elapsed / 60.0)  # ramps over first 60 s

        # --- Utilization: 20-80% random walk ---
        drift = random.gauss(0, 4.0)
        self._util = max(15.0, min(85.0, self._util + drift))

        # --- Temperature: 60-85°C, loosely correlated with utilization ---
        target_temp = 55.0 + (self._util / 100.0) * 30.0
        self._temp += (target_temp - self._temp) * 0.05 + random.gauss(0, 0.5)
        self._temp = max(40.0, min(95.0, self._temp))

        # --- Power: 100-450W, correlated with utilization ---
        target_power = 80.0 + (self._util / 100.0) * 370.0
        self._power += (target_power - self._power) * 0.08 + random.gauss(0, 5.0)
        self._power = max(60.0, min(500.0, self._power))

        # --- VRAM used: 2048-8192 MB, influenced by utilization ---
        target_vram = 2048.0 + (self._util / 100.0) * 6144.0
        self._vram += (target_vram - self._vram) * 0.03 + random.gauss(0, 50.0)
        self._vram = max(1024.0, min(16384.0, self._vram))

        return GPUReading(
            gpu_utilization=round(self._util, 1),
            vram_used=round(self._vram, 1),
            vram_total=float(self.VRAM_TOTAL),
            temperature=round(self._temp, 1),
            power_draw=round(self._power, 1),
        )
