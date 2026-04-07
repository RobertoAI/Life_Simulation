import numpy as np; np.random.seed(42)
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.config import Settings
from backend.simulation.engine import SimulationEngine


def test_start_stops_cleanly():
    config = Settings()
    config.initial_population = 50
    config.grid_width = 64
    config.grid_height = 64
    config.max_agents = 200
    engine = SimulationEngine(config)
    assert engine.status == "stopped"
    # Start then stop
    import asyncio
    async def _run():
        await engine.start()
        assert engine.status == "running"
        await engine.stop()
        assert engine.status == "stopped"
    asyncio.get_event_loop().run_until_complete(_run())


def test_tick_loop_10_ticks():
    config = Settings()
    config.initial_population = 30
    config.grid_width = 64
    config.grid_height = 64
    config.max_agents = 200
    engine = SimulationEngine(config)
    import asyncio
    async def _run():
        await engine.start()
        for _ in range(10):
            metrics = await engine.tick()
            assert isinstance(metrics, dict)
        assert engine.tick_count >= 10
        await engine.stop()
    asyncio.get_event_loop().run_until_complete(_run())


def test_pause_then_resume():
    config = Settings()
    config.initial_population = 50
    config.grid_width = 64
    config.grid_height = 64
    config.max_agents = 200
    engine = SimulationEngine(config)
    import asyncio
    async def _run():
        await engine.start()
        assert engine.status == "running"
        await engine.pause()  # First pause
        assert engine.status == "paused"
        await engine.pause()  # Second call resumes
        assert engine.status == "running"
        await engine.stop()
    asyncio.get_event_loop().run_until_complete(_run())


def test_profile_report_returns_dict():
    config = Settings()
    config.initial_population = 50
    config.grid_width = 64
    config.grid_height = 64
    config.max_agents = 200
    engine = SimulationEngine(config)
    report = engine.profile_report()
    assert isinstance(report, dict)
    # After no ticks, should still have structure
    assert 'total' in report or 'phases' in report or 'summary' in report
