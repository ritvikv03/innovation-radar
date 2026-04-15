---
title: Fendt Sentinel
emoji: 🚜
colorFrom: blue
colorTo: blue
sdk: docker
pinned: false
---

# Fendt PESTEL-EL Sentinel

**Autonomous Strategic Intelligence for AGCO/Fendt**

A production intelligence platform that monitors macro-environmental signals across six PESTEL dimensions, scores them with AI, stores them in a vector database, and presents them in a C-suite war-room dashboard.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Dashboard | Dash + Dash Bootstrap Components + Plotly |
| LLM | HuggingFace InferenceClient — `meta-llama/Llama-3.1-8B-Instruct` (Cerebras provider) |
| Vector Store | DataStax Astra DB — Nvidia NV-Embed-QA embeddings (1024 dims, cosine) |
| Knowledge Graph | LangGraph 4-node RAG pipeline (SPO triples + causal chains) |
| Multi-Agent Chat | LangGraph Router → Calculator / Analyst |
| Scheduler | APScheduler — 6-hour Scout cycle |

---

## Getting Started

```bash
# 1. Clone and install dependencies
git clone <repo-url>
cd innovation-radar
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
# Edit .env and fill in:
#   HUGGINGFACEHUB_API_TOKEN   — from huggingface.co/settings/tokens
#   ASTRA_DB_TOKEN             — from Astra DB console
#   ASTRA_DB_ENDPOINT          — from Astra DB console
#   FIRECRAWL_API_KEY          — optional, for HTML page scraping

# 3. Run the dashboard
python app.py
# Opens at http://localhost:8050

# 4. Or run a single pipeline pass (score + persist one article)
python run_pipeline.py

# 5. Dry-run (score without saving to Astra DB)
python run_pipeline.py --no-save

# 6. Score a specific URL
python run_pipeline.py --url https://example.com/article
```

---

## Agent Roles

| Agent | Module | Role |
|-------|--------|------|
| Scout | `core/scheduler.py` + `core/scraper.py` | 6-hour RSS/HTML scrape cycle across PESTEL sources |
| Analyst | `core/graph_engine.py` | Builds SPO triples + causal chains after each ingestion |
| Critic | `core/pipeline.py` `LLMScoreResponse` + `Signal` validators | EU Data Act 2026 provenance enforcement |
| Writer | `core/summary_engine.py` | Markdown intelligence briefs with LLM + rule-based fallback |
| Advisor | `core/agents.py` | LangGraph multi-agent chat (Router → Calculator / Analyst) |

---

## Dashboard Tabs

| Tab | Purpose |
|-----|---------|
| Overview | KPI tiles, urgency matrix, velocity chart, disruption distribution |
| Field Intelligence | Live signal feed with PESTEL filter and semantic search |
| Radar | Plotly radar chart of disruption scores by dimension |
| Knowledge Graph | Interactive Cytoscape graph of SPO triples and causal chains |
| Inquisition | LangGraph multi-agent chat for quantitative + synthesis queries |
| Intelligence Brief | Auto-generated BLUF executive summary with source citations |

---

## Pipeline Flow

```
PESTEL_SOURCES (core/sources.py)
    → scrape_source()         [core/scraper.py]      RSS / HTML fetch
    → score_and_save()        [core/pipeline.py]     LLM → LLMScoreResponse → Signal
    → SignalDB.insert()       [core/database.py]     Astra DB upsert
    → run_graph_update()      [core/graph_engine.py] SPO triple + causal chain
```

All external HTTP calls use `retry_with_backoff` from `core/utils.py`.

Near-duplicate signals are automatically detected via cosine distance (threshold 0.08) before LLM scoring — saving API quota and preventing redundant entries.

---

## Testing

```bash
# Run the full test suite (offline — all APIs mocked)
pytest tests/ -v

# Run a specific test file
pytest tests/test_phase1.py -v
pytest tests/test_phase2.py -v
```

Astra DB integration tests skip automatically when `ASTRA_DB_TOKEN` is not set.

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `HUGGINGFACEHUB_API_TOKEN` | Yes | LLM scoring, summaries, agent chat |
| `ASTRA_DB_TOKEN` | Yes | Astra DB application token |
| `ASTRA_DB_ENDPOINT` | Yes | Astra DB API endpoint URL |
| `FIRECRAWL_API_KEY` | Optional | HTML page scraping (falls back to `requests`) |
| `LOG_LEVEL` | Optional | Console verbosity: `DEBUG`/`INFO`/`WARNING`/`ERROR` |

---

## GitHub Actions — Required Secrets

For the automated daily sweep (`sentinel.yml`) to work, add these three secrets in **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|-------|
| `HUGGINGFACEHUB_API_TOKEN` | Your HuggingFace token |
| `ASTRA_DB_TOKEN` | Your Astra DB application token |
| `ASTRA_DB_ENDPOINT` | Your Astra DB API endpoint URL |

The workflow runs daily at midnight UTC and can also be triggered manually via **Actions → Sentinel — Daily Intelligence Sweep → Run workflow**.

---

## Adding Intelligence Sources

All sources are defined in `core/sources.py`. To add a new source, append an entry to `PESTEL_SOURCES`:

```python
{
    "url":         "https://example.com/feed.rss",
    "dimension":   "ECONOMIC",          # one of the 6 PESTEL values
    "source_name": "Example Feed",
    "scrape_mode": "rss",               # "rss", "page", or "api_ec_press"
}
```

The Scout will pick it up automatically on the next 6-hour cycle.
