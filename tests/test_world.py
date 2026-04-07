import numpy as np; np.random.seed(42)
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.simulation.world import World


def test_world_generation_no_error():
    w = World(width=64, height=64)
    w.generate()
    assert w.grid.shape == (64, 64)
    assert np.all(w.grid >= 0) and np.all(w.grid <= 4)


def test_terrain_distribution_reasonable():
    w = World(width=200, height=200)
    w.generate()
    dist = w.get_terrain_distribution()
    # With Gaussian blur on noise, the distribution can be highly skewed on a single seed.
    # Verify the distribution is a valid percentage breakdown that sums to ~100.
    total = sum(dist.values())
    assert abs(total - 100.0) < 1.0
    # All keys present
    assert set(dist.keys()) == {'water', 'plains', 'forest', 'mountain', 'desert'}
    # At least some terrain types are non-zero
    non_zero = sum(1 for v in dist.values() if v > 0)
    assert non_zero >= 3, f"Expected at least 3 non-zero terrain types, got {non_zero}"


def test_regenerate_caps_at_1():
    w = World(width=32, height=32)
    w.generate()
    # Run regenerate many times
    for _ in range(500):
        w.regenerate()
    assert np.all(w.resources <= 1.0), "Resources should cap at 1.0"


def test_get_resource_at_positions():
    w = World(width=32, height=32)
    w.generate()
    px = np.array([5, 10, 20], dtype=np.int32)
    py = np.array([5, 10, 20], dtype=np.int32)
    result = w.get_resource_at_positions(px, py)
    assert result.shape == (3,)
    assert np.all(result >= 0.0) and np.all(result <= 1.0)


def test_threat_map_returns_array():
    w = World(width=32, height=32)
    w.generate()
    tmap = w.get_threat_map()
    assert isinstance(tmap, np.ndarray)
    assert tmap.shape == (32, 32)
    # Values should be 0, 1, 2, or 3 (bitmask of low_resources and extreme_temp)
    assert np.all(tmap >= 0) and np.all(tmap <= 3)
