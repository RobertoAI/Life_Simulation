"""Background GPU monitor using nvidia-smi CLI parsing."""

import asyncio
import logging
import random
import subprocess
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GPUReading:
    """A single GPU utilization reading."""
    gpu_utilization: Optional[float]
    vram_used: Optional[float]
    vram_total: Optional[float]
    temperature: Optional[float]
    power_draw: Optional[float]

    def to_dict(self) -> dict:
        """Convert reading to dictionary."""
        return {
            "gpu_utilization": self.gpu_utilization,
            "vram_used": self.vram_used,
            "vram_total": self.vram_total,
            "temperature": self.temperature,
            "power_draw": self.power_draw,
        }


logger = logging.getLogger(__name__)


class GPUMonitor:
    """Background GPU monitor that polls nvidia-smi at a configurable interval.

    Runs as an asyncio background task, collecting readings into a ring buffer
    (max 300 samples). Supports querying current state and historical data.
    """

    NVIDIA_SMI_CMD = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    MAX_SAMPLES = 300  # 5 minutes at 1 sample/sec

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._buffer: deque[GPUReading] = deque(maxlen=self.MAX_SAMPLES)
        self._task: Optional[asyncio.Task] = None
        self._gpu_available: bool = False
        self._stopped = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def start(self) -> asyncio.Task:
        """Schedule the background polling loop as an asyncio task."""
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._poll_loop())
        return self._task

    async def stop(self):
        """Stop the background polling loop."""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_current(self) -> Optional[GPUReading]:
        """Return the latest reading, or None if no data collected yet."""
        if self._buffer:
            return self._buffer[-1]
        return None

    def get_history(self, n: int = 300) -> list[GPUReading]:
        """Return the last n readings from the ring buffer."""
        return list(self._buffer)[-n:]

    def has_gpu(self) -> bool:
        """True if nvidia-smi has succeeded at least once."""
        return self._gpu_available

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _poll_loop(self):
        """Continuously poll nvidia-smi and append parsed readings."""
        while not self._stopped:
            try:
                result = subprocess.run(
                    self.NVIDIA_SMI_CMD,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    reading = self._parse_output(result.stdout)
                    if reading is not None:
                        self._buffer.append(reading)
                        self._gpu_available = True
                else:
                    logger.debug(
                        "nvidia-smi returned non-zero: %s", result.stderr.strip()
                    )
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
                logger.debug("nvidia-smi unavailable: %s", exc)
            await asyncio.sleep(self.interval)

    def _parse_output(self, raw: str) -> Optional[GPUReading]:
        """Parse nvidia-smi CSV output into a GPUReading.

        Expected format (one line, comma-separated):
            45.0, 4096, 32768, 72, 200.5
        Handles 'N/A', '[Not Supported]', blank fields gracefully.
        """
        line = raw.strip()
        if not line:
            return None

        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            logger.warning("nvidia-smi output has unexpected columns: %s", line)
            return None

        def _float_or_none(val: str) -> Optional[float]:
            if val in ("N/A", "[Not Supported]", ""):
                return None
            try:
                return float(val)
            except ValueError:
                return None

        return GPUReading(
            gpu_utilization=_float_or_none(parts[0]),
            vram_used=_float_or_none(parts[1]),
            vram_total=_float_or_none(parts[2]),
            temperature=_float_or_none(parts[3]),
            power_draw=_float_or_none(parts[4]),
        )
