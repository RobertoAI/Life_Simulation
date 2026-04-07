import numpy as np; np.random.seed(42)
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.simulation.events import EventSystem, ActiveEvent, EVENT_EFFECTS


def test_event_system_creation():
    es = EventSystem(grid_width=64, grid_height=64)
    assert es.grid_width == 64
    assert es.grid_height == 64
    assert isinstance(es._active_events, list)
    assert len(es._active_events) == 0  # No events at start


def test_event_generation_at_tick_200():
    es = EventSystem(grid_width=64, grid_height=64)
    # The event system schedules first event between 100-300 ticks from 0
    # So by tick 200 there's a good chance an event was generated
    # We force the schedule to be early for deterministic testing
    es._next_event_tick = 150  # Force event to be available by tick 200
    grid = np.zeros((64, 64), dtype=np.int32)
    temperature = np.zeros((64, 64), dtype=np.float32)
    humidity = np.zeros((64, 64), dtype=np.float32)
    resources = np.zeros((64, 64), dtype=np.float32)
    active = es.process(grid, temperature, humidity, resources, tick_count=200)
    # Should have generated at least one event
    assert len(active) >= 1
    # Verify event structure
    for event in active:
        assert isinstance(event, ActiveEvent)
        assert event.type in EVENT_EFFECTS
        assert event.severity >= 0.2
        assert event.remaining > 0


def test_storm_reduces_resources():
    es = EventSystem(grid_width=64, grid_height=64)
    # Create a storm event manually
    storm = ActiveEvent(
        event_type="storm",
        severity=0.5,
        center_x=32, center_y=32,
        radius=20,
        duration=5,
        effect_type="storm",
    )
    es._active_events.append(storm)

    grid = np.zeros((64, 64), dtype=np.int32)
    temperature = np.zeros((64, 64), dtype=np.float32)
    humidity = np.zeros((64, 64), dtype=np.float32)
    resources = np.ones((64, 64), dtype=np.float32) * 0.5  # Start with 0.5 resources

    before_sum = resources.sum()
    es.process(grid, temperature, humidity, resources, tick_count=5)
    after_sum = resources.sum()

    # Storm should reduce resources
    assert after_sum < before_sum, f"Resources not reduced: {after_sum} >= {before_sum}"
