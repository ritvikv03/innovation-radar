"""
Q2 Pipeline: End-to-End Industry Disruption Detection
======================================================

Main orchestrator for Solution A (Single Unified Agent).

Usage:
    python q2_pipeline.py --query "What forces are reshaping EU precision agriculture?"
    python q2_pipeline.py --demo   # Run with sample data
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Import Q2 modules
from signal_classifier import SignalClassifier
from disruption_scorer import DisruptionScorer
from innovation_radar import InnovationRadar
from strategic_report_generator import StrategicReportGenerator

# Import database module
try:
    from database import SignalDatabase
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("Warning: database.py not found. Signals will not be persisted to SQLite.")


class Q2Pipeline:
    """
    End-to-end pipeline for Q2 Industry Disruption Detection.
    """

    def __init__(self, output_dir: str = './outputs', db_path: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        (self.output_dir / 'reports').mkdir(exist_ok=True)
        (self.output_dir / 'charts').mkdir(exist_ok=True)
        (self.output_dir / 'data').mkdir(exist_ok=True)

        self.classifier = SignalClassifier()
        self.scorer = DisruptionScorer(db_path=db_path)  # Pass db_path to scorer
        self.radar = InnovationRadar()
        self.report_generator = StrategicReportGenerator()

        # Initialize database connection
        if DATABASE_AVAILABLE:
            self.db = SignalDatabase(db_path)
            print(f"✓ Database initialized at: {self.db.db_path}")
        else:
            self.db = None

    def run(self, raw_signals: list, company_priorities: dict = None):
        """
        Execute full Q2 pipeline.

        Args:
            raw_signals: List of raw signal dictionaries
            company_priorities: Company A strategic priorities (optional)

        Returns:
            dict: Pipeline execution results
        """
        print("=" * 70)
        print("Q2 INDUSTRY DISRUPTION DETECTION PIPELINE")
        print("=" * 70)
        print(f"\nProcessing {len(raw_signals)} signals...\n")

        # Step 1: Classification
        print("Step 1: Classifying signals into PESTEL dimensions...")
        classified_signals = []
        for signal in raw_signals:
            classified = self.classifier.classify_signal(signal)
            classified_signals.append(classified)
        print(f"✓ Classified {len(classified_signals)} signals")

        # Step 2: Disruption Scoring
        print("\nStep 2: Scoring disruption potential...")
        scored_signals = []
        for signal in classified_signals:
            scored = self.scorer.score_signal(signal)
            scored_signals.append(scored)

        critical_count = sum(1 for s in scored_signals if s.get('classification') == 'CRITICAL')
        high_count = sum(1 for s in scored_signals if s.get('classification') == 'HIGH')
        print(f"✓ Scored {len(scored_signals)} signals")
        print(f"  - CRITICAL: {critical_count}")
        print(f"  - HIGH: {high_count}")

        # Save scored signals to SQLite database
        if self.db:
            print("\nStep 2b: Persisting signals to SQLite database...")
            persisted_count = 0
            for signal in scored_signals:
                try:
                    # Extract entities as list
                    entities = []
                    signal_entities = signal.get('entities', {})
                    if isinstance(signal_entities, dict):
                        for entity_list in signal_entities.values():
                            if isinstance(entity_list, list):
                                entities.extend(entity_list)

                    # Extract themes
                    themes = [signal.get('primary_dimension')]
                    themes.extend(signal.get('secondary_dimensions', []))

                    # Insert into database
                    self.db.insert_signal(
                        title=signal.get('title', 'Untitled'),
                        content=signal.get('content', ''),
                        source=signal.get('source', 'Unknown'),
                        url=signal.get('url', 'https://unknown.local'),
                        date_ingested=signal.get('scored_at', datetime.now().isoformat()),
                        primary_dimension=signal.get('primary_dimension', 'UNKNOWN'),
                        novelty_score=signal.get('novelty_score'),
                        impact_score=signal.get('impact_score'),
                        velocity_score=signal.get('velocity_score'),
                        disruption_classification=signal.get('classification'),
                        entities=entities,
                        themes=themes
                    )
                    persisted_count += 1
                except Exception as e:
                    print(f"  ⚠ Failed to persist signal '{signal.get('title', 'unknown')}': {e}")

            print(f"✓ Persisted {persisted_count}/{len(scored_signals)} signals to database")

            # Print database statistics
            stats = self.db.get_database_stats()
            print(f"  - Total signals in database: {stats['total_signals']}")
            print(f"  - Signals per dimension: {stats['signals_per_dimension']}")

        # Save scored signals to JSON (for backwards compatibility)
        scored_path = self.output_dir / 'data' / 'scored_signals.json'
        with open(scored_path, 'w') as f:
            json.dump(scored_signals, f, indent=2, default=str)
        print(f"  - Also saved to JSON: {scored_path}")

        # Step 3: Generate Innovation Radar
        print("\nStep 3: Generating Innovation Radar visualization...")
        radar_fig = self.radar.create_radar(scored_signals)
        radar_path = self.output_dir / 'charts' / 'innovation_radar.html'
        radar_fig.write_html(str(radar_path))
        print(f"✓ Innovation Radar saved to: {radar_path}")

        # Step 4: Generate PESTEL Heatmap
        print("\nStep 4: Generating PESTEL Disruption Heatmap...")
        heatmap_fig = self.radar.create_pestel_heatmap(scored_signals)
        heatmap_path = self.output_dir / 'charts' / 'pestel_heatmap.html'
        heatmap_fig.write_html(str(heatmap_path))
        print(f"✓ PESTEL Heatmap saved to: {heatmap_path}")

        # Step 5: Generate Strategic Reports
        print("\nStep 5: Generating strategic reports...")

        # Disruption Map
        disruption_map_path = self.output_dir / 'reports' / 'disruption_map.md'
        self.report_generator.generate_disruption_map(scored_signals, str(disruption_map_path))
        print(f"  ✓ Disruption Map: {disruption_map_path}")

        # Weak Signal Digest
        weak_signal_path = self.output_dir / 'reports' / 'weak_signal_digest.md'
        self.report_generator.generate_weak_signal_digest(scored_signals, str(weak_signal_path))
        print(f"  ✓ Weak Signal Digest: {weak_signal_path}")

        # R&D Alignment Brief
        rd_brief_path = self.output_dir / 'reports' / 'rd_alignment_brief.md'
        self.report_generator.generate_rd_alignment_brief(
            scored_signals,
            str(rd_brief_path),
            company_priorities
        )
        print(f"  ✓ R&D Alignment Brief: {rd_brief_path}")

        # Pipeline summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'signals_processed': len(scored_signals),
            'critical_disruptions': critical_count,
            'high_disruptions': high_count,
            'outputs': {
                'innovation_radar': str(radar_path),
                'pestel_heatmap': str(heatmap_path),
                'disruption_map': str(disruption_map_path),
                'weak_signal_digest': str(weak_signal_path),
                'rd_alignment_brief': str(rd_brief_path)
            }
        }

        summary_path = self.output_dir / 'pipeline_summary.json'
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)

        print("\n" + "=" * 70)
        print("PIPELINE EXECUTION COMPLETE")
        print("=" * 70)
        print(f"Summary saved to: {summary_path}")
        print("\nNext Steps:")
        print("1. Open innovation_radar.html in a browser to explore disruptions")
        print("2. Review strategic reports in outputs/reports/")
        print("3. Share findings with Company A leadership team")
        print("=" * 70)

        return summary


def get_sample_signals():
    """
    Generate sample European agricultural disruption signals.
    """
    return [
        {
            'title': 'EU Battery Swapping Mandate for Agricultural Machinery by 2027',
            'content': 'The European Union announced a groundbreaking regulatory mandate '
                      'requiring all new agricultural machinery manufacturers to adopt '
                      'standardized battery swapping infrastructure by 2027. This regulation '
                      'accelerates the electrification transition across tractors, harvesters, '
                      'and precision farming equipment. Impact: 150,000+ European farms, '
                      '€5B equipment market. Technology readiness: moderate. Stage V emissions '
                      'compliance drives urgency.',
            'source': 'EUR-Lex',
            'url': 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R0567',
            'date': '2024-03-15'
        },
        {
            'title': 'German AgTech Startups Raise Record €450M for Autonomous Farming',
            'content': 'German agricultural technology startups raised a record €450 million '
                      'in Q1 2024, with 60% focused on autonomous tractor systems and AI-powered '
                      'field management. Notable deals: FarmDroid (€120M), AgriBot Systems (€95M). '
                      'Patent filings for autonomous navigation surged 300% year-over-year. '
                      'Technology maturity: commercial pilots underway across Bavaria and '
                      'Lower Saxony. Regulatory clarity expected by 2025.',
            'source': 'Crunchbase / AgFunder',
            'url': 'https://agfunder.com/research/2024-german-agtech-report',
            'date': '2024-02-28'
        },
        {
            'title': 'France Introduces €2B Subsidy Program for Precision Agriculture Adoption',
            'content': 'The French Ministry of Agriculture launched a €2 billion subsidy program '
                      'targeting precision agriculture adoption among small and mid-sized farms '
                      '(<100 hectares). Eligible technologies: GPS-guided tractors, variable rate '
                      'application systems, soil sensors, drone monitoring. Expected beneficiaries: '
                      '85,000 farms. Program timeline: 2024-2027. Political driver: CAP Strategic '
                      'Plan alignment, carbon reduction targets.',
            'source': 'French Ministry of Agriculture',
            'url': 'https://agriculture.gouv.fr/precision-agriculture-subsidy-2024',
            'date': '2024-01-20'
        },
        {
            'title': 'Eastern European Labor Shortage Drives 40% Wage Increase for Farm Workers',
            'content': 'Poland, Romania, and Bulgaria report 35-40% wage increases for seasonal '
                      'agricultural labor due to migration to Western Europe and urban centers. '
                      'Impact: Rising operational costs for labor-intensive crops (fruits, '
                      'vegetables). Farmer response: accelerated automation investments, '
                      'particularly in harvesting robotics. Social implication: rural '
                      'depopulation accelerating. Economic pressure: tightening farm profit margins.',
            'source': 'Eurostat / COPA-COGECA',
            'url': 'https://ec.europa.eu/eurostat/farm-labor-2024',
            'date': '2024-02-10'
        },
        {
            'title': 'EU Nature Restoration Law Mandates 10% Land Rewilding by 2030',
            'content': 'The European Parliament approved the Nature Restoration Law requiring '
                      'member states to restore 10% of agricultural land to natural ecosystems '
                      'by 2030. Impact: ~15 million hectares affected. Farmer compensation: '
                      'under negotiation. Technology opportunity: biodiversity monitoring systems, '
                      'carbon credit platforms, regenerative agriculture equipment. Environmental '
                      'forcing function: non-negotiable legal mandate. Industry disruption: '
                      'traditional tillage equipment demand declines.',
            'source': 'European Parliament / EEA',
            'url': 'https://www.europarl.europa.eu/nature-restoration-law-2024',
            'date': '2024-03-01'
        },
        {
            'title': 'Fertilizer Prices Surge 65% Due to Natural Gas Supply Disruptions',
            'content': 'European fertilizer prices increased 65% year-over-year following '
                      'natural gas supply constraints. Impact: nitrogen fertilizer €850/ton '
                      '(vs. €515/ton in 2023). Farmer response: precision application systems, '
                      'variable rate technology adoption accelerating. Economic consequence: '
                      'crop input costs up 20-25%, squeezing margins. Market opportunity: '
                      'biological fertilizers, nitrogen-fixing technologies, soil health platforms.',
            'source': 'Rabobank / CRU Group',
            'url': 'https://www.rabobank.com/fertilizer-market-outlook-2024',
            'date': '2024-02-15'
        },
        {
            'title': 'Carbon Tax on Diesel Agricultural Machinery Proposed for 2026',
            'content': 'European Commission proposes carbon tax on diesel-powered agricultural '
                      'equipment starting 2026, estimated €500-800/ton CO2. Projected impact: '
                      '€2,000-3,500/year for average farm operation. Political debate: farmer '
                      'protests in France, Netherlands. Technology implication: electric and '
                      'hydrogen equipment competitiveness improves. Legal timeline: final '
                      'regulation expected Q4 2024, enforcement 2026. Industry strategic risk: '
                      'diesel equipment residual value collapse.',
            'source': 'European Commission DG CLIMA',
            'url': 'https://ec.europa.eu/clima/carbon-tax-agriculture-2026',
            'date': '2024-03-05'
        },
        {
            'title': 'AI-Powered Crop Disease Detection Patents Increase 220% in European Patent Office',
            'content': 'European Patent Office reports 220% increase in AI-powered crop disease '
                      'detection patent filings (2022-2024). Leading applicants: John Deere, '
                      'BASF, Bayer, plus 15 AgTech startups. Technology maturity: commercial '
                      'products expected 2025-2026. Farmer value proposition: 30-40% reduction '
                      'in pesticide use, early disease intervention. Market size: €1.2B European '
                      'precision agriculture market. Technological convergence: computer vision, '
                      'IoT sensors, satellite imagery.',
            'source': 'Espacenet (EPO)',
            'url': 'https://worldwide.espacenet.com/statistics/ai-agriculture-2024',
            'date': '2024-01-30'
        }
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Q2 Industry Disruption Detection Pipeline')
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run with sample European agricultural signals'
    )
    parser.add_argument(
        '--signals-file',
        type=str,
        help='Path to JSON file containing raw signals'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./outputs',
        help='Output directory for reports and charts'
    )

    args = parser.parse_args()

    # Load signals
    if args.demo:
        print("Running in DEMO mode with sample European agricultural signals...")
        raw_signals = get_sample_signals()
    elif args.signals_file:
        with open(args.signals_file, 'r') as f:
            raw_signals = json.load(f)
    else:
        print("ERROR: Must specify either --demo or --signals-file")
        sys.exit(1)

    # Company A strategic priorities (from proposal context)
    company_priorities = {
        'electrification': 0.90,
        'autonomous_farming': 0.75,
        'precision_agriculture': 0.70,
        'carbon_neutrality': 0.85,
        'digital_platforms': 0.65
    }

    # Execute pipeline
    pipeline = Q2Pipeline(output_dir=args.output_dir)
    summary = pipeline.run(raw_signals, company_priorities)

    print(f"\n✓ All outputs generated successfully!")
    print(f"  Open {summary['outputs']['innovation_radar']} to explore results.")
