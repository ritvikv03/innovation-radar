"""
AI Agents for Q2 Solution
==========================

Agent-based architecture following best practices:
- ClassifierAgent: PESTEL classification + entity extraction
- EvaluatorAgent: Disruption scoring (Novelty × Impact × Velocity)
- SynthesisAgent: Strategic report generation

Each agent has structured inputs/outputs using Pydantic models.
"""

from typing import List, Dict
from datetime import datetime
import sys
from pathlib import Path

# Import Pydantic models
from models import (
    RawSignal, ClassifiedSignal, ScoredSignal, StrategicReport,
    StrategicInsight, ExtractedEntities, TemporalMetadata
)

# Import existing functionality
from signal_classifier import SignalClassifier
from disruption_scorer import DisruptionScorer
from strategic_report_generator import StrategicReportGenerator


class ClassifierAgent:
    """
    Agent responsible for PESTEL classification and entity extraction.

    Input: RawSignal
    Output: ClassifiedSignal
    """

    def __init__(self):
        self.classifier = SignalClassifier()

    def classify(self, raw_signal: RawSignal) -> ClassifiedSignal:
        """
        Classify a raw signal into PESTEL dimensions.

        Args:
            raw_signal: Pydantic RawSignal model

        Returns:
            ClassifiedSignal with PESTEL tags and entities
        """
        # Convert Pydantic model to dict for existing classifier
        signal_dict = {
            'title': raw_signal.title,
            'content': raw_signal.content,
            'source': raw_signal.source,
            'url': str(raw_signal.url),
            'date': raw_signal.date
        }

        # Use existing classifier
        classified_dict = self.classifier.classify_signal(signal_dict)

        # Convert back to Pydantic model
        classified_signal = ClassifiedSignal(
            title=classified_dict['title'],
            content=classified_dict['content'],
            source=classified_dict['source'],
            url=classified_dict['url'],
            date=classified_dict['date'],
            primary_dimension=classified_dict['primary_dimension'],
            secondary_dimensions=classified_dict['secondary_dimensions'],
            dimension_scores=classified_dict['dimension_scores'],
            entities=ExtractedEntities(**classified_dict['entities']),
            temporal_metadata=TemporalMetadata(**classified_dict['temporal_metadata']),
            classified_at=datetime.now()
        )

        return classified_signal


class EvaluatorAgent:
    """
    Agent responsible for disruption scoring.

    Input: ClassifiedSignal
    Output: ScoredSignal

    Scoring Formula: (0.35 × Novelty) + (0.40 × Impact) + (0.25 × Velocity)
    """

    def __init__(self, historical_signals: List[Dict] = None):
        self.scorer = DisruptionScorer(historical_signals=historical_signals)

    def evaluate(self, classified_signal: ClassifiedSignal) -> ScoredSignal:
        """
        Evaluate disruption potential of a classified signal.

        Args:
            classified_signal: Pydantic ClassifiedSignal model

        Returns:
            ScoredSignal with disruption scores
        """
        # Convert to dict for existing scorer
        signal_dict = {
            'title': classified_signal.title,
            'content': classified_signal.content,
            'source': classified_signal.source,
            'url': str(classified_signal.url),
            'date': classified_signal.date,
            'primary_dimension': classified_signal.primary_dimension,
            'secondary_dimensions': classified_signal.secondary_dimensions,
            'dimension_scores': classified_signal.dimension_scores,
            'entities': classified_signal.entities.model_dump(),
            'temporal_metadata': classified_signal.temporal_metadata.model_dump()
        }

        # Use existing scorer
        scored_dict = self.scorer.score_signal(signal_dict)

        # Convert back to Pydantic model
        scored_signal = ScoredSignal(
            title=scored_dict['title'],
            content=scored_dict['content'],
            source=scored_dict['source'],
            url=scored_dict['url'],
            date=scored_dict['date'],
            primary_dimension=scored_dict['primary_dimension'],
            secondary_dimensions=scored_dict['secondary_dimensions'],
            dimension_scores=scored_dict['dimension_scores'],
            entities=ExtractedEntities(**scored_dict['entities']),
            temporal_metadata=TemporalMetadata(**scored_dict['temporal_metadata']),
            classified_at=classified_signal.classified_at,
            novelty_score=scored_dict['novelty_score'],
            impact_score=scored_dict['impact_score'],
            velocity_score=scored_dict['velocity_score'],
            disruption_score=scored_dict['disruption_score'],
            classification=scored_dict['classification'],
            scored_at=datetime.now()
        )

        return scored_signal


