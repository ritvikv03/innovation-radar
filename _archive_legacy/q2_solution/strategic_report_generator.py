"""
Strategic Report Generator for Q2
==================================

Generates board-ready strategic outputs:
1. Disruption Map (Markdown report)
2. Weak Signal Digest (12-36 month horizon)
3. R&D Alignment Brief (scored recommendations)
4. Innovation Gap Analysis
"""

from typing import List, Dict
from datetime import datetime
import json


class StrategicReportGenerator:
    """
    Generates strategic analysis reports from scored disruption signals.
    """

    def __init__(self):
        pass

    def generate_disruption_map(self, signals: List[Dict], output_path: str) -> str:
        """
        Generate Disruption Map markdown report.

        Args:
            signals: List of scored signals
            output_path: Path to save markdown file

        Returns:
            str: Generated markdown content
        """
        # Sort by disruption score
        sorted_signals = sorted(signals, key=lambda x: x.get('disruption_score', 0), reverse=True)

        # Group by classification
        critical = [s for s in sorted_signals if s.get('classification') == 'CRITICAL']
        high = [s for s in sorted_signals if s.get('classification') == 'HIGH']
        moderate = [s for s in sorted_signals if s.get('classification') == 'MODERATE']

        report = f"""# European Agriculture Industry Disruption Map

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Total Signals Analyzed:** {len(signals)}

---

## Executive Summary

This disruption map identifies {len(critical)} **CRITICAL** and {len(high)} **HIGH** priority disruptions
reshaping the European agricultural machinery sector over the next 12-36 months.

### Key Findings

- **Immediate Threats (12-month horizon):** {len([s for s in sorted_signals if s.get('time_horizon') == '12_MONTH'])} signals
- **Emerging Trends (24-month horizon):** {len([s for s in sorted_signals if s.get('time_horizon') == '24_MONTH'])} signals
- **Early-Stage Innovations (36-month horizon):** {len([s for s in sorted_signals if s.get('time_horizon') == '36_MONTH'])} signals

---

## CRITICAL Disruptions (Disruption Score ≥ 0.75)

*Immediate board-level attention required. These signals represent structural industry shifts
that will fundamentally alter competitive dynamics.*

"""

        for idx, signal in enumerate(critical, 1):
            report += self._format_signal_detail(signal, idx)

        report += f"""
---

## HIGH Priority Disruptions (Disruption Score 0.50-0.74)

*Strategic monitoring required. Prepare response strategies and assess R&D implications.*

"""

        for idx, signal in enumerate(high, 1):
            report += self._format_signal_detail(signal, idx)

        report += f"""
---

## MODERATE Signals (Disruption Score 0.30-0.49)

*Background tracking. {len(moderate)} signals identified for continued observation.*

"""

        # Save report
        with open(output_path, 'w') as f:
            f.write(report)

        return report

    def generate_weak_signal_digest(self, signals: List[Dict], output_path: str) -> str:
        """
        Generate Weak Signal Digest focusing on 12-36 month horizon signals.

        Args:
            signals: List of scored signals
            output_path: Path to save markdown file

        Returns:
            str: Generated markdown content
        """
        # Filter for high novelty (weak signals)
        weak_signals = [s for s in signals if s.get('novelty_score', 0) >= 0.6]
        weak_signals.sort(key=lambda x: x.get('novelty_score', 0), reverse=True)

        report = f"""# Weak Signal Digest: European Agriculture

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Signals Identified:** {len(weak_signals)}

---

## What are Weak Signals?

Weak signals are early indicators of potential disruptions that have not yet reached
mainstream awareness. These signals have **high novelty scores** (≥0.6) and represent
emerging trends 12-36 months before they impact the market.

---

## Top Emerging Signals

"""

        for idx, signal in enumerate(weak_signals[:10], 1):  # Top 10
            novelty = signal.get('novelty_score', 0)
            horizon = signal.get('time_horizon', '36_MONTH')
            dimension = signal.get('primary_dimension', 'UNKNOWN')

            report += f"""
### {idx}. {signal.get('title', 'Unknown Signal')}

**Novelty Score:** {novelty:.2f} | **PESTEL:** {dimension} | **Horizon:** {horizon.replace('_', ' ')}

{signal.get('content', '')[:200]}...

**Strategic Implication:** This signal is highly novel compared to current industry trends.
Monitor for acceleration in patent filings, regulatory mentions, or startup activity.

---
"""

        report += """
## Recommended Actions

1. **Establish monitoring protocols** for top 5 weak signals
2. **Assign research leads** for each PESTEL dimension represented
3. **Quarterly review** to assess if weak signals are strengthening
4. **Prepare contingency strategies** for CRITICAL-classified weak signals

"""

        # Save report
        with open(output_path, 'w') as f:
            f.write(report)

        return report

    def generate_rd_alignment_brief(self, signals: List[Dict], output_path: str,
                                    company_priorities: Dict[str, float] = None) -> str:
        """
        Generate R&D Alignment Brief with strategic recommendations.

        Args:
            signals: List of scored signals
            output_path: Path to save markdown file
            company_priorities: Dict of strategic priorities with weights

        Returns:
            str: Generated markdown content
        """
        if company_priorities is None:
            company_priorities = {
                'electrification': 0.90,
                'autonomous_farming': 0.75,
                'precision_agriculture': 0.70,
                'carbon_neutrality': 0.85,
                'digital_platforms': 0.65
            }

        # Score R&D alignment
        aligned_signals = []
        for signal in signals:
            alignment_score = self._calculate_alignment(signal, company_priorities)
            aligned_signals.append({
                **signal,
                'alignment_score': alignment_score
            })

        # Sort by alignment
        aligned_signals.sort(key=lambda x: x['alignment_score'], reverse=True)

        report = f"""# R&D Alignment Brief: Company A Strategic Priorities

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Signals Evaluated:** {len(signals)}

---

## Company A Strategic Priorities (Weighted)

"""

        for priority, weight in sorted(company_priorities.items(), key=lambda x: x[1], reverse=True):
            report += f"- **{priority.replace('_', ' ').title()}:** {weight:.0%}\n"

        report += f"""

---

## Top R&D Investment Opportunities

*These disruption signals have the highest strategic alignment with Company A's priorities.*

"""

        for idx, signal in enumerate(aligned_signals[:8], 1):  # Top 8
            title = signal.get('title', 'Unknown')
            alignment = signal.get('alignment_score', 0)
            disruption = signal.get('disruption_score', 0)
            dimension = signal.get('primary_dimension', 'UNKNOWN')

            # Recommendation
            if alignment >= 0.75 and disruption >= 0.70:
                recommendation = "**ACCELERATE:** Immediate R&D investment priority"
            elif alignment >= 0.75:
                recommendation = "**BUILD:** High strategic fit - develop capabilities"
            elif disruption >= 0.70:
                recommendation = "**PARTNER:** High disruption - consider M&A or partnerships"
            else:
                recommendation = "**MONITOR:** Track developments, prepare response"

            report += f"""
### {idx}. {title}

**Alignment Score:** {alignment:.2f} | **Disruption Score:** {disruption:.2f} | **PESTEL:** {dimension}

**Recommendation:** {recommendation}

**Rationale:** {self._generate_rationale(signal, company_priorities)}

---
"""

        report += """
## Strategic Recommendations

### Immediate Actions (Next Quarter)
1. Initiate R&D projects for top 3 ACCELERATE opportunities
2. Establish partnerships for high-disruption, moderate-fit signals
3. Allocate innovation budget across all 6 PESTEL dimensions

### Medium-Term (6-12 Months)
1. Build capability gaps for BUILD-classified opportunities
2. Monitor weak signals for acceleration
3. Prepare board presentation on industry disruption landscape

"""

        # Save report
        with open(output_path, 'w') as f:
            f.write(report)

        return report

    def _format_signal_detail(self, signal: Dict, idx: int) -> str:
        """Format individual signal for disruption map."""
        title = signal.get('title', 'Unknown Signal')
        score = signal.get('disruption_score', 0)
        dimension = signal.get('primary_dimension', 'UNKNOWN')
        horizon = signal.get('time_horizon', '36_MONTH')
        novelty = signal.get('novelty_score', 0)
        impact = signal.get('impact_score', 0)
        velocity = signal.get('velocity_score', 0)

        return f"""
### {idx}. {title}

**Disruption Score:** {score:.2f} | **PESTEL:** {dimension} | **Horizon:** {horizon.replace('_', ' ')}

**Component Scores:**
- Novelty: {novelty:.2f} (how new/emerging)
- Impact: {impact:.2f} (industry-wide effect)
- Velocity: {velocity:.2f} (acceleration rate)

**Summary:** {signal.get('content', '')[:250]}...

---
"""

    def _calculate_alignment(self, signal: Dict, priorities: Dict[str, float]) -> float:
        """Calculate strategic alignment score."""
        from difflib import SequenceMatcher

        title = signal.get('title', '').lower()
        content = signal.get('content', '').lower()
        combined = f"{title} {content}"

        max_alignment = 0.0
        for priority, weight in priorities.items():
            # Simple keyword match
            if priority.replace('_', ' ') in combined:
                alignment = weight
                max_alignment = max(max_alignment, alignment)

        # Boost for high disruption score
        disruption = signal.get('disruption_score', 0)
        final_alignment = max_alignment * 0.7 + disruption * 0.3

        return min(final_alignment, 1.0)

    def _generate_rationale(self, signal: Dict, priorities: Dict[str, float]) -> str:
        """Generate brief rationale for R&D recommendation."""
        alignment = signal.get('alignment_score', 0)
        disruption = signal.get('disruption_score', 0)

        if alignment >= 0.75 and disruption >= 0.70:
            return "High strategic fit with proven disruption potential. Immediate investment recommended."
        elif alignment >= 0.75:
            return "Strong alignment with Company A priorities. Build internal capabilities."
        elif disruption >= 0.70:
            return "Significant industry disruption potential. Consider external partnerships or M&A."
        else:
            return "Moderate strategic relevance. Continue monitoring for signal strengthening."


