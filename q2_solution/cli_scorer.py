#!/usr/bin/env python3
"""
CLI Wrapper for Disruption Scoring
===================================

Usage:
    python cli_scorer.py "The EU has just mandated a 40% reduction in synthetic fertilizer use by 2028."

Output:
    Disruption Score: 0.76 (CRITICAL)
    Time Horizon: 12_MONTH
"""

import sys
from signal_classifier import SignalClassifier
from disruption_scorer import DisruptionScorer


def main():
    if len(sys.argv) < 2:
        print("Usage: python cli_scorer.py \"<signal text>\"")
        print("Example: python cli_scorer.py \"The EU has mandated 40% fertilizer reduction by 2028.\"")
        sys.exit(1)

    # Get signal text from command line
    signal_text = " ".join(sys.argv[1:])

    # Create minimal signal dict
    signal = {
        'title': signal_text[:100],  # First 100 chars as title
        'content': signal_text,
        'source': 'CLI Input',
        'url': 'https://cli.local',
        'date': '2024-01-01'
    }

    # Initialize classifier and scorer
    classifier = SignalClassifier()
    scorer = DisruptionScorer()

    # Classify
    classified = classifier.classify_signal(signal)

    # Score
    scored = scorer.score_signal(classified)

    # Output results
    print(f"Disruption Score: {scored['disruption_score']:.2f} ({scored['classification']})")
    print(f"Time Horizon: {scored['temporal_metadata']['time_horizon']}")
    print(f"Primary PESTEL Dimension: {scored['primary_dimension']}")
    print(f"Novelty: {scored['novelty_score']:.2f} | Impact: {scored['impact_score']:.2f} | Velocity: {scored['velocity_score']:.2f}")


if __name__ == "__main__":
    main()
