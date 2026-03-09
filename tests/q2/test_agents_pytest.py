"""
Pytest-compatible tests for Agent system
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'q2_solution'))

from models import RawSignal
from agents import ClassifierAgent, EvaluatorAgent, SynthesisAgent


@pytest.fixture
def sample_raw_signal():
    """Fixture providing a sample raw signal."""
    return RawSignal(
        title="EU Stage V Emission Standards Impact Electric Tractor Adoption",
        content="New EU Stage V emission regulations mandate stricter diesel emission controls by 2025, "
                "accelerating the shift toward electric and hybrid agricultural machinery. "
                "Major manufacturers are investing in battery technology and autonomous systems.",
        source="EUR-Lex",
        url="https://eur-lex.europa.eu/test",
        date="2024-03-15"
    )


@pytest.fixture
def classifier_agent():
    """Fixture providing ClassifierAgent instance."""
    return ClassifierAgent()


@pytest.fixture
def evaluator_agent():
    """Fixture providing EvaluatorAgent instance."""
    return EvaluatorAgent()


@pytest.fixture
def synthesis_agent():
    """Fixture providing SynthesisAgent instance."""
    return SynthesisAgent()


class TestClassifierAgent:
    """Test suite for ClassifierAgent."""

    def test_classify_returns_classified_signal(self, classifier_agent, sample_raw_signal):
        """Test that classification returns ClassifiedSignal model."""
        result = classifier_agent.classify(sample_raw_signal)

        assert result.title == sample_raw_signal.title
        assert result.primary_dimension in [
            'POLITICAL', 'ECONOMIC', 'SOCIAL',
            'TECHNOLOGICAL', 'ENVIRONMENTAL', 'LEGAL'
        ]
        assert hasattr(result, 'classified_at')

    def test_classify_extracts_entities(self, classifier_agent, sample_raw_signal):
        """Test that entity extraction works."""
        result = classifier_agent.classify(sample_raw_signal)

        assert hasattr(result, 'entities')
        assert hasattr(result.entities, 'regulations')
        assert hasattr(result.entities, 'technologies')
        assert isinstance(result.entities.regulations, list)

    def test_classify_assigns_temporal_metadata(self, classifier_agent, sample_raw_signal):
        """Test that temporal metadata is assigned."""
        result = classifier_agent.classify(sample_raw_signal)

        assert hasattr(result, 'temporal_metadata')
        assert result.temporal_metadata.time_horizon in ['12_MONTH', '24_MONTH', '36_MONTH']
        assert result.temporal_metadata.urgency in ['HIGH', 'MEDIUM', 'LOW']


class TestEvaluatorAgent:
    """Test suite for EvaluatorAgent."""

    def test_evaluate_returns_scored_signal(self, evaluator_agent, classifier_agent, sample_raw_signal):
        """Test that evaluation returns ScoredSignal model."""
        classified = classifier_agent.classify(sample_raw_signal)
        result = evaluator_agent.evaluate(classified)

        assert hasattr(result, 'disruption_score')
        assert hasattr(result, 'classification')
        assert hasattr(result, 'scored_at')

    def test_evaluate_score_in_valid_range(self, evaluator_agent, classifier_agent, sample_raw_signal):
        """Test that all scores are in [0, 1] range."""
        classified = classifier_agent.classify(sample_raw_signal)
        result = evaluator_agent.evaluate(classified)

        assert 0.0 <= result.novelty_score <= 1.0
        assert 0.0 <= result.impact_score <= 1.0
        assert 0.0 <= result.velocity_score <= 1.0
        assert 0.0 <= result.disruption_score <= 1.0

    def test_evaluate_classification_matches_score(self, evaluator_agent, classifier_agent, sample_raw_signal):
        """Test that classification matches disruption score thresholds."""
        classified = classifier_agent.classify(sample_raw_signal)
        result = evaluator_agent.evaluate(classified)

        if result.disruption_score >= 0.75:
            assert result.classification == 'CRITICAL'
        elif result.disruption_score >= 0.50:
            assert result.classification == 'HIGH'
        elif result.disruption_score >= 0.30:
            assert result.classification == 'MODERATE'
        else:
            assert result.classification == 'LOW'


class TestSynthesisAgent:
    """Test suite for SynthesisAgent."""

    def test_synthesize_returns_strategic_report(
        self,
        synthesis_agent,
        classifier_agent,
        evaluator_agent,
        sample_raw_signal
    ):
        """Test that synthesis returns StrategicReport model."""
        classified = classifier_agent.classify(sample_raw_signal)
        scored = evaluator_agent.evaluate(classified)

        report = synthesis_agent.synthesize([scored])

        assert hasattr(report, 'generated_at')
        assert hasattr(report, 'insights')
        assert hasattr(report, 'executive_summary')
        assert hasattr(report, 'top_recommendation')

    def test_synthesize_counts_classifications_correctly(
        self,
        synthesis_agent,
        classifier_agent,
        evaluator_agent,
        sample_raw_signal
    ):
        """Test that classification counts are accurate."""
        classified = classifier_agent.classify(sample_raw_signal)
        scored = evaluator_agent.evaluate(classified)

        report = synthesis_agent.synthesize([scored, scored])  # 2 copies

        total = report.critical_count + report.high_count + report.moderate_count
        assert total <= 2  # Should not exceed number of signals

    def test_synthesize_generates_insights(
        self,
        synthesis_agent,
        classifier_agent,
        evaluator_agent,
        sample_raw_signal
    ):
        """Test that insights are generated."""
        classified = classifier_agent.classify(sample_raw_signal)
        scored = evaluator_agent.evaluate(classified)

        report = synthesis_agent.synthesize([scored])

        assert len(report.insights) > 0
        insight = report.insights[0]
        assert hasattr(insight, 'signal_title')
        assert hasattr(insight, 'recommendation')
        assert hasattr(insight, 'rationale')


class TestAgentPipeline:
    """Integration tests for full agent pipeline."""

    def test_full_pipeline_execution(
        self,
        classifier_agent,
        evaluator_agent,
        synthesis_agent,
        sample_raw_signal
    ):
        """Test complete pipeline from raw signal to strategic report."""
        # Step 1: Classify
        classified = classifier_agent.classify(sample_raw_signal)
        assert classified.primary_dimension is not None

        # Step 2: Evaluate
        scored = evaluator_agent.evaluate(classified)
        assert scored.disruption_score is not None

        # Step 3: Synthesize
        report = synthesis_agent.synthesize([scored])
        assert report.total_signals == 1
        assert len(report.insights) > 0

    def test_pipeline_preserves_signal_data(
        self,
        classifier_agent,
        evaluator_agent,
        sample_raw_signal
    ):
        """Test that signal data is preserved through pipeline."""
        classified = classifier_agent.classify(sample_raw_signal)
        scored = evaluator_agent.evaluate(classified)

        # Original data preserved
        assert scored.title == sample_raw_signal.title
        assert scored.content == sample_raw_signal.content
        assert str(scored.url) == str(sample_raw_signal.url)

        # New data added
        assert scored.disruption_score is not None
        assert scored.primary_dimension is not None


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v"])
