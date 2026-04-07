
"""Genome system - genes, mutation, and inheritance for agents."""

import numpy as np
from typing import Dict

# Gene names and their properties
GENE_NAMES = [
    "speed",
    "metabolism", 
    "fertility",
    "resilience",
    "aggression",
    "intelligence",
    "size",
    "vision_range",
]

# Vision range is integer 1-10, all others are float32 [0,1]
INTEGER_GENES = {"vision_range"}


def random_genome(n: int) -> Dict[str, np.ndarray]:
    """Generate n random genomes as dict of numpy arrays.
    
    Args:
        n: Number of genomes to generate.
        
    Returns:
        Dict mapping gene name to numpy array of shape (n,).
    """
    genome = {}
    for gene in GENE_NAMES:
        if gene in INTEGER_GENES:
            genome[gene] = np.random.randint(1, 11, size=n, dtype=np.int32)
        else:
            genome[gene] = np.random.random(size=n).astype(np.float32)
    return genome


def crossover(
    parent1_genes: Dict[str, np.ndarray],
    parent2_genes: Dict[str, np.ndarray],
    child_idx: int,
) -> Dict[str, float]:
    """Perform crossover between two parent genomes for a single child.
    
    Args:
        parent1_genes: Dict of gene arrays for parent 1.
        parent2_genes: Dict of gene arrays for parent 2.
        child_idx: Index of this child among all children being spawned.
        
    Returns:
        Dict mapping gene name to single value for the child.
    """
    child = {}
    for gene in GENE_NAMES:
        # Randomly pick allele from either parent (uniform crossover)
        if np.random.random() < 0.5:
            child[gene] = parent1_genes[gene][child_idx]
        else:
            child[gene] = parent2_genes[gene][child_idx]
    return child


def mutate(
    genes: Dict[str, float],
    rate: float = 0.05,
    magnitude: float = 0.1,
) -> Dict[str, float]:
    """Apply random mutation to a genome dict.
    
    Args:
        genes: Dict of gene name to value.
        rate: Probability that any given gene will mutate.
        magnitude: Maximum change magnitude for a mutation.
        
    Returns:
        Mutated genes dict.
    """
    mutated = {}
    for gene, value in genes.items():
        if np.random.random() < rate:
            if gene in INTEGER_GENES:
                delta = int(np.random.randint(-1, 2))
                mutated[gene] = np.clip(value + delta, 1, 10)
            else:
                delta = np.random.uniform(-magnitude, magnitude)
                mutated[gene] = float(np.clip(value + delta, 0.0, 1.0))
        else:
            mutated[gene] = value
    return mutated
