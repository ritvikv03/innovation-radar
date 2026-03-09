"""
Signal Classifier for Q2 - Industry Disruption Detection
=========================================================

Classifies raw signals into PESTEL-EL dimensions using keyword matching.

Input: Raw signal data (title, content, source)
Output: Classified signal with PESTEL-EL tags, entities, temporal metadata

Dimensions (8 pillars per CLAUDE.md):
  POLITICAL, ECONOMIC, SOCIAL, TECHNOLOGICAL, ENVIRONMENTAL, LEGAL,
  INNOVATION, SOCIAL_MEDIA

Tie-breaking priority (highest C-suite urgency first):
  LEGAL > ENVIRONMENTAL > TECHNOLOGICAL > ECONOMIC > POLITICAL > SOCIAL
  > INNOVATION > SOCIAL_MEDIA
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple
from collections import Counter


# PESTEL-EL Dimension Keyword Dictionaries (8 pillars)
PESTEL_KEYWORDS = {
    'POLITICAL': [
        'policy', 'election', 'government', 'trade', 'tariff', 'subsidy',
        'CAP', 'common agricultural policy', 'EU council', 'parliament',
        'vote', 'legislation', 'reform', 'political'
    ],
    'ECONOMIC': [
        'price', 'cost', 'market', 'GDP', 'inflation', 'interest rate',
        'commodity', 'income', 'profit', 'investment', 'financing',
        'revenue', 'expense', 'budget', 'economic', 'financial'
    ],
    'SOCIAL': [
        'farmer', 'labor', 'protest', 'sentiment', 'demographics',
        'rural', 'community', 'migration', 'workforce', 'skill',
        'education', 'health', 'safety', 'social', 'cultural'
    ],
    'TECHNOLOGICAL': [
        'digital', 'automation', 'AI', 'robotics',
        'sensor', 'IoT', 'software', 'R&D', 'research',
        'technology', 'algorithm', 'data', 'connectivity', 'precision',
        'autonomous', 'electric', 'hydrogen', 'telematics'
    ],
    'ENVIRONMENTAL': [
        'climate', 'emission', 'carbon', 'sustainability', 'weather',
        'drought', 'biodiversity', 'soil', 'water', 'pollution',
        'renewable', 'green', 'environmental', 'ecological', 'conservation'
    ],
    'LEGAL': [
        'regulation', 'law', 'directive', 'compliance', 'standard',
        'certification', 'ban', 'mandate', 'enforcement', 'penalty',
        'legal', 'court', 'ruling', 'obligation', 'requirement'
    ],
    'INNOVATION': [
        'product launch', 'new model', 'market entry', 'commercial release',
        'concept machine', 'prototype', 'startup', 'funding round',
        'acquisition', 'joint venture', 'spin-off', 'technology transfer',
        'Agritechnica', 'SIMA', 'Farm Progress Show', 'dealer launch',
        'production ready', 'series production', 'unveil', 'debut'
    ],
    'SOCIAL_MEDIA': [
        'viral', 'influencer', 'hashtag', 'trending', 'social media',
        'tiktok', 'youtube', 'instagram', 'online discussion', 'buzz',
        'sentiment online', 'digital community', 'forum', 'reddit', 'twitter'
    ]
}

# Tie-breaking priority: index 0 = highest priority
TIE_BREAK_PRIORITY = [
    'LEGAL', 'ENVIRONMENTAL', 'TECHNOLOGICAL', 'ECONOMIC',
    'POLITICAL', 'SOCIAL', 'INNOVATION', 'SOCIAL_MEDIA'
]


class SignalClassifier:
    """
    Classifies signals into PESTEL dimensions using keyword-based scoring.
    """

    def __init__(self):
        self.pestel_keywords = PESTEL_KEYWORDS

    def classify_signal(self, signal: Dict) -> Dict:
        """
        Classify a signal into PESTEL dimensions.

        Args:
            signal: Dictionary with 'title', 'content', 'source', 'url', 'date'

        Returns:
            Dict: Enhanced signal with PESTEL tags and metadata
        """
        title = signal.get('title', '')
        content = signal.get('content', '')
        combined_text = f"{title} {content}".lower()

        # Score each PESTEL dimension
        dimension_scores = {}
        for dimension, keywords in self.pestel_keywords.items():
            score = sum(1 for keyword in keywords if keyword.lower() in combined_text)
            dimension_scores[dimension] = score

        # Primary dimension: highest score; ties broken by TIE_BREAK_PRIORITY
        max_score = max(dimension_scores.values())
        top_dims = [d for d, s in dimension_scores.items() if s == max_score]
        primary_dimension = min(top_dims, key=lambda d: TIE_BREAK_PRIORITY.index(d))

        # Secondary dimensions (score >= 2)
        secondary_dimensions = [
            dim for dim, score in dimension_scores.items()
            if score >= 2 and dim != primary_dimension
        ]

        # Extract entities
        entities = self._extract_entities(combined_text)

        # Extract temporal metadata
        temporal_data = self._extract_temporal_metadata(combined_text)

        return {
            **signal,  # Preserve original fields
            'primary_dimension': primary_dimension,
            'secondary_dimensions': secondary_dimensions,
            'dimension_scores': dimension_scores,
            'entities': entities,
            'temporal_metadata': temporal_data,
            'classified_at': datetime.now().isoformat()
        }

    def _extract_entities(self, text: str) -> Dict:
        """
        Extract key entities from text.

        Returns:
            Dict with keys: regulations, companies, locations, technologies
        """
        entities = {
            'regulations': [],
            'companies': [],
            'locations': [],
            'technologies': []
        }

        # Regulation patterns (e.g., "Stage V", "EU 2024/123", "EUR-Lex")
        regulation_patterns = [
            r'Stage [IV]+',
            r'EU \d{4}/\d+',
            r'Regulation \(EU\) \d{4}/\d+',
            r'Directive \d{4}/\d+/EU',
            r'CAP \d{4}',
            r'Green Deal',
            r'Farm to Fork'
        ]
        for pattern in regulation_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities['regulations'].extend(matches)

        # European location patterns
        location_patterns = [
            r'\b(Germany|France|Italy|Spain|Poland|Netherlands|Belgium|Denmark)\b',
            r'\b(European Union|EU|Europe)\b'
        ]
        for pattern in location_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            entities['locations'].extend(matches)

        # Technology keywords (simple extraction)
        tech_keywords = ['electric', 'autonomous', 'precision farming', 'IoT',
                        'AI', 'robot', 'drone', 'sensor', 'GPS', 'satellite']
        for keyword in tech_keywords:
            if keyword.lower() in text:
                entities['technologies'].append(keyword)

        # Remove duplicates
        for key in entities:
            entities[key] = list(set(entities[key]))

        return entities

    def _extract_temporal_metadata(self, text: str) -> Dict:
        """
        Extract temporal information (dates, horizons).

        Returns:
            Dict with keys: mentioned_years, time_horizon, urgency
        """
        temporal = {
            'mentioned_years': [],
            'time_horizon': None,
            'urgency': 'MEDIUM'
        }

        # Extract years (2024–2035)
        year_matches = re.findall(r'\b(202[4-9]|203[0-5])\b', text)
        temporal['mentioned_years'] = sorted(list(set(year_matches)))

        # Dynamic urgency: HIGH = current or next year, MEDIUM = +2/+3 years, LOW = further
        current_year = datetime.now().year
        high_years = {str(current_year), str(current_year + 1)}
        medium_years = {str(current_year + 2), str(current_year + 3)}

        mentioned_set = set(temporal['mentioned_years'])
        if mentioned_set & high_years or any(kw in text for kw in ['immediate', 'urgent', 'now']):
            temporal['time_horizon'] = '12_MONTH'
            temporal['urgency'] = 'HIGH'
        elif mentioned_set & medium_years or any(kw in text for kw in ['upcoming', 'near future']):
            temporal['time_horizon'] = '24_MONTH'
            temporal['urgency'] = 'MEDIUM'
        else:
            temporal['time_horizon'] = '36_MONTH'
            temporal['urgency'] = 'LOW'

        return temporal


if __name__ == "__main__":
    # Example usage
    classifier = SignalClassifier()

    test_signal = {
        'title': 'EU Stage V Emission Standards Impact Electric Tractor Adoption',
        'content': 'The new EU Stage V emission regulations mandate stricter diesel '
                  'emission controls by 2025, accelerating the shift toward electric and '
                  'hybrid agricultural machinery. Major manufacturers are investing in '
                  'battery technology and autonomous precision farming systems.',
        'source': 'EUR-Lex',
        'url': 'https://eur-lex.europa.eu/example',
        'date': '2024-03-15'
    }

    result = classifier.classify_signal(test_signal)

    print("=" * 70)
    print("SIGNAL CLASSIFIER - EXAMPLE OUTPUT")
    print("=" * 70)
    print(f"Title: {result['title']}")
    print(f"Primary Dimension: {result['primary_dimension']}")
    print(f"Secondary Dimensions: {', '.join(result['secondary_dimensions'])}")
    print(f"\nDimension Scores:")
    for dim, score in sorted(result['dimension_scores'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {dim}: {score}")
    print(f"\nExtracted Entities:")
    for entity_type, values in result['entities'].items():
        if values:
            print(f"  {entity_type.capitalize()}: {', '.join(values)}")
    print(f"\nTemporal Metadata:")
    print(f"  Years mentioned: {', '.join(result['temporal_metadata']['mentioned_years'])}")
    print(f"  Time Horizon: {result['temporal_metadata']['time_horizon']}")
    print(f"  Urgency: {result['temporal_metadata']['urgency']}")
    print("=" * 70)
