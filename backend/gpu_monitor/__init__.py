"""GPU monitor module -- exports monitors and factory."""

from backend.gpu_monitor.monitor import GPUMonitor, GPUReading
from backend.gpu_monitor.fallback import FallbackGPUMonitor


def create_gpu_monitor(interval: float = 1.0):
    """Factory: tries real GPUMonitor, falls back to FallbackGPUMonitor.

    We perform a quick probe (run nvidia-smi once) to decide which class to
    instantiate so the application never crashes at startup.
    """
    import subprocess
    import logging

    logger = logging.getLogger(__name__)

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.info("GPU monitor initialized (real nvidia-smi)")
            return GPUMonitor(interval=interval)
        else:
            raise RuntimeError(f"nvidia-smi probe failed: {result.stderr.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, RuntimeError) as exc:
        logger.info("GPU monitor using fallback mode: %s", exc)
        return FallbackGPUMonitor(interval=interval)


__all__ = ["GPUMonitor", "FallbackGPUMonitor", "GPUReading", "create_gpu_monitor"]
