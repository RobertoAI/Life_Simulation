#!/usr/bin/env python3
"""CLI script to run the Life Simulation benchmark suite.

Usage:
    python scripts/run_benchmark.py --agents 10000 --ticks 100 --output benchmark.json
    python scripts/run_benchmark.py --agents 1000 5000 10000 --ticks 200
    python scripts/run_benchmark.py --agents 1000 --ticks 50 --pheromones --advanced-behaviors
"""

import argparse
import json
import sys
import os
import time

# Ensure backend is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.simulation.benchmark import run_benchmark, save_report


def main():
    parser = argparse.ArgumentParser(
        description="Life Simulation Benchmark Suite"
    )
    parser.add_argument(
        "--agents", "-n",
        type=int,
        nargs="+",
        default=[1000, 5000, 10000],
        help="Agent population sizes to benchmark (default: 1000 5000 10000)",
    )
    parser.add_argument(
        "--ticks", "-t",
        type=int,
        default=100,
        help="Number of ticks to run per benchmark (default: 100)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="benchmark.json",
        help="Output JSON file path (default: benchmark.json)",
    )
    parser.add_argument(
        "--pheromones",
        action="store_true",
        default=False,
        help="Enable pheromone system during benchmark",
    )
    parser.add_argument(
        "--advanced-behaviors",
        action="store_true",
        default=False,
        help="Enable advanced behaviors during benchmark",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print(f"Life Simulation Benchmark Suite")
    print(f"  Agent counts: {args.agents}")
    print(f"  Ticks: {args.ticks}")
    print(f"  Pheromones: {'enabled' if args.pheromones else 'disabled'}")
    print(f"  Advanced behaviors: {'enabled' if args.advanced_behaviors else 'disabled'}")
    print(f"  Output: {args.output}")
    print()

    start_time = time.time()

    report = run_benchmark(
        agent_counts=args.agents,
        ticks=args.ticks,
        enable_pheromones=args.pheromones,
        enable_advanced_behaviors=args.advanced_behaviors,
        verbose=not args.quiet,
    )

    elapsed = time.time() - start_time

    # Add timing info
    report["wall_clock_seconds"] = elapsed

    # Save report
    save_report(report, args.output)

    print()
    print(f"Benchmark complete in {elapsed:.1f}s")
    print(f"Results saved to {args.output}")

    # Print summary
    summary = report.get("summary", {})
    for pop, tps in summary.get("tps_by_population", {}).items():
        mt = summary.get("mean_tick_ms_by_population", {}).get(pop, 0)
        print(f"  {pop:>6} agents: {tps:>8.1f} ticks/s  ({mt:.1f} ms/tick)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