class SynthesisAgent:
    """
    Agent responsible for strategic report synthesis.

    Input: List[ScoredSignal]
    Output: StrategicReport

    Generates board-ready strategic insights and R&D recommendations.
    """

    def __init__(self, company_priorities: Dict[str, float] = None):
        self.report_generator = StrategicReportGenerator()
        self.company_priorities = company_priorities or {
            'electrification': 0.90,
            'autonomous_farming': 0.75,
            'precision_agriculture': 0.70,
            'carbon_neutrality': 0.85,
            'digital_platforms': 0.65
        }

    def synthesize(self, scored_signals: List[ScoredSignal]) -> StrategicReport:
        """
        Synthesize strategic insights from scored signals.

        Args:
            scored_signals: List of Pydantic ScoredSignal models

        Returns:
            StrategicReport with insights and recommendations
        """
        # Convert to dict for existing generator
        signals_dict = [s.model_dump() for s in scored_signals]

        # Count by classification
        critical_count = sum(1 for s in scored_signals if s.classification == 'CRITICAL')
        high_count = sum(1 for s in scored_signals if s.classification == 'HIGH')
        moderate_count = sum(1 for s in scored_signals if s.classification == 'MODERATE')

        # Generate insights
        insights = []
        for signal in sorted(scored_signals, key=lambda x: x.disruption_score, reverse=True)[:10]:
            # Calculate alignment score
            alignment_score = self._calculate_alignment(signal)

            # Generate recommendation
            if alignment_score >= 0.75 and signal.disruption_score >= 0.70:
                recommendation = "ACCELERATE: Immediate R&D investment priority"
            elif alignment_score >= 0.75:
                recommendation = "BUILD: High strategic fit - develop capabilities"
            elif signal.disruption_score >= 0.70:
                recommendation = "PARTNER: High disruption - consider M&A or partnerships"
            else:
                recommendation = "MONITOR: Track developments, prepare response"

            insight = StrategicInsight(
                signal_title=signal.title,
                dimension=signal.primary_dimension,
                disruption_score=signal.disruption_score,
                recommendation=recommendation,
                rationale=self._generate_rationale(signal, alignment_score),
                time_horizon=signal.temporal_metadata.time_horizon,
                alignment_score=alignment_score
            )
            insights.append(insight)

        # Top recommendation
        if insights:
            top_recommendation = f"{insights[0].signal_title}: {insights[0].recommendation}"
        else:
            top_recommendation = "No high-priority disruptions identified"

        # Executive summary
        executive_summary = self._generate_executive_summary(
            scored_signals, critical_count, high_count
        )

        report = StrategicReport(
            generated_at=datetime.now(),
            total_signals=len(scored_signals),
            critical_count=critical_count,
            high_count=high_count,
            moderate_count=moderate_count,
            insights=insights,
            top_recommendation=top_recommendation,
            executive_summary=executive_summary
        )

        return report

    def _calculate_alignment(self, signal: ScoredSignal) -> float:
        """Calculate strategic alignment with Company A priorities."""
        title = signal.title.lower()
        content = signal.content.lower()
        combined = f"{title} {content}"

        max_alignment = 0.0
        for priority, weight in self.company_priorities.items():
            if priority.replace('_', ' ') in combined:
                alignment = weight
                max_alignment = max(max_alignment, alignment)

        # Boost for high disruption score
        final_alignment = max_alignment * 0.7 + signal.disruption_score * 0.3
        return min(final_alignment, 1.0)

    def _generate_rationale(self, signal: ScoredSignal, alignment: float) -> str:
        """Generate brief rationale for recommendation."""
        if alignment >= 0.75 and signal.disruption_score >= 0.70:
            return "High strategic fit with proven disruption potential. Immediate investment recommended."
        elif alignment >= 0.75:
            return "Strong alignment with Company A priorities. Build internal capabilities."
        elif signal.disruption_score >= 0.70:
            return "Significant industry disruption potential. Consider external partnerships or M&A."
        else:
            return "Moderate strategic relevance. Continue monitoring for signal strengthening."

    def _generate_executive_summary(
        self,
        signals: List[ScoredSignal],
        critical_count: int,
        high_count: int
    ) -> str:
        """Generate executive summary."""
        horizon_12 = sum(1 for s in signals if s.temporal_metadata.time_horizon == '12_MONTH')
        horizon_24 = sum(1 for s in signals if s.temporal_metadata.time_horizon == '24_MONTH')
        horizon_36 = sum(1 for s in signals if s.temporal_metadata.time_horizon == '36_MONTH')

        summary = (
            f"Analysis of {len(signals)} European agricultural disruption signals identified "
            f"{critical_count} CRITICAL and {high_count} HIGH priority disruptions. "
            f"Time horizon distribution: {horizon_12} immediate (12-month), "
            f"{horizon_24} emerging (24-month), {horizon_36} early-stage (36-month). "
            f"Primary strategic focus areas: electrification, autonomous farming, precision agriculture."
        )

        return summary


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("AGENT SYSTEM - EXAMPLE EXECUTION")
    print("=" * 70)

    # Step 1: Create raw signal
    raw_signal = RawSignal(
        title="EU Battery Swapping Mandate for Agricultural Machinery by 2027",
        content="The European Union announced a groundbreaking regulatory mandate "
                "requiring all new agricultural machinery manufacturers to adopt "
                "standardized battery swapping infrastructure by 2027. This regulation "
                "accelerates the electrification transition across tractors, harvesters, "
                "and precision farming equipment.",
        source="EUR-Lex",
        url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R0567",
        date="2024-03-15"
    )

    print(f"\n1. Raw Signal:")
    print(f"   Title: {raw_signal.title[:60]}...")
    print(f"   Source: {raw_signal.source}")

    # Step 2: Classify
    classifier_agent = ClassifierAgent()
    classified = classifier_agent.classify(raw_signal)

    print(f"\n2. After Classification:")
    print(f"   Primary Dimension: {classified.primary_dimension}")
    print(f"   Secondary Dimensions: {', '.join(classified.secondary_dimensions) or 'None'}")
    print(f"   Technologies: {', '.join(classified.entities.technologies[:3])}")

    # Step 3: Evaluate
    evaluator_agent = EvaluatorAgent()
    scored = evaluator_agent.evaluate(classified)

    print(f"\n3. After Evaluation:")
    print(f"   Novelty Score:    {scored.novelty_score:.3f}")
    print(f"   Impact Score:     {scored.impact_score:.3f}")
    print(f"   Velocity Score:   {scored.velocity_score:.3f}")
    print(f"   Disruption Score: {scored.disruption_score:.3f} ({scored.classification})")
    print(f"   Time Horizon:     {scored.temporal_metadata.time_horizon}")

    # Step 4: Synthesize
    synthesis_agent = SynthesisAgent()
    report = synthesis_agent.synthesize([scored])

    print(f"\n4. Strategic Report:")
    print(f"   Total Signals: {report.total_signals}")
    print(f"   Top Recommendation: {report.top_recommendation[:80]}...")
    print(f"   Executive Summary: {report.executive_summary[:120]}...")

    if report.insights:
        print(f"\n   Top Insight:")
        insight = report.insights[0]
        print(f"   - Signal: {insight.signal_title[:50]}...")
        print(f"   - Alignment Score: {insight.alignment_score:.2f}")
        print(f"   - Recommendation: {insight.recommendation}")

    print("\n" + "=" * 70)
    print("AGENT PIPELINE EXECUTED SUCCESSFULLY")
    print("=" * 70)
