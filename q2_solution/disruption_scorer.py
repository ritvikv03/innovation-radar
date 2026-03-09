"""
Disruption Scorer for Q2 - Industry Disruption Detection
=========================================================

Calculates disruption potential using: Novelty × Impact × Velocity

Formula: Disruption Score = (0.35 × Novelty) + (0.40 × Impact) + (0.25 × Velocity)

Classification:
- 0.75-1.00: CRITICAL
- 0.50-0.74: HIGH
- 0.30-0.49: MODERATE
- 0.00-0.29: LOW
"""

import math
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

# Import database module if available
try:
    from database import SignalDatabase
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


class DisruptionScorer:
    """
    Scores signals for disruption potential across European agriculture.
    """

    def __init__(self, historical_signals: List[Dict] = None, db_path: Optional[str] = None):
        """
        Args:
            historical_signals: List of past signals for novelty comparison (fallback if no DB)
            db_path: Path to SQLite database for temporal velocity calculation
        """
        self.historical_signals = historical_signals or []
        self.weight_novelty = 0.35
        self.weight_impact = 0.40
        self.weight_velocity = 0.25

        # Initialize database connection for velocity calculation
        if DATABASE_AVAILABLE:
            self.db = SignalDatabase(db_path)
            self.use_database = True
        else:
            self.db = None
            self.use_database = False

    def score_signal(self, signal: Dict) -> Dict:
        """
        Score a signal for disruption potential.

        Args:
            signal: Classified signal with PESTEL tags and entities

        Returns:
            Dict: Signal with disruption scores added
        """
        # Calculate component scores
        novelty_score = self._calculate_novelty(signal)
        impact_score = self._calculate_impact(signal)
        velocity_score = self._calculate_velocity(signal)

        # Overall disruption score
        disruption_score = (
            self.weight_novelty * novelty_score +
            self.weight_impact * impact_score +
            self.weight_velocity * velocity_score
        )

        # Classification
        if disruption_score >= 0.75:
            classification = "CRITICAL"
        elif disruption_score >= 0.50:
            classification = "HIGH"
        elif disruption_score >= 0.30:
            classification = "MODERATE"
        else:
            classification = "LOW"

        # Time horizon (from temporal metadata or estimate from velocity)
        time_horizon = signal.get('temporal_metadata', {}).get('time_horizon')
        if not time_horizon:
            time_horizon = self._estimate_time_horizon(velocity_score)

        return {
            **signal,
            'novelty_score': round(novelty_score, 3),
            'impact_score': round(impact_score, 3),
            'velocity_score': round(velocity_score, 3),
            'disruption_score': round(disruption_score, 3),
            'classification': classification,
            'time_horizon': time_horizon,
            'scored_at': datetime.now().isoformat()
        }

    def _build_signal_fingerprint(self, signal: Dict) -> str:
        """
        Build a comparable text fingerprint from title + content keywords.

        Combining title with key content terms catches rephrased duplicates
        that differ in title wording but share the same substantive themes.
        """
        title = signal.get('title', '')
        content = signal.get('content', '')
        # Use first 300 chars of content to capture dominant themes without noise
        content_excerpt = content[:300] if content else ''
        return f"{title} {content_excerpt}".lower()

    def _calculate_novelty(self, signal: Dict) -> float:
        """
        Calculate how novel this signal is vs. historical signals.

        Compares a fingerprint of title + content excerpt against history
        so that rephrased duplicates with different titles score low novelty.

        High novelty = emerging disruption
        Low novelty = mainstream trend

        Returns:
            float: Novelty score [0.0-1.0]
        """
        if not self.historical_signals:
            return 0.8  # Default high novelty if no history

        signal_fingerprint = self._build_signal_fingerprint(signal)
        max_similarity = 0.0

        for hist_signal in self.historical_signals:
            hist_fingerprint = self._build_signal_fingerprint(hist_signal)
            similarity = SequenceMatcher(None, signal_fingerprint, hist_fingerprint).ratio()
            max_similarity = max(max_similarity, similarity)

        # Novelty = inverse of similarity
        return 1.0 - max_similarity

    def _calculate_impact(self, signal: Dict) -> float:
        """
        Calculate potential impact on European agricultural industry.

        Impact factors:
        - Cross-PESTEL reach (more dimensions = broader impact)
        - Regulatory forcing function (mandates = high impact)
        - Technology scope (precision ag, electrification, etc.)

        Returns:
            float: Impact score [0.0-1.0]
        """
        impact = 0.0

        # Factor 1: Cross-PESTEL reach (40%)
        primary_dim = signal.get('primary_dimension', '')
        secondary_dims = signal.get('secondary_dimensions', [])
        total_dimensions = 1 + len(secondary_dims)
        cross_pestel_factor = min(total_dimensions / 6.0, 1.0)  # Max 6 PESTEL dimensions
        impact += cross_pestel_factor * 0.40

        # Factor 2: Regulatory forcing function (35%)
        regulations = signal.get('entities', {}).get('regulations', [])
        if regulations or 'mandate' in signal.get('content', '').lower():
            impact += 0.35
        elif 'regulation' in signal.get('content', '').lower():
            impact += 0.20

        # Factor 3: Technology scope (25%)
        technologies = signal.get('entities', {}).get('technologies', [])
        high_impact_techs = ['electric', 'autonomous', 'AI', 'precision farming']
        tech_match = any(tech.lower() in str(technologies).lower() for tech in high_impact_techs)
        if tech_match:
            impact += 0.25
        elif technologies:
            impact += 0.15

        return min(impact, 1.0)

    def _calculate_velocity(self, signal: Dict) -> float:
        """
        Calculate trend velocity using TRUE MATHEMATICAL MOMENTUM.

        NEW APPROACH (Phase 2):
        Instead of keyword-based heuristics ("urgent", "immediate"), we query the
        database to calculate ACTUAL signal frequency:

        - Recent window: Last 30 days
        - Historical window: 30-180 days ago
        - Velocity = (recent_count - historical_avg) / (historical_avg + 1)

        This measures how much faster similar themes/entities are appearing now
        versus historically.

        Fallback to keyword-based if database is unavailable.

        Returns:
            float: Velocity score [0.0-1.0]
        """
        if self.use_database and self.db:
            # Extract entities and themes for temporal analysis
            entities = []
            themes = []

            # Get entities from signal
            signal_entities = signal.get('entities', {})
            if isinstance(signal_entities, dict):
                for entity_list in signal_entities.values():
                    if isinstance(entity_list, list):
                        entities.extend(entity_list)

            # Get themes from primary dimension and content keywords
            if 'primary_dimension' in signal:
                themes.append(signal['primary_dimension'])

            # Extract key themes from title
            title = signal.get('title', '')
            theme_keywords = ['CAP', 'emissions', 'electric', 'autonomous', 'AI',
                            'climate', 'regulation', 'protest', 'subsidy', 'trade']
            themes.extend([kw for kw in theme_keywords if kw.lower() in title.lower()])

            # Get date for reference
            date_str = signal.get('date', datetime.now().date().isoformat())

            # Calculate velocity from database
            if entities or themes:
                velocity, metadata = self.db.calculate_temporal_velocity(
                    entities=entities,
                    themes=themes,
                    reference_date=date_str
                )

                # Store metadata in signal for transparency
                signal['velocity_metadata'] = metadata

                return velocity

        # FALLBACK: Keyword-based velocity (legacy approach)
        velocity = 0.5  # Default moderate velocity
        temporal_data = signal.get('temporal_metadata', {})

        # High velocity indicators
        urgency = temporal_data.get('urgency', 'MEDIUM')
        if urgency == 'HIGH':
            velocity = 0.85
        elif urgency == 'MEDIUM':
            velocity = 0.55
        else:
            velocity = 0.30

        # Boost for imminent years
        mentioned_years = temporal_data.get('mentioned_years', [])
        current_year = str(datetime.now().year)
        next_year = str(datetime.now().year + 1)
        if current_year in mentioned_years or next_year in mentioned_years:
            velocity = min(velocity + 0.15, 1.0)

        return velocity

    def _estimate_time_horizon(self, velocity: float) -> str:
        """
        Estimate time horizon based on velocity.

        Args:
            velocity: Velocity score [0-1]

        Returns:
            str: '12_MONTH', '24_MONTH', or '36_MONTH'
        """
        if velocity >= 0.7:
            return '12_MONTH'
        elif velocity >= 0.4:
            return '24_MONTH'
        else:
            return '36_MONTH'

    def add_historical_signal(self, signal: Dict):
        """Add a signal to historical database for future novelty comparisons."""
        self.historical_signals.append(signal)


