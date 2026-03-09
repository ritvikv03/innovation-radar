"""
Unit tests for Disruption Scorer
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'q2_solution'))

from signal_classifier import SignalClassifier
from disruption_scorer import DisruptionScorer


def test_score_critical_disruption():
    """Test scoring of CRITICAL disruption signal."""
    classifier = SignalClassifier()
    scorer = DisruptionScorer()

    signal = {
        'title': 'EU Mandates Complete Diesel Ban for Agricultural Machinery by 2027',
        'content': 'Unprecedented regulatory mandate requires all new agricultural equipment '
                  'to be electric or hydrogen-powered by 2027. Immediate industry transformation. '
                  'Stage VI emissions regulation enforcement. Autonomous electric tractors required.',
        'source': 'EUR-Lex',
        'url': 'https://eur-lex.europa.eu/test',
        'date': '2024-03-15'
    }

    classified = classifier.classify_signal(signal)
    result = scorer.score_signal(classified)

    assert result['disruption_score'] >= 0.50, \
        f"Expected HIGH/CRITICAL score, got {result['disruption_score']:.2f}"
    assert result['classification'] in ['HIGH', 'CRITICAL'], \
        f"Expected HIGH or CRITICAL, got {result['classification']}"
    assert result['impact_score'] > 0.3, \
        f"Regulatory mandate should have high impact, got {result['impact_score']:.2f}"
    print("✓ test_score_critical_disruption passed")


def test_score_low_disruption():
    """Test scoring of LOW disruption signal."""
    scorer = DisruptionScorer()

    # Pre-classified low-impact signal
    signal = {
        'title': 'Minor Update to Tractor Safety Guidelines',
        'content': 'Small procedural change to existing safety standards.',
        'primary_dimension': 'LEGAL',
        'secondary_dimensions': [],
        'entities': {'regulations': [], 'technologies': []},
        'temporal_metadata': {
            'mentioned_years': ['2030'],
            'time_horizon': '36_MONTH',
            'urgency': 'LOW'
        }
    }

    result = scorer.score_signal(signal)

    assert result['disruption_score'] < 0.50, \
        f"Expected LOW/MODERATE score, got {result['disruption_score']:.2f}"
    assert result['classification'] in ['LOW', 'MODERATE'], \
        f"Expected LOW or MODERATE, got {result['classification']}"
    print("✓ test_score_low_disruption passed")


def test_novelty_calculation():
    """Test novelty score calculation vs historical signals."""
    historical = [
        {'title': 'Electric Tractors Gain Market Share'},
        {'title': 'Solar-Powered Farm Equipment Growing'},
        {'title': 'Battery Technology Improvements for Agriculture'}
    ]

    scorer = DisruptionScorer(historical_signals=historical)

    # Similar signal (low novelty)
    signal_low_novelty = {
        'title': 'Electric Tractors See Continued Growth',
        'primary_dimension': 'TECHNOLOGICAL',
        'secondary_dimensions': [],
        'entities': {'technologies': ['electric']},
        'temporal_metadata': {'time_horizon': '24_MONTH', 'urgency': 'MEDIUM'}
    }

    result_low = scorer.score_signal(signal_low_novelty)
    assert result_low['novelty_score'] < 0.5, \
        f"Expected low novelty (<0.5), got {result_low['novelty_score']:.2f}"

    # Novel signal (high novelty)
    signal_high_novelty = {
        'title': 'Quantum Computing Enables Precision Soil Analysis at Molecular Level',
        'primary_dimension': 'TECHNOLOGICAL',
        'secondary_dimensions': [],
        'entities': {'technologies': ['quantum']},
        'temporal_metadata': {'time_horizon': '36_MONTH', 'urgency': 'LOW'}
    }

    result_high = scorer.score_signal(signal_high_novelty)
    assert result_high['novelty_score'] > 0.5, \
        f"Expected high novelty (>0.5), got {result_high['novelty_score']:.2f}"

    print("✓ test_novelty_calculation passed")


def test_time_horizon_assignment():
    """Test time horizon assignment based on urgency."""
    scorer = DisruptionScorer()

    # High urgency → 12 month
    signal_urgent = {
        'title': 'Immediate Regulation Change',
        'primary_dimension': 'LEGAL',
        'secondary_dimensions': [],
        'entities': {},
        'temporal_metadata': {
            'mentioned_years': ['2024'],
            'time_horizon': '12_MONTH',
            'urgency': 'HIGH'
        }
    }

    result = scorer.score_signal(signal_urgent)
    assert result['time_horizon'] == '12_MONTH', \
        f"Expected 12_MONTH, got {result['time_horizon']}"

    print("✓ test_time_horizon_assignment passed")


def test_score_components():
    """Test that all score components are present and valid."""
    classifier = SignalClassifier()
    scorer = DisruptionScorer()

    signal = {
        'title': 'Test Signal',
        'content': 'Test content with technology and regulation keywords.',
        'source': 'Test',
        'url': 'https://test.com',
        'date': '2024-01-01'
    }

    classified = classifier.classify_signal(signal)
    result = scorer.score_signal(classified)

    # Check all components exist
    assert 'novelty_score' in result, "Missing novelty_score"
    assert 'impact_score' in result, "Missing impact_score"
    assert 'velocity_score' in result, "Missing velocity_score"
    assert 'disruption_score' in result, "Missing disruption_score"
    assert 'classification' in result, "Missing classification"
    assert 'time_horizon' in result, "Missing time_horizon"

    # Check ranges
    assert 0.0 <= result['novelty_score'] <= 1.0, "Novelty score out of range"
    assert 0.0 <= result['impact_score'] <= 1.0, "Impact score out of range"
    assert 0.0 <= result['velocity_score'] <= 1.0, "Velocity score out of range"
    assert 0.0 <= result['disruption_score'] <= 1.0, "Disruption score out of range"

    print("✓ test_score_components passed")


def test_novelty_accounts_for_repeated_content_themes():
    """A signal with a new title but same content themes as history should score lower novelty."""
    historical = [
        {
            'title': 'EU bans diesel agricultural machinery',
            'content': 'electric mandate regulation compliance enforcement ban diesel tractor'
        }
    ]
    scorer = DisruptionScorer(historical_signals=historical)

    # Different title, but shares same core content themes as historical signal
    signal_repeated_content = {
        'title': 'Brussels Acts on Farm Equipment Emissions',  # different title
        'content': 'New electric mandate regulation compliance enforcement ban diesel tractor requirements.',
        'primary_dimension': 'LEGAL',
        'secondary_dimensions': [],
        'entities': {'regulations': ['EU 2026/123'], 'technologies': ['electric']},
        'temporal_metadata': {'time_horizon': '12_MONTH', 'urgency': 'HIGH', 'mentioned_years': ['2026']}
    }

    result = scorer.score_signal(signal_repeated_content)

    assert result['novelty_score'] < 0.6, \
        f"Signal with repeated content themes should score novelty < 0.6, got {result['novelty_score']:.3f}"


if __name__ == "__main__":
    print("=" * 70)
    print("Running Disruption Scorer Tests")
    print("=" * 70)

    test_score_critical_disruption()
    test_score_low_disruption()
    test_novelty_calculation()
    test_time_horizon_assignment()
    test_score_components()
    test_novelty_accounts_for_repeated_content_themes()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✓")
    print("=" * 70)
