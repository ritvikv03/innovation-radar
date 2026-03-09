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


if __name__ == "__main__":
    print("=" * 70)
    print("Running Signal Classifier Tests")
    print("=" * 70)

    test_classify_legal_signal()
    test_classify_technological_signal()
    test_classify_economic_signal()
    test_entity_extraction()
    test_temporal_metadata_extraction()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED ✓")
    print("=" * 70)
