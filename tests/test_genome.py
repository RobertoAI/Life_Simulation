import numpy as np; np.random.seed(42)
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.simulation import genome


def test_crossover_mixes_parents():
    p1 = genome.random_genome(1)
    p2 = genome.random_genome(1)
    child = genome.crossover(p1, p2, child_idx=0)
    # Child should have all the same keys
    assert set(child.keys()) == set(genome.GENE_NAMES)
    # Run many crossovers to verify mixing
    p1_arrs = genome.random_genome(100)
    p2_arrs = genome.random_genome(100)
    children = [genome.crossover(p1_arrs, p2_arrs, child_idx=i) for i in range(100)]
    # At least some children should have taken from parent1 and some from parent2
    speeds = [c['speed'] for c in children]
    from_p1 = sum(1 for i, sp in enumerate(speeds) if abs(sp - p1_arrs['speed'][i]) < 1e-6)
    from_p2 = sum(1 for i, sp in enumerate(speeds) if abs(sp - p2_arrs['speed'][i]) < 1e-6)
    assert from_p1 > 0
    assert from_p2 > 0


def test_mutation_changes_some_genes():
    genes = {
        'speed': 0.5, 'metabolism': 0.5, 'fertility': 0.5,
        'resilience': 0.5, 'aggression': 0.5, 'intelligence': 0.5,
        'size': 0.5, 'vision_range': 5,
    }
    # Run many mutation trials to ensure some genes actually change
    any_changed = False
    for _ in range(50):
        mutated = genome.mutate(genes, rate=0.5, magnitude=0.3)  # High rate
        if mutated != genes:
            any_changed = True
            break
    assert any_changed, "Mutation should change at least one gene with high rate"

    # Also verify values stay in range
    mutated = genome.mutate(genes, rate=1.0, magnitude=0.1)  # Mutate everything
    for gene_name, val in mutated.items():
        if gene_name == 'vision_range':
            assert 1 <= val <= 10
        else:
            assert 0.0 <= val <= 1.0


def test_random_genome_valid():
    g = genome.random_genome(50)
    assert set(g.keys()) == set(genome.GENE_NAMES)
    for gene_name, arr in g.items():
        assert len(arr) == 50
        if gene_name == 'vision_range':
            assert arr.dtype == np.int32
            assert np.all(arr >= 1) and np.all(arr <= 10)
        else:
            assert arr.dtype == np.float32
            assert np.all(arr >= 0.0) and np.all(arr <= 1.0)
