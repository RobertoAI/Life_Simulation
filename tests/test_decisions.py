import numpy as np; np.random.seed(42)
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.simulation.decisions import decide, ACTION_IDS


def test_hungry_agent_eats():
    n = 10
    hunger = np.full(n, 95.0, dtype=np.float32)  # Very hungry
    energy = np.full(n, 50.0, dtype=np.float32)
    fertility = np.full(n, 0.3, dtype=np.float32)
    nearby_food = np.full(n, 0.8, dtype=np.float32)  # Food nearby
    nearby_mates = np.full(n, 0.0, dtype=np.float32)
    threat = np.zeros(n, dtype=np.float32)
    p_openness = np.full(n, 0.3, dtype=np.float32)
    p_conscientiousness = np.full(n, 0.3, dtype=np.float32)
    p_extraversion = np.full(n, 0.3, dtype=np.float32)
    p_agreeableness = np.full(n, 0.3, dtype=np.float32)
    p_neuroticism = np.full(n, 0.2, dtype=np.float32)
    intelligence = np.full(n, 0.5, dtype=np.float32)

    actions = decide(
        hunger=hunger, energy=energy, fertility=fertility,
        nearby_food=nearby_food, nearby_mates=nearby_mates,
        threat=threat, p_openness=p_openness,
        p_conscientiousness=p_conscientiousness, p_extraversion=p_extraversion,
        p_agreeableness=p_agreeableness, p_neuroticism=p_neuroticism,
        intelligence=intelligence,
    )
    # Hungry agents with food nearby should predominantly choose eat (action 0)
    eat_count = np.sum(actions == ACTION_IDS['eat'])
    assert eat_count > n * 0.5, f"Expected most hungry agents to eat, got {eat_count}/{n}"


def test_flee_threat():
    n = 10
    hunger = np.full(n, 10.0, dtype=np.float32)
    energy = np.full(n, 60.0, dtype=np.float32)
    fertility = np.full(n, 0.3, dtype=np.float32)
    nearby_food = np.full(n, 0.1, dtype=np.float32)
    nearby_mates = np.full(n, 0.0, dtype=np.float32)
    threat = np.full(n, 0.9, dtype=np.float32)  # High threat
    p_openness = np.full(n, 0.3, dtype=np.float32)
    p_conscientiousness = np.full(n, 0.3, dtype=np.float32)
    p_extraversion = np.full(n, 0.3, dtype=np.float32)
    p_agreeableness = np.full(n, 0.3, dtype=np.float32)
    p_neuroticism = np.full(n, 0.9, dtype=np.float32)  # High neuroticism
    intelligence = np.full(n, 0.5, dtype=np.float32)

    actions = decide(
        hunger=hunger, energy=energy, fertility=fertility,
        nearby_food=nearby_food, nearby_mates=nearby_mates,
        threat=threat, p_openness=p_openness,
        p_conscientiousness=p_conscientiousness, p_extraversion=p_extraversion,
        p_agreeableness=p_agreeableness, p_neuroticism=p_neuroticism,
        intelligence=intelligence,
    )
    flee_count = np.sum(actions == ACTION_IDS['flee'])
    assert flee_count > n * 0.5, f"Expected most threatened agents to flee, got {flee_count}/{n}"


def test_reproduce():
    n = 10
    hunger = np.full(n, 10.0, dtype=np.float32)
    energy = np.full(n, 95.0, dtype=np.float32)  # High energy
    fertility = np.full(n, 0.9, dtype=np.float32)  # High fertility
    nearby_food = np.full(n, 0.3, dtype=np.float32)
    nearby_mates = np.full(n, 0.8, dtype=np.float32)  # Mates available
    threat = np.zeros(n, dtype=np.float32)
    p_openness = np.full(n, 0.3, dtype=np.float32)
    p_conscientiousness = np.full(n, 0.3, dtype=np.float32)
    p_extraversion = np.full(n, 0.5, dtype=np.float32)
    p_agreeableness = np.full(n, 0.5, dtype=np.float32)
    p_neuroticism = np.full(n, 0.2, dtype=np.float32)
    intelligence = np.full(n, 0.5, dtype=np.float32)

    actions = decide(
        hunger=hunger, energy=energy, fertility=fertility,
        nearby_food=nearby_food, nearby_mates=nearby_mates,
        threat=threat, p_openness=p_openness,
        p_conscientiousness=p_conscientiousness, p_extraversion=p_extraversion,
        p_agreeableness=p_agreeableness, p_neuroticism=p_neuroticism,
        intelligence=intelligence,
    )
    reproduce_count = np.sum(actions == ACTION_IDS['reproduce'])
    assert reproduce_count > 0, "Expected some agents to choose reproduce"


def test_action_range():
    n = 100
    np.random.seed(42)
    actions = decide(
        hunger=np.random.uniform(0, 100, n).astype(np.float32),
        energy=np.random.uniform(0, 100, n).astype(np.float32),
        fertility=np.random.uniform(0, 1, n).astype(np.float32),
        nearby_food=np.random.uniform(0, 1, n).astype(np.float32),
        nearby_mates=np.random.uniform(0, 1, n).astype(np.float32),
        threat=np.random.uniform(0, 1, n).astype(np.float32),
        p_openness=np.random.uniform(0, 1, n).astype(np.float32),
        p_conscientiousness=np.random.uniform(0, 1, n).astype(np.float32),
        p_extraversion=np.random.uniform(0, 1, n).astype(np.float32),
        p_agreeableness=np.random.uniform(0, 1, n).astype(np.float32),
        p_neuroticism=np.random.uniform(0, 1, n).astype(np.float32),
        intelligence=np.random.uniform(0, 1, n).astype(np.float32),
    )
    assert np.all(actions >= 0) and np.all(actions <= 5), "All actions must be in range 0-5"
