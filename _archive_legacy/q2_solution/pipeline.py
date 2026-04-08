"""
Enhanced Pipeline for Q2 Solution
==================================

Production-grade pipeline with:
- Agent-based architecture (ClassifierAgent → EvaluatorAgent → SynthesisAgent)
- Pydantic model validation
- Storage abstraction layer
- Error handling and logging
- Progress tracking

Follows Gemini's suggested architecture while maintaining our domain-specific logic.
"""

from typing import List, Dict, Optional
from pathlib import Path
import json
from datetime import datetime

from models import RawSignal, ClassifiedSignal, ScoredSignal, StrategicReport
from agents import ClassifierAgent, EvaluatorAgent, SynthesisAgent
from storage import JSONSignalStore
from innovation_radar import InnovationRadar


class DisruptionDetectionPipeline:
    """
    End-to-end pipeline for industry disruption detection.

    Architecture:
        Raw Signals → ClassifierAgent → EvaluatorAgent → Storage → SynthesisAgent → Reports
    """

    def __init__(
        self,
        output_dir: str = "./outputs",
        company_priorities: Optional[Dict[str, float]] = None,
        use_storage: bool = True
    ):
        """
        Initialize pipeline with agents and storage.

        Args:
            output_dir: Directory for outputs
            company_priorities: Company A strategic priorities
            use_storage: Whether to persist signals to storage
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize agents
        self.classifier_agent = ClassifierAgent()
        self.evaluator_agent = EvaluatorAgent()
        self.synthesis_agent = SynthesisAgent(company_priorities=company_priorities)

        # Initialize storage
        self.use_storage = use_storage
        if use_storage:
            self.store = JSONSignalStore(
                filepath=str(self.output_dir / "data" / "signals_store.json")
            )

        # Initialize visualization
        self.radar = InnovationRadar()

        # Execution stats
        self.stats = {
            'signals_processed': 0,
            'classification_errors': 0,
            'evaluation_errors': 0,
            'critical_count': 0,
            'high_count': 0,
            'moderate_count': 0,
            'low_count': 0
        }

    def process_signals(self, raw_signals: List[RawSignal]) -> StrategicReport:
        """
        Process raw signals through full pipeline.

        Pipeline flow:
        1. Validate input (Pydantic)
        2. Classify (ClassifierAgent)
        3. Evaluate (EvaluatorAgent)
        4. Store (JSONSignalStore)
        5. Synthesize (SynthesisAgent)
        6. Generate outputs (Reports + Visualizations)

        Args:
            raw_signals: List of Pydantic RawSignal models

        Returns:
            StrategicReport with insights and recommendations
        """
        print("=" * 70)
        print("DISRUPTION DETECTION PIPELINE - EXECUTION")
        print("=" * 70)
        print(f"\nProcessing {len(raw_signals)} signals...\n")

        scored_signals: List[ScoredSignal] = []

        # Step 1: Classification
        print("Step 1: Classifying signals (PESTEL dimensions)...")
        classified_signals: List[ClassifiedSignal] = []

        for idx, raw_signal in enumerate(raw_signals, 1):
            try:
                classified = self.classifier_agent.classify(raw_signal)
                classified_signals.append(classified)
                print(f"  [{idx}/{len(raw_signals)}] ✓ {classified.title[:50]}... → {classified.primary_dimension}")
            except Exception as e:
                print(f"  [{idx}/{len(raw_signals)}] ✗ Classification error: {e}")
                self.stats['classification_errors'] += 1

        print(f"✓ Classified {len(classified_signals)}/{len(raw_signals)} signals")

        # Step 2: Evaluation
        print("\nStep 2: Evaluating disruption potential...")

        for idx, classified in enumerate(classified_signals, 1):
            try:
                scored = self.evaluator_agent.evaluate(classified)
                scored_signals.append(scored)

                # Update stats
                if scored.classification == 'CRITICAL':
                    self.stats['critical_count'] += 1
                elif scored.classification == 'HIGH':
                    self.stats['high_count'] += 1
                elif scored.classification == 'MODERATE':
                    self.stats['moderate_count'] += 1
                else:
                    self.stats['low_count'] += 1

                print(f"  [{idx}/{len(classified_signals)}] ✓ {scored.title[:40]}... "
                      f"Score: {scored.disruption_score:.2f} ({scored.classification})")
            except Exception as e:
                print(f"  [{idx}/{len(classified_signals)}] ✗ Evaluation error: {e}")
                self.stats['evaluation_errors'] += 1

        print(f"✓ Evaluated {len(scored_signals)} signals")
        print(f"  - CRITICAL: {self.stats['critical_count']}")
        print(f"  - HIGH: {self.stats['high_count']}")
        print(f"  - MODERATE: {self.stats['moderate_count']}")

        # Step 3: Storage
        if self.use_storage:
            print("\nStep 3: Persisting signals to storage...")
            for signal in scored_signals:
                self.store.save_signal(signal)
            print(f"✓ Saved {len(scored_signals)} signals to storage")

        # Step 4: Synthesis
        print("\nStep 4: Synthesizing strategic insights...")
        strategic_report = self.synthesis_agent.synthesize(scored_signals)
        print(f"✓ Generated strategic report with {len(strategic_report.insights)} insights")

        # Step 5: Generate outputs
        print("\nStep 5: Generating visualizations and reports...")
        self._generate_outputs(scored_signals, strategic_report)

        self.stats['signals_processed'] = len(scored_signals)

        print("\n" + "=" * 70)
        print("PIPELINE EXECUTION COMPLETE")
        print("=" * 70)
        print(f"Signals Processed: {self.stats['signals_processed']}")
        print(f"CRITICAL Disruptions: {self.stats['critical_count']}")
        print(f"HIGH Disruptions: {self.stats['high_count']}")
        print(f"Errors: {self.stats['classification_errors'] + self.stats['evaluation_errors']}")
        print("=" * 70)

        return strategic_report

    def _generate_outputs(self, scored_signals: List[ScoredSignal], report: StrategicReport) -> None:
        """Generate all output artifacts."""
        # Convert Pydantic models to dicts for existing visualization code
        signals_dict = [s.model_dump() for s in scored_signals]

        # Innovation Radar
        radar_fig = self.radar.create_radar(signals_dict)
        radar_path = self.output_dir / "charts" / "innovation_radar.html"
        radar_path.parent.mkdir(exist_ok=True)
        radar_fig.write_html(str(radar_path))
        print(f"  ✓ Innovation Radar: {radar_path}")

        # PESTEL Heatmap
        heatmap_fig = self.radar.create_pestel_heatmap(signals_dict)
        heatmap_path = self.output_dir / "charts" / "pestel_heatmap.html"
        heatmap_fig.write_html(str(heatmap_path))
        print(f"  ✓ PESTEL Heatmap: {heatmap_path}")

        # Strategic Report (JSON)
        report_path = self.output_dir / "reports" / "strategic_report.json"
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report.model_dump(), f, indent=2, default=str)
        print(f"  ✓ Strategic Report (JSON): {report_path}")

        # Strategic Report (Markdown)
        md_report_path = self.output_dir / "reports" / "strategic_report.md"
        with open(md_report_path, 'w') as f:
            f.write(self._format_markdown_report(report))
        print(f"  ✓ Strategic Report (Markdown): {md_report_path}")

    def _format_markdown_report(self, report: StrategicReport) -> str:
        """Format strategic report as Markdown."""
        md = f"""# Strategic Intelligence Report: European Agriculture Disruptions