if __name__ == "__main__":
    # Example usage
    from signal_classifier import SignalClassifier

    classifier = SignalClassifier()
    scorer = DisruptionScorer()

    test_signal = {
        'title': 'EU Mandates Battery Swapping Infrastructure for Agricultural Machinery by 2027',
        'content': 'In a groundbreaking regulatory shift, the European Union announced '
                  'mandatory battery swapping infrastructure deployment for electric '
                  'agricultural machinery by 2027. This accelerates electrification '
                  'across all farm equipment categories, requiring manufacturers to '
                  'adopt standardized battery formats. The regulation impacts precision '
                  'farming, autonomous tractors, and sustainable agriculture initiatives.',
        'source': 'EUR-Lex',
        'url': 'https://eur-lex.europa.eu/example',
        'date': '2024-03-15'
    }

    # Classify first
    classified = classifier.classify_signal(test_signal)

    # Then score
    scored = scorer.score_signal(classified)

    print("=" * 70)
    print("DISRUPTION SCORER - EXAMPLE OUTPUT")
    print("=" * 70)
    print(f"Title: {scored['title'][:70]}...")
    print(f"\nPESTEL Classification:")
    print(f"  Primary: {scored['primary_dimension']}")
    print(f"  Secondary: {', '.join(scored['secondary_dimensions']) or 'None'}")
    print(f"\nDisruption Scoring:")
    print(f"  Novelty:    {scored['novelty_score']:.3f} (how new/emerging)")
    print(f"  Impact:     {scored['impact_score']:.3f} (industry-wide effect)")
    print(f"  Velocity:   {scored['velocity_score']:.3f} (acceleration rate)")
    print(f"  " + "-" * 50)
    print(f"  DISRUPTION SCORE: {scored['disruption_score']:.3f} ({scored['classification']})")
    print(f"\nTime Horizon: {scored['time_horizon']}")
    print(f"\nStrategic Implication:")
    if scored['classification'] == 'CRITICAL':
        print("  → IMMEDIATE R&D PRIORITY - Board-level decision required")
    elif scored['classification'] == 'HIGH':
        print("  → MONITOR CLOSELY - Prepare strategic response")
    else:
        print("  → TRACK DEVELOPMENTS - Background monitoring")
    print("=" * 70)
