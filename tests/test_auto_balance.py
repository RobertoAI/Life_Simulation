import numpy as np; np.random.seed(42)
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.config import Settings
from backend.simulation.auto_balance import AutoBalancer


@pytest.fixture
def balancer():
    config = Settings()
    config.initial_population = 1000
    config.max_agents = 10000
    return AutoBalancer(config)


def test_auto_balancer_creation():
    config = Settings()
    config.initial_population = 500
    config.max_agents = 5000
    ab = AutoBalancer(config)
    assert ab is not None
    assert hasattr(ab, '_enabled')
    assert hasattr(ab, '_adjustment_history')


def test_enabled_by_default():
    config = Settings()
    ab = AutoBalancer(config)
    assert ab.enabled is True
    ab.disable()
    assert ab.enabled is False
    ab.enable()
    assert ab.enabled is True


def test_get_adjustment_history_empty_initially():
    config = Settings()
    ab = AutoBalancer(config)
    history = ab.get_adjustment_history()
    assert isinstance(history, list)
    assert len(history) == 0
