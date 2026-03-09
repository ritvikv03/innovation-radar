"""
Unit tests for Signal Classifier
"""

import sys
from pathlib import Path

# Add q2_solution to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'q2_solution'))

from signal_classifier import SignalClassifier


def test_classify_legal_signal():
    """Test classification of legal/regulatory signal."""
    classifier = SignalClassifier()

    signal = {
        'title': 'EU Stage V Emission Standards',
        'content': 'New regulation mandates stricter emission controls. '
                  'Legal compliance required by 2025. Directive 2024/123/EU.',
        'source': 'EUR-Lex',
        'url': 'https://eur-lex.europa.eu/test',
        'date': '2024-03-15'
    }

    result = classifier.classify_signal(signal)

    assert result['primary_dimension'] == 'LEGAL', \
        f"Expected LEGAL, got {result['primary_dimension']}"
    assert 'regulations' in result['entities']
    assert any('stage' in str(reg).lower() for reg in result['entities']['regulations']), \
        f"Stage regulation not extracted: {result['entities']}"
    print("✓ test_classify_legal_signal passed")


def test_classify_technological_signal():
    """Test classification of technology signal."""
    classifier = SignalClassifier()

    signal = {
        'title': 'AI-Powered Autonomous Tractors',
        'content': 'New artificial intelligence algorithms enable autonomous '
                  'tractor navigation using GPS and IoT sensors. Research patents filed.',
        'source': 'Espacenet',
        'url': 'https://espacenet.com/test',
        'date': '2024-02-20'
    }

    result = classifier.classify_signal(signal)

    assert result['primary_dimension'] == 'TECHNOLOGICAL', \
        f"Expected TECHNOLOGICAL, got {result['primary_dimension']}"
    assert len(result['entities']['technologies']) > 0, \
        "No technologies extracted"
    print("✓ test_classify_technological_signal passed")


def test_classify_economic_signal():
    """Test classification of economic signal."""
    classifier = SignalClassifier()

    signal = {
        'title': 'Fertilizer Prices Surge 65%',
        'content': 'Market prices for commodities increased dramatically. '
                  'Economic impact: higher costs for farmers, affecting profit margins.',
        'source': 'Rabobank',
        'url': 'https://rabobank.com/test',
        'date': '2024-01-15'
    }

    result = classifier.classify_signal(signal)

    assert result['primary_dimension'] == 'ECONOMIC', \
        f"Expected ECONOMIC, got {result['primary_dimension']}"
    print("✓ test_classify_economic_signal passed")


def test_entity_extraction():
    """Test entity extraction functionality."""
    classifier = SignalClassifier()

    signal = {
        'title': 'France Launches Precision Agriculture Program',
        'content': 'The French government introduces subsidies for GPS-guided tractors '
                  'and autonomous drones. CAP 2024 Strategic Plan alignment. '
                  'Regulation (EU) 2024/456 compliance required.',
        'source': 'French Ministry',
        'url': 'https://agriculture.gouv.fr/test',
        'date': '2024-03-01'
    }

    result = classifier.classify_signal(signal)

    assert any('france' in str(loc).lower() for loc in result['entities']['locations']), \
        f"France not extracted from locations: {result['entities']['locations']}"
    assert len(result['entities']['technologies']) > 0, \
        "No technologies extracted"
    print("✓ test_entity_extraction passed")


def test_temporal_metadata_extraction():
    """Test temporal metadata extraction."""
    classifier = SignalClassifier()

    signal = {
        'title': 'Urgent: 2024 Emission Standards',
        'content': 'Immediate compliance required by 2025. New regulation effective now.',
        'source': 'Test',
        'url': 'https://test.com',
        'date': '2024-01-01'
    }

    result = classifier.classify_signal(signal)

    temporal = result['temporal_metadata']
    assert '2024' in temporal['mentioned_years'] or '2025' in temporal['mentioned_years'], \
        f"Years not extracted: {temporal['mentioned_years']}"
    assert temporal['time_horizon'] in ['12_MONTH', '24_MONTH', '36_MONTH'], \
        f"Invalid time horizon: {temporal['time_horizon']}"
    print("✓ test_temporal_metadata_extraction passed")


