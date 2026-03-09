"""
Integration test for full Q2 pipeline
"""

import sys
import json
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'q2_solution'))

from q2_pipeline import Q2Pipeline, get_sample_signals


def test_full_pipeline_execution():
    """Test complete pipeline execution with sample data."""
    # Use temporary output directory
    output_dir = Path(__file__).parent / 'test_outputs'
    output_dir.mkdir(exist_ok=True)

    # Get sample signals
    signals = get_sample_signals()[:3]  # Use 3 signals for faster testing

    # Execute pipeline
    pipeline = Q2Pipeline(output_dir=str(output_dir))
    summary = pipeline.run(signals)

    # Verify outputs exist
    assert (output_dir / 'data' / 'scored_signals.json').exists(), \
        "scored_signals.json not created"
    assert (output_dir / 'charts' / 'innovation_radar.html').exists(), \
        "innovation_radar.html not created"
    assert (output_dir / 'charts' / 'pestel_heatmap.html').exists(), \
        "pestel_heatmap.html not created"
    assert (output_dir / 'reports' / 'disruption_map.md').exists(), \
        "disruption_map.md not created"
    assert (output_dir / 'reports' / 'weak_signal_digest.md').exists(), \
        "weak_signal_digest.md not created"
    assert (output_dir / 'reports' / 'rd_alignment_brief.md').exists(), \
        "rd_alignment_brief.md not created"

    # Verify summary structure
    assert 'signals_processed' in summary
    assert summary['signals_processed'] == 3
    assert 'outputs' in summary

    # Verify scored signals format
    with open(output_dir / 'data' / 'scored_signals.json', 'r') as f:
        scored = json.load(f)

    assert len(scored) == 3
    for signal in scored:
        assert 'disruption_score' in signal
        assert 'classification' in signal
        assert 'primary_dimension' in signal
        assert 'time_horizon' in signal

    print("✓ test_full_pipeline_execution passed")
    print(f"  Processed {summary['signals_processed']} signals")
    print(f"  CRITICAL disruptions: {summary['critical_disruptions']}")
    print(f"  HIGH disruptions: {summary['high_disruptions']}")

    # Cleanup (optional - comment out to inspect outputs)
    # import shutil
    # shutil.rmtree(output_dir)


def test_sample_signals_validity():
    """Test that sample signals have required structure."""
    signals = get_sample_signals()

    assert len(signals) > 0, "No sample signals generated"

    for signal in signals:
        assert 'title' in signal, f"Signal missing title: {signal}"
        assert 'content' in signal, f"Signal missing content: {signal}"
        assert 'source' in signal, f"Signal missing source: {signal}"
        assert 'url' in signal, f"Signal missing url: {signal}"
        assert 'date' in signal, f"Signal missing date: {signal}"

    print(f"✓ test_sample_signals_validity passed ({len(signals)} signals)")


if __name__ == "__main__":
    print("=" * 70)
    print("Running Q2 Pipeline Integration Tests")
    print("=" * 70)

    test_sample_signals_validity()
    test_full_pipeline_execution()

    print("\n" + "=" * 70)
    print("ALL INTEGRATION TESTS PASSED ✓")
    print("=" * 70)
