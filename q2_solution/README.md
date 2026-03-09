# Q2 Solution: Industry Disruption Detection for European Agriculture

**Solution A: Single Unified Agent Architecture**

This implementation answers Research Question 2 from the AgriNova proposal:

> "How can artificial intelligence-driven analytics be used to detect, classify, and evaluate emerging technological advancements and macro-environmental signals in order to anticipate future disruptions, align innovative strategies, and better address the evolving needs of farmers in Europe?"

---

## Overview

This solution provides **industry-level disruption detection** for Company A's strategic planning team. Unlike Q1 (farmer behavior tracking), Q2 focuses on:

- **Weak signal detection** 12-36 months before mainstream impact
- **Cross-PESTEL disruption analysis** (6 dimensions + Innovation + Social Media)
- **Strategic outputs** for C-suite decision-making: Innovation Radar, Disruption Maps, R&D Alignment Briefs

---

## Architecture

```
User Query → Signal Classifier → Disruption Scorer → Strategic Analyzer → Output Generator
              (PESTEL tags)       (Novelty×Impact     (Innovation gaps)    (Radar, Reports)
                                   ×Velocity)          (R&D alignment)
```

### Components

1. **signal_classifier.py**: Classifies raw signals into PESTEL dimensions using keyword matching
2. **disruption_scorer.py**: Scores disruption potential (Novelty × Impact × Velocity)
3. **innovation_radar.py**: Generates Thoughtworks-style Innovation Radar visualization
4. **strategic_report_generator.py**: Creates board-ready Markdown reports
5. **q2_pipeline.py**: End-to-end orchestrator

---

## Installation

```bash
# Install dependencies
pip install pandas numpy plotly matplotlib

# Verify installation
cd q2_solution
python q2_pipeline.py --help
```

---

## Usage

### Option 1: Demo Mode (Sample European Signals)

```bash
python q2_pipeline.py --demo
```

This runs the pipeline with 8 pre-loaded European agricultural disruption signals.

### Option 2: Custom Signal Data

```bash
python q2_pipeline.py --signals-file your_signals.json
```

Your JSON file should contain an array of signals with this structure:

```json
[
  {
    "title": "EU Battery Swapping Mandate for Agricultural Machinery by 2027",
    "content": "The European Union announced a regulatory mandate...",
    "source": "EUR-Lex",
    "url": "https://eur-lex.europa.eu/...",
    "date": "2024-03-15"
  }
]
```

---

## Outputs

All outputs are saved to `outputs/`:

### 📊 Visualizations (`outputs/charts/`)

- **innovation_radar.html**: Interactive Plotly chart showing disruptions by PESTEL dimension and time horizon
- **pestel_heatmap.html**: Signal distribution heatmap

### 📄 Strategic Reports (`outputs/reports/`)

- **disruption_map.md**: Full analysis of CRITICAL, HIGH, and MODERATE disruptions
- **weak_signal_digest.md**: Top 10 emerging signals (novelty ≥ 0.6)
- **rd_alignment_brief.md**: R&D opportunities scored by strategic fit to Company A

### 📁 Data (`outputs/data/`)

- **scored_signals.json**: All signals with disruption scores and classifications

---

## Disruption Scoring Formula

```
Disruption Score = (0.35 × Novelty) + (0.40 × Impact) + (0.25 × Velocity)
```

### Component Scores

1. **Novelty** (35%): How new/emerging is this signal vs. historical trends?
2. **Impact** (40%): How broadly will this affect the European agricultural industry?
   - Cross-PESTEL reach
   - Regulatory forcing functions (EU mandates)
   - Technology scope
3. **Velocity** (25%): How fast is this trend accelerating?
   - Urgency keywords (immediate, urgent)
   - Near-term years (2024, 2025)

### Classification Thresholds

- **CRITICAL** (0.75-1.00): Immediate board-level attention required
- **HIGH** (0.50-0.74): Strategic monitoring, prepare response
- **MODERATE** (0.30-0.49): Track developments
- **LOW** (0.00-0.29): Background monitoring

---

## Example: Demo Output Summary

```
Signals Processed: 8
CRITICAL Disruptions: 1
  - Carbon Tax on Diesel Agricultural Machinery (Score: 0.76)
HIGH Disruptions: 6
  - EU Battery Swapping Mandate (Score: 0.71)
  - French Precision Agriculture Subsidy (Score: 0.67)
  - German AgTech Funding Surge (Score: 0.66)
  - AI Crop Disease Detection Patents (Score: 0.66)
  - EU Nature Restoration Law (Score: 0.57)
  - Fertilizer Price Surge (Score: 0.52)

Time Horizons:
  - 12 Month (Immediate): 4 signals
  - 24 Month (Emerging): 1 signal
  - 36 Month (Early-stage): 3 signals
```

---

## Testing

Run unit tests to verify functionality:

```bash
cd ../tests/q2

# Test signal classification
python test_signal_classifier.py

# Test disruption scoring
python test_disruption_scorer.py

# Test full pipeline
python test_pipeline.py
```

All tests include assertions for:
- PESTEL classification accuracy
- Entity extraction (regulations, technologies, locations)
- Disruption score component ranges
- Output file generation

---

## Customization

### Adjust Company Strategic Priorities

Edit the priorities in `q2_pipeline.py` (line ~280):

```python
company_priorities = {
    'electrification': 0.90,        # 90% priority weight
    'autonomous_farming': 0.75,
    'precision_agriculture': 0.70,
    'carbon_neutrality': 0.85,
    'digital_platforms': 0.65
}
```

These weights affect R&D Alignment scoring in strategic reports.

### Add New PESTEL Keywords

Edit `signal_classifier.py` (line ~16) to add domain-specific keywords:

```python
PESTEL_KEYWORDS = {
    'TECHNOLOGICAL': [
        'innovation', 'digital', 'automation', 'AI', 'robotics',
        # Add your keywords here
        'blockchain', 'quantum', 'nanotechnology'
    ],
    ...
}
```

---

## Deliverables Mapping to Proposal

This implementation delivers:

- ✅ **PESTEL Signal Database**: `outputs/data/scored_signals.json`
- ✅ **NLP Classification Pipeline**: `signal_classifier.py`
- ✅ **Solution A (Single Unified Agent)**: `q2_pipeline.py`
- ✅ **Innovation Radar**: `outputs/charts/innovation_radar.html`
- ✅ **Strategic Frameworks**: Disruption Map, R&D Alignment Brief
- ✅ **Board Presentation Export**: Markdown reports ready for PDF conversion

---

## Next Steps for Production

1. **Integrate Firecrawl MCP** for live European data source scraping (EUR-Lex, Espacenet, etc.)
2. **Add temporal tracking** to calculate velocity from real patent/funding trends
3. **Implement Solution B (6-Agent System)** for deeper cross-PESTEL analysis
4. **Export to PDF/PPTX** using `python-pptx` and `reportlab`
5. **Schedule daily scans** via GitHub Actions or cron jobs

---

## Support

For questions or issues:
1. Check test outputs in `tests/q2/test_outputs/`
2. Review sample reports in `outputs/reports/`
3. Inspect scored signals in `outputs/data/scored_signals.json`

---

## License

Built for Company A (AGCO/Fendt) - AgriNova Project
© 2024 AgriNova Strategy Team