def test_temporal_urgency_current_year_is_high():
    """Current year (2026) in signal content must produce HIGH urgency, not MEDIUM."""
    from datetime import datetime
    classifier = SignalClassifier()
    current_year = str(datetime.now().year)

    signal = {
        'title': f'EU CAP Reform Deadline Set for {current_year}',
        'content': f'European Commission confirms mandatory compliance by {current_year}. '
                  f'Member states must implement changes before end of {current_year}.',
        'source': 'EUR-Lex',
        'url': 'https://eur-lex.europa.eu/test',
        'date': f'{current_year}-01-01'
    }

    result = classifier.classify_signal(signal)
    temporal = result['temporal_metadata']

    assert temporal['urgency'] == 'HIGH', \
        f"Current year {current_year} should yield HIGH urgency, got {temporal['urgency']}"
    assert temporal['time_horizon'] == '12_MONTH', \
        f"Current year {current_year} should yield 12_MONTH, got {temporal['time_horizon']}"


def test_temporal_urgency_past_year_is_not_high():
    """A year that is now in the past (2024) must NOT produce HIGH urgency."""
    classifier = SignalClassifier()

    signal = {
        'title': 'Historical Review of 2024 Farm Subsidy Changes',
        'content': 'Analysis of subsidy reforms introduced in 2024 and their outcomes.',
        'source': 'Eurostat',
        'url': 'https://eurostat.ec.europa.eu/test',
        'date': '2026-01-01'
    }

    result = classifier.classify_signal(signal)
    temporal = result['temporal_metadata']

    assert temporal['urgency'] != 'HIGH', \
        f"Past year 2024 should NOT yield HIGH urgency, got {temporal['urgency']}"


def test_classify_innovation_signal():
    """A Fendt product launch at Agritechnica must classify as INNOVATION, not TECHNOLOGICAL."""
    classifier = SignalClassifier()

    signal = {
        'title': 'Fendt Unveils New Vario 900 Concept Machine at Agritechnica',
        'content': 'Fendt announced the commercial release of its next-generation concept machine '
                  'at Agritechnica. The new model enters the market in 2027 following a successful '
                  'prototype demonstration. Dealer launch events confirmed across Germany and France.',
        'source': 'Agritechnica Press',
        'url': 'https://agritechnica.com/fendt-vario-900',
        'date': '2026-11-15'
    }

    result = classifier.classify_signal(signal)

    assert result['primary_dimension'] == 'INNOVATION', \
        f"Product launch signal should classify as INNOVATION, got {result['primary_dimension']}"


def test_classifier_tie_breaking_prefers_legal():
    """On a PESTEL dimension tie, LEGAL must take priority over TECHNOLOGICAL."""
    classifier = SignalClassifier()

    # Craft a signal with exactly equal LEGAL and TECHNOLOGICAL keyword hits
    # LEGAL keywords: regulation, law, directive, compliance, standard (5)
    # TECHNOLOGICAL keywords: innovation, digital, automation, AI, robotics (5)
    signal = {
        'title': 'AI Regulation Compliance Standard',
        'content': 'New directive mandates law on automation. Digital innovation robotics compliance.',
        'source': 'EUR-Lex',
        'url': 'https://eur-lex.europa.eu/test',
        'date': '2026-01-01'
    }

    # Run twice to confirm determinism
    result1 = classifier.classify_signal(signal)
    result2 = classifier.classify_signal(signal)

    assert result1['primary_dimension'] == result2['primary_dimension'], \
        "Classifier must be deterministic on repeated calls with identical input"
    assert result1['primary_dimension'] == 'LEGAL', \
        f"On tie, LEGAL should win over TECHNOLOGICAL, got {result1['primary_dimension']}"


if __name__ == "__main__":
    print("=" * 70)
    print("Running Signal Classifier Tests")
    print("=" * 70)

    test_classify_legal_signal()
    test_classify_technological_signal()
    test_classify_economic_signal()
    test_entity_extraction()
    test_temporal_metadata_extraction()
    test_temporal_urgency_current_year_is_high()
    test_temporal_urgency_past_year_is_not_high()
    test_classify_innovation_signal()
    test_classifier_tie_breaking_prefers_legal()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✓")
    print("=" * 70)
