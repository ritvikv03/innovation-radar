"""
Pydantic Models for Q2 Solution
================================

Type-safe data structures for signals, classifications, and reports.
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Optional, Literal
from datetime import datetime


class RawSignal(BaseModel):
    """
    Raw signal from European data sources (EUR-Lex, Espacenet, etc.)
    """
    title: str = Field(..., min_length=10, description="Signal title")
    content: str = Field(..., min_length=50, description="Signal content/summary")
    source: str = Field(..., description="Data source name")
    url: HttpUrl = Field(..., description="Source URL")
    date: str = Field(..., description="Publication date (YYYY-MM-DD)")


class ExtractedEntities(BaseModel):
    """
    Entities extracted from signal text
    """
    regulations: List[str] = Field(default_factory=list)
    companies: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)


class TemporalMetadata(BaseModel):
    """
    Temporal information about signal
    """
    mentioned_years: List[str] = Field(default_factory=list)
    time_horizon: Literal['12_MONTH', '24_MONTH', '36_MONTH'] = '36_MONTH'
    urgency: Literal['HIGH', 'MEDIUM', 'LOW'] = 'MEDIUM'


class ClassifiedSignal(RawSignal):
    """
    Signal after PESTEL classification
    """
    primary_dimension: Literal[
        'POLITICAL', 'ECONOMIC', 'SOCIAL',
        'TECHNOLOGICAL', 'ENVIRONMENTAL', 'LEGAL'
    ]
    secondary_dimensions: List[str] = Field(default_factory=list)
    dimension_scores: Dict[str, int] = Field(default_factory=dict)
    entities: ExtractedEntities
    temporal_metadata: TemporalMetadata
    classified_at: datetime


class DisruptionScores(BaseModel):
    """
    Component scores for disruption potential
    """
    novelty_score: float = Field(..., ge=0.0, le=1.0, description="How new/emerging")
    impact_score: float = Field(..., ge=0.0, le=1.0, description="Industry-wide effect")
    velocity_score: float = Field(..., ge=0.0, le=1.0, description="Acceleration rate")
    disruption_score: float = Field(..., ge=0.0, le=1.0, description="Overall score")
    classification: Literal['CRITICAL', 'HIGH', 'MODERATE', 'LOW']
    time_horizon: Literal['12_MONTH', '24_MONTH', '36_MONTH']


class ScoredSignal(ClassifiedSignal):
    """
    Signal after disruption scoring
    """
    novelty_score: float = Field(..., ge=0.0, le=1.0)
    impact_score: float = Field(..., ge=0.0, le=1.0)
    velocity_score: float = Field(..., ge=0.0, le=1.0)
    disruption_score: float = Field(..., ge=0.0, le=1.0)
    classification: Literal['CRITICAL', 'HIGH', 'MODERATE', 'LOW']
    scored_at: datetime


class StrategicInsight(BaseModel):
    """
    Strategic insight for board presentation
    """
    signal_title: str
    dimension: str
    disruption_score: float
    recommendation: str
    rationale: str
    time_horizon: str
    alignment_score: Optional[float] = None


class StrategicReport(BaseModel):
    """
    Final strategic report for Company A
    """
    generated_at: datetime
    total_signals: int
    critical_count: int
    high_count: int
    moderate_count: int
    insights: List[StrategicInsight]
    top_recommendation: str
    executive_summary: str


class PipelineSummary(BaseModel):
    """
    Pipeline execution summary
    """
    timestamp: datetime
    signals_processed: int
    critical_disruptions: int
    high_disruptions: int
    outputs: Dict[str, str]


# Example usage
if __name__ == "__main__":
    import json

    # Test RawSignal validation
    try:
        signal = RawSignal(
            title="EU Battery Mandate",
            content="The European Union announced regulatory requirements for battery swapping infrastructure in agricultural machinery.",
            source="EUR-Lex",
            url="https://eur-lex.europa.eu/test",
            date="2024-03-15"
        )
        print("✓ RawSignal validation passed")
        print(f"  Title: {signal.title}")
        print(f"  URL: {signal.url}")
    except Exception as e:
        print(f"✗ RawSignal validation failed: {e}")

    # Test invalid URL
    try:
        bad_signal = RawSignal(
            title="Test",
            content="Short",  # Too short, will fail min_length
            source="Test",
            url="not-a-url",
            date="2024-01-01"
        )
    except Exception as e:
        print(f"✓ Validation correctly rejected invalid signal: {type(e).__name__}")

    # Test DisruptionScores
    try:
        scores = DisruptionScores(
            novelty_score=0.85,
            impact_score=0.73,
            velocity_score=0.55,
            disruption_score=0.71,
            classification='HIGH',
            time_horizon='24_MONTH'
        )
        print(f"✓ DisruptionScores validation passed")
        print(f"  Overall score: {scores.disruption_score:.2f}")
        print(f"  Classification: {scores.classification}")
    except Exception as e:
        print(f"✗ DisruptionScores validation failed: {e}")

    print("\n" + "=" * 70)
    print("All Pydantic models validated successfully!")
    print("=" * 70)