**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M')}
**Signals Analyzed:** {report.total_signals}

---

## Executive Summary

{report.executive_summary}

### Key Metrics

- **CRITICAL Disruptions:** {report.critical_count}
- **HIGH Priority Disruptions:** {report.high_count}
- **MODERATE Signals:** {report.moderate_count}

---

## Top Strategic Recommendation

**{report.top_recommendation}**

---

## Detailed Insights

"""

        for idx, insight in enumerate(report.insights[:10], 1):
            md += f"""
### {idx}. {insight.signal_title}

**PESTEL Dimension:** {insight.dimension}
**Disruption Score:** {insight.disruption_score:.2f}
**Time Horizon:** {insight.time_horizon.replace('_', ' ')}
**Alignment Score:** {f"{insight.alignment_score:.2f}" if insight.alignment_score else 'N/A'}

**Recommendation:** {insight.recommendation}

**Rationale:** {insight.rationale}

---
"""

        md += """
## Next Steps

1. **Immediate Action:** Address CRITICAL and HIGH priority disruptions
2. **Strategic Planning:** Align R&D roadmap with top recommendations
3. **Monitoring:** Track MODERATE signals for acceleration
4. **Board Presentation:** Share insights with Company A leadership

---

*Generated by AgriNova Q2 Disruption Detection Pipeline*
"""

        return md

    def get_stats(self) -> Dict:
        """Get pipeline execution statistics."""
        return self.stats


# Example usage
if __name__ == "__main__":
    from models import RawSignal

    # Sample signals
    sample_signals = [
        RawSignal(
            title="EU Battery Swapping Mandate for Agricultural Machinery by 2027",
            content="The European Union announced a regulatory mandate requiring battery swapping infrastructure for electric agricultural equipment.",
            source="EUR-Lex",
            url="https://eur-lex.europa.eu/test1",
            date="2024-03-15"
        ),
        RawSignal(
            title="German AgTech Startups Raise Record €450M for Autonomous Farming",
            content="German agricultural technology startups raised record funding for autonomous tractor systems and AI-powered field management.",
            source="Crunchbase",
            url="https://crunchbase.com/test2",
            date="2024-02-28"
        )
    ]

    # Initialize pipeline
    pipeline = DisruptionDetectionPipeline(
        output_dir="./test_outputs",
        company_priorities={
            'electrification': 0.90,
            'autonomous_farming': 0.75,
            'precision_agriculture': 0.70
        }
    )

    # Execute
    report = pipeline.process_signals(sample_signals)

    # Display results
    print(f"\n📊 Pipeline Statistics:")
    print(f"   Signals Processed: {pipeline.stats['signals_processed']}")
    print(f"   CRITICAL: {pipeline.stats['critical_count']}")
    print(f"   HIGH: {pipeline.stats['high_count']}")
    print(f"\n📄 Strategic Report:")
    print(f"   Insights: {len(report.insights)}")
    print(f"   Top Recommendation: {report.top_recommendation[:80]}...")
