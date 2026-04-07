
"""Utility-based decision system for agent actions.

All functions are fully vectorized with numpy -- no Python loops over agents.

Actions:
    0 = eat
    1 = move
    2 = reproduce
    3 = rest
    4 = flee
    5 = idle
"""

import numpy as np

ACTION_IDS = {
    "eat": 0,
    "move": 1,
    "reproduce": 2,
    "rest": 3,
    "flee": 4,
    "idle": 5,
}


def compute_eat_utility(
    hunger: np.ndarray,
    nearby_food: np.ndarray,
    distance: np.ndarray,
    intelligence: np.ndarray,
) -> np.ndarray:
    """Compute utility of eating action.
    
    Higher hunger and more nearby food increase utility.
    Intelligence reduces the distance penalty (smarter agents plan better).
    """
    hunger_factor = hunger / 100.0  # Normalize to [0, 1]
    food_factor = np.clip(nearby_food, 0.0, 1.0)
    # Smarter agents suffer less from distance
    effective_distance = distance / (1.0 + intelligence * 2.0)
    distance_factor = 1.0 / (1.0 + effective_distance)
    
    return 3.0 * hunger_factor * food_factor * distance_factor


def compute_move_utility(
    openness: np.ndarray,
    nearby_resources: np.ndarray,
    distance: np.ndarray,
) -> np.ndarray:
    """Compute utility of moving action.
    
    More open agents are more likely to explore further.
    """
    exploration_drive = 0.5 + 0.5 * openness  # [0.5, 1.0]
    resource_pull = np.clip(nearby_resources, 0.0, 1.0)
    distance_factor = 1.0 / (1.0 + distance * 0.5)
    
    return 1.5 * exploration_drive * resource_pull * distance_factor


def compute_reproduce_utility(
    energy: np.ndarray,
    fertility: np.ndarray,
    nearby_mates: np.ndarray,
) -> np.ndarray:
    """Compute utility of reproducing action.
    
    Requires sufficient energy and fertility.
    """
    energy_factor = np.clip((energy - 50.0) / 50.0, 0.0, 1.0)
    fertility_factor = fertility  # Already [0, 1]
    mate_factor = np.clip(nearby_mates, 0.0, 1.0)
    
    return 2.5 * energy_factor * fertility_factor * mate_factor


def compute_rest_utility(
    energy: np.ndarray,
    safety_score: np.ndarray,
) -> np.ndarray:
    """Compute utility of resting action.
    
    Low energy agents prefer to rest, especially in safe environments.
    """
    need_rest = np.clip((80.0 - energy) / 80.0, 0.0, 1.0)
    safety_factor = np.clip(safety_score, 0.0, 1.0)
    
    return 2.0 * need_rest * (0.5 + 0.5 * safety_factor)


def compute_flee_utility(
    threat_detected: np.ndarray,
    neuroticism: np.ndarray,
) -> np.ndarray:
    """Compute utility of fleeing action.
    
    Higher neuroticism increases flight response to perceived threats.
    """
    threat_factor = np.clip(threat_detected, 0.0, 1.0)
    fear_factor = 0.3 + 0.7 * neuroticism  # neurotic agents are more fearful
    
    return 3.0 * threat_factor * fear_factor


def _compute_distance(
    agent_x: np.ndarray,
    agent_y: np.ndarray,
    target_x: np.ndarray,
    target_y: np.ndarray,
) -> np.ndarray:
    """Compute euclidean distance between agent positions and target positions."""
    dx = agent_x - target_x
    dy = agent_y - target_y
    return np.sqrt(dx * dx + dy * dy)


def decide(
    hunger: np.ndarray,
    energy: np.ndarray,
    fertility: np.ndarray,
    nearby_food: np.ndarray,
    nearby_mates: np.ndarray,
    threat: np.ndarray,
    p_openness: np.ndarray,
    p_conscientiousness: np.ndarray,
    p_extraversion: np.ndarray,
    p_agreeableness: np.ndarray,
    p_neuroticism: np.ndarray,
    intelligence: np.ndarray,
    agent_x: np.ndarray | None = None,
    agent_y: np.ndarray | None = None,
    target_x: np.ndarray | None = None,
    target_y: np.ndarray | None = None,
) -> np.ndarray:
    """Determine the best action for each agent based on utility scores.
    
    All inputs should be 1D numpy arrays of the same length (one per agent).
    Position arrays are optional; if provided they refine distance-based utilities.
    
    Args:
        hunger: Hunger level for each agent [0, 100]
        energy: Energy level for each agent [0, 100]
        fertility: Genome fertility gene [0, 1]
        nearby_food: How much food is nearby [0, 1]
        nearby_mates: How many mates are nearby [0, 1]
        threat: Threat level detected [0, 1]
        p_openness: Openness personality trait [0, 1]
        p_conscientiousness: Conscientiousness personality trait [0, 1]
        p_extraversion: Extraversion personality trait [0, 1]
        p_agreeableness: Agreeableness personality trait [0, 1]
        p_neuroticism: Neuroticism personality trait [0, 1]
        intelligence: Genome intelligence gene [0, 1]
        agent_x: Optional agent x positions
        agent_y: Optional agent y positions
        target_x: Optional target x positions (for distance calculation)
        target_y: Optional target y positions (for distance calculation)
        
    Returns:
        Array of action IDs (0-5), one per agent.
    """
    n = len(hunger)
    
    # Default distance estimates when positions not provided
    if agent_x is not None and target_x is not None:
        distances = _compute_distance(agent_x, agent_y, target_x, target_y)
    else:
        # Use a moderate default distance inversely proportional to nearby_food
        distances = 1.0 / (0.1 + nearby_food)
    
    clamp = lambda v, lo, hi: np.clip(v, lo, hi)
    
    # Safety score influenced by agreeableness and conscientiousness
    safety_score = 0.5 * p_agreeableness + 0.5 * p_conscientiousness
    
    # Compute utility for each action
    eat_utility = compute_eat_utility(hunger, nearby_food, distances, intelligence)
    move_utility = compute_move_utility(p_openness, nearby_food, distances)
    reproduce_utility = compute_reproduce_utility(energy, fertility, nearby_mates)
    rest_utility = compute_rest_utility(energy, safety_score)
    flee_utility = compute_flee_utility(threat, p_neuroticism)
    
    # Idle utility is the baseline (always an option, scaled by conscientiousness)
    idle_utility = np.full(n, 0.5, dtype=np.float32) * (0.5 + 0.5 * p_conscientiousness)
    
    # Stack all utilities and pick the action with maximum utility
    utilities = np.stack([
        eat_utility,
        move_utility,
        reproduce_utility,
        rest_utility,
        flee_utility,
        idle_utility,
    ], axis=1)  # shape: (n, 6)
    
    # Return the action with highest utility for each agent
    return np.argmax(utilities, axis=1).astype(np.int32)
