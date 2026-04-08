#!/usr/bin/env python3
"""
Fendt PESTEL-EL Sentinel — Production Orchestrator
====================================================

Canonical entry point for the autonomous disruption detection pipeline.
Uses the SchedulerRegistry from core.scheduler so new intelligence use
cases can be plugged in without touching this file.

Usage::

    python sentinel.py --run-once              # Run the default use case
    python sentinel.py --use-case fendt-pestel # Run a specific use case
    python sentinel.py --run-all               # Run every registered use case
    python sentinel.py --list                  # List registered use cases
    python sentinel.py --status                # Show database statistics
"""

import argparse
import sys
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "q2_solution"))
sys.path.insert(0, str(PROJECT_ROOT))

# ── Imports ─────────────────────────────────────────────────────────────────
from core.scheduler import registry, UseCase  # noqa: E402
from database import SignalDatabase            # noqa: E402
from q2_pipeline import Q2Pipeline, get_sample_signals  # noqa: E402

# ── Use-case registration ────────────────────────────────────────────────────
# Add new use cases here.  Core scheduler logic is never modified.

_OUTPUTS_DIR = PROJECT_ROOT / "outputs"


def _run_fendt_pestel() -> dict:
    """Fendt PESTEL-EL industry disruption detection (sample signals)."""
    pipeline = Q2Pipeline(output_dir=str(_OUTPUTS_DIR))
    raw_signals = get_sample_signals()
    print(f"  ✓ Loaded {len(raw_signals)} signals")
    result = pipeline.run(raw_signals)
    # Normalise key names to match scheduler expectations
    return {
        "total_processed": result.get("signals_processed"),
        "critical_count":  result.get("critical_disruptions"),
        "high_count":      result.get("high_disruptions"),
        "outputs":         result.get("outputs", {}),
        "timestamp":       result.get("timestamp"),
    }


registry.register(UseCase(
    name="fendt-pestel",
    run_fn=_run_fendt_pestel,
    output_dir=_OUTPUTS_DIR,
    description="Fendt PESTEL-EL industry disruption detection",
))

# ── CLI helpers ──────────────────────────────────────────────────────────────

def show_status() -> None:
    """Print current database statistics."""
    db = SignalDatabase()
    stats = db.get_database_stats()
    width = 60
    print("\n" + "=" * width)
    print("SENTINEL STATUS")
    print("=" * width)
    print(f"  Total signals   : {stats['total_signals']}")
    print(f"  Date range      : {stats['date_range']['earliest']} → {stats['date_range']['latest']}")
    print(f"  Dimensions      : {', '.join(stats.get('dimensions', []))}")
    print("=" * width)


def list_use_cases() -> None:
    """Print all registered use cases."""
    print("\nRegistered use cases:")
    for name in registry.registered:
        uc = registry._use_cases[name]
        print(f"  • {name:<24} {uc.description}")


def print_run_result(results: dict) -> None:
    width = 60
    print("\n" + "=" * width)
    print("SENTINEL PIPELINE COMPLETE")
    print("=" * width)
    for name, result in results.items():
        if "error" in result:
            print(f"  ✗ {name}: {result['error']}")
        else:
            print(f"  ✓ {name}")
            print(f"      Signals processed : {result.get('total_processed', 'N/A')}")
            print(f"      Critical          : {result.get('critical_count', 'N/A')}")
            print(f"      Output dir        : {_OUTPUTS_DIR}")
    print("=" * width)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fendt PESTEL-EL Sentinel — Autonomous Disruption Detection"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Execute the default use case (fendt-pestel)",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Execute every registered use case",
    )
    parser.add_argument(
        "--use-case",
        type=str,
        default="fendt-pestel",
        metavar="NAME",
        help="Use-case name to run with --run-once (default: fendt-pestel)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all registered use cases",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current database statistics",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.list:
        list_use_cases()
    elif args.run_all:
        results = registry.run_all()
        print_run_result(results)
    elif args.run_once:
        result = registry.run(args.use_case)
        print_run_result({args.use_case: result})
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
