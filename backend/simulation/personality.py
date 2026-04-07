
"""Personality system - Big Five personality traits for agents."""

import numpy as np
from typing import Dict

# Big Five personality trait names
PERSONALITY_TRAITS = [
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
]


def random_personality(n: int) -> Dict[str, np.ndarray]:
    """Generate n random personalities using the Big Five model.
    
    All traits are float32 in range [0, 1].
    
    Args:
        n: Number of personalities to generate.
        
    Returns:
        Dict mapping trait name to numpy array of shape (n,).
    """
    personality = {}
    for trait in PERSONALITY_TRAITS:
        personality[trait] = np.random.random(size=n).astype(np.float32)
    return personality
