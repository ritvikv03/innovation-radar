#!/usr/bin/env python3
"""
Fendt PESTEL-EL Sentinel — Production Orchestrator
====================================================

Canonical entry point for the autonomous disruption detection pipeline.
Wraps Q2Pipeline (which writes to SQLite via database.py) so every
component in the system shares a single data path.

Usage:
    python sentinel.py --run-once          # Single pipeline execution
    python sentinel.py --agent scout       # Run a specific agent stage
    python sentinel.py --status            # Show database stats
"""

import argparse
import sys
from pathlib import Path

# Ensure q2_solution is importable
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "q2_solution"))

from q2_pipeline import Q2Pipeline, get_sample_signals
from database import SignalDatabase


def run_pipeline(use_sample: bool = True):
    """Execute the full Q2 disruption detection pipeline."""
    pipeline = Q2Pipeline(output_dir="./outputs")

    if use_sample:
        raw_signals = get_sample_signals()
        print(f"✓ Loaded {len(raw_signals)} sample signals")
    else:
        # Future: ingest from raw_ingest/*.json or live APIs
        raw_signals = get_sample_signals()
        print(f"✓ Loaded {len(raw_signals)} signals (sample fallback)")

    results = pipeline.run(raw_signals)

    print("\n" + "=" * 60)
    print("SENTINEL PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Signals processed : {results.get('total_processed', 'N/A')}")
    print(f"  Critical signals  : {results.get('critical_count', 'N/A')}")
    print(f"  Reports generated : {results.get('reports_generated', 'N/A')}")
    print(f"  Output directory  : ./outputs/")
    print("=" * 60)

    return results


def show_status():
    """Display current database statistics."""
    db = SignalDatabase()
    stats = db.get_database_stats()

    print("\n" + "=" * 60)
    print("SENTINEL STATUS")
    print("=" * 60)
    print(f"  Total signals   : {stats['total_signals']}")
    print(f"  Date range      : {stats['date_range']['earliest']} → {stats['date_range']['latest']}")
    print(f"  Dimensions      : {', '.join(stats.get('dimensions', []))}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Fendt PESTEL-EL Sentinel — Autonomous Disruption Detection"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Execute a single pipeline run with sample data"
    )
    parser.add_argument(
        "--agent",
        type=str,
        choices=["scout", "classifier", "evaluator", "writer"],
        help="Run a specific agent stage (future use)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current database statistics"
    )

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.run_once:
        run_pipeline(use_sample=True)
    elif args.agent:
        print(f"Agent '{args.agent}' execution is reserved for production deployment.")
        print("Use --run-once to execute the full pipeline with sample data.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
