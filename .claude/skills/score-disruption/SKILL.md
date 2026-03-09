---
disable-model-invocation: true
---

# /score-disruption Skill

Fast disruption scoring for European agricultural signals using Q2 pipeline.

## Usage

```bash
/score-disruption "The EU has just mandated a 40% reduction in synthetic fertilizer use by 2028."
```

## What It Does

This skill pipes your signal text directly to the Q2 disruption detection pipeline and returns:
- **Disruption Score** (0.00-1.00)
- **Classification** (CRITICAL/HIGH/MODERATE/LOW)
- **Time Horizon** (12_MONTH/24_MONTH/36_MONTH)
- **Primary PESTEL Dimension**
- **Component Scores** (Novelty, Impact, Velocity)

## Command

```bash
python cli_scorer.py "$ARGUMENTS"
```

## Example Output

```
Disruption Score: 0.52 (HIGH)
Time Horizon: 36_MONTH
Primary PESTEL Dimension: LEGAL
Novelty: 0.80 | Impact: 0.42 | Velocity: 0.30
```

## Technical Details

The CLI wrapper:
1. Takes your input text as a signal
2. Runs it through `SignalClassifier` (PESTEL dimension scoring)
3. Runs it through `DisruptionScorer` (Novelty × Impact × Velocity formula)
4. Returns formatted results

**No model invocation** - direct Python execution for <1s response time.

## Use Cases

- Quick signal triage during research
- Testing PESTEL classification accuracy
- Benchmarking disruption formulas
- Validating Scout agent signals before graph ingestion