if __name__ == "__main__":
    # Example usage
    from signal_classifier import SignalClassifier
    from disruption_scorer import DisruptionScorer

    # Sample signals
    sample_signals_raw = [
        {
            'title': 'EU Battery Swapping Mandate for Agricultural Machinery by 2027',
            'content': 'European Union announces mandatory battery swapping infrastructure '
                      'for electric agricultural equipment, accelerating electrification transition.',
            'source': 'EUR-Lex',
            'url': 'https://eur-lex.europa.eu/example',
            'date': '2024-03-15'
        },
        {
            'title': 'Autonomous Tractor Patent Filings Surge 300% in Germany',
            'content': 'German agricultural machinery manufacturers filed record number of '
                      'autonomous tractor patents, indicating major R&D investment shift.',
            'source': 'Espacenet',
            'url': 'https://espacenet.europa.eu/example',
            'date': '2024-02-20'
        }
    ]

    # Process signals
    classifier = SignalClassifier()
    scorer = DisruptionScorer()

    processed_signals = []
    for raw_signal in sample_signals_raw:
        classified = classifier.classify_signal(raw_signal)
        scored = scorer.score_signal(classified)
        processed_signals.append(scored)

    # Generate reports
    generator = StrategicReportGenerator()

    print("Generating strategic reports...")

    disruption_map = generator.generate_disruption_map(
        processed_signals,
        '/Users/ritvikvasikarla/Desktop/innovation-radar/q2_solution/outputs/reports/disruption_map.md'
    )
    print("✓ Disruption Map generated")

    weak_signal_digest = generator.generate_weak_signal_digest(
        processed_signals,
        '/Users/ritvikvasikarla/Desktop/innovation-radar/q2_solution/outputs/reports/weak_signal_digest.md'
    )
    print("✓ Weak Signal Digest generated")

    rd_brief = generator.generate_rd_alignment_brief(
        processed_signals,
        '/Users/ritvikvasikarla/Desktop/innovation-radar/q2_solution/outputs/reports/rd_alignment_brief.md'
    )
    print("✓ R&D Alignment Brief generated")

    print("\n" + "=" * 70)
    print("All strategic reports generated successfully!")
    print("Location: q2_solution/outputs/reports/")
    print("=" * 70)
