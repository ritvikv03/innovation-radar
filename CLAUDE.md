# CLAUDE.md — Fendt PESTEL-EL Sentinel: Enterprise Architecture Rules

This is the single source of truth for how this codebase is structured, what each module owns, and how to develop against it correctly.

---

## Strategic Context

The **Fendt PESTEL-EL Sentinel** is a production intelligence platform for AGCO/Fendt. It monitors macro-environmental signals across six PESTEL dimensions, scores them with AI, stores them in a vector database, and presents them in a C-suite Dash dashboard.

---

## Repository Map

```
innovation-radar/
├── app.py                   — Primary Dash war-room dashboard (DBC layout, all tabs)
├── run_pipeline.py          — CLI: score text or URL, persist to Astra DB
│
├── core/                    — THE SINGLE SOURCE OF TRUTH for all data + AI logic
│   ├── __init__.py
│   ├── database.py          — Astra DB façade + Signal Pydantic model
│   ├── pipeline.py          — HuggingFace scoring pipeline (raw text → Signal)
│   ├── scraper.py           — RSS / HTML scraping
│   ├── sources.py           — PESTEL source registry (single list of URLs)
│   ├── scheduler.py         — APScheduler background engine (6-hour cycle)
│   ├── summary_engine.py    — LLM summaries with SQLite persistence + fallback
│   ├── graph_engine.py      — LangGraph 4-node RAG knowledge graph (triples + causal chains)
│   ├── agents.py            — LangGraph multi-agent system (router → calculator / analyst)
│   ├── logger.py            — Centralised rotating file + console logger
│   └── utils.py             — retry_with_backoff (shared across all modules)
│
├── data/
│   └── graph.json           — Auto-generated knowledge graph (gitignored; rebuilt each cycle)
│
├── assets/                  — Dash CSS/JS static assets
├── lib/                     — Third-party frontend bundles (vis.js, tom-select)
├── logs/                    — Rotating log files (agent.log)
├── output/ / outputs/       — Generated reports and exports
├── raw_ingest/              — Scraped article JSON staged for pipeline
├── tests/                   — Pytest test suite
└── docs/
    └── autopsy-architecture.md — Historical defect record (read-only reference)
```

**`_archive_legacy/`** — Contains old `q2_solution/` code. Never import from it. Never add to it. It is read-only archaeology.

---

## Core Data Model

All intelligence flows through one canonical model. Never invent parallel data structures.

```python
# core/database.py

class PESTELDimension(str, Enum):
    POLITICAL | ECONOMIC | SOCIAL | TECHNOLOGICAL | ENVIRONMENTAL | LEGAL

class Signal(BaseModel):
    id: str                          # UUID, auto-generated
    title: str                       # 5–300 chars
    pestel_dimension: PESTELDimension
    content: str                     # 20+ chars, English synthesis
    source_url: str                  # verbatim provenance URL (REQUIRED)
    impact_score: float              # 0.0–1.0
    novelty_score: float             # 0.0–1.0
    velocity_score: float            # 0.0–1.0 (temporal momentum)
    date_ingested: datetime          # UTC, auto-set
    entities: list[str]              # extracted named entities
```

**The disruption score** is derived: `impact×0.5 + novelty×0.3 + velocity×0.2`. No signal is valid without all three sub-scores.

---

## Storage Architecture

**One vector database. One embedding model. No alternatives.**

| Concern | Solution |
|---------|----------|
| Signal storage | Astra DB (serverless vector store) |
| Embedding model | Astra Vectorize — Nvidia NV-Embed-QA (1024 dims, cosine) |
| Summary persistence | SQLite via `SummaryEngine` (summary cache only) |
| Knowledge graph | `data/graph.json` (rebuilt each cycle by `graph_engine.py`) |
| Dashboard cache | `SummaryEngine.get_latest()` — never re-hit the LLM on page reload |

**Astra DB endpoint** is read from the `ASTRA_DB_ENDPOINT` environment variable at runtime. It is never hard-coded. Both `ASTRA_DB_TOKEN` and `ASTRA_DB_ENDPOINT` must be set or `SignalDB()` raises `RuntimeError` on instantiation.

**Rules:**
- All reads/writes go through `SignalDB` in `core/database.py`. Never call Astra DB directly from app code.
- SQLite is legitimate for summary caching only (`SummaryEngine`). Do not use it for signals.
- Any second vector store, ChromaDB, or `@vercel/postgres` for signals is forbidden.
- The `_archive_legacy/` SQLite databases (`signals.db`, `sentinel.db`) are dead. Do not reference them.

---

## AI Layer

**One LLM: HuggingFace InferenceClient (Cerebras provider). One model: `meta-llama/Llama-3.1-8B-Instruct`.**

| Task | Module | How |
|------|--------|-----|
| Score raw article text → Signal | `core/pipeline.py` | `score_text(text)` or `score_and_save(text, db)` |
| Generate BLUF executive summary | `core/summary_engine.py` | `SummaryEngine.generate(...)` with `fallback_fn` |
| Dashboard chat (Inquisition) | `core/agents.py` | `run_agent_query()` via LangGraph multi-agent |
| Knowledge graph update | `core/graph_engine.py` | `run_graph_update(signal)` after each ingestion |

**Rules:**
- Always provide a `fallback_fn` to `SummaryEngine.generate()`. LLM quota errors must never crash the UI.
- The model string is `"meta-llama/Llama-3.1-8B-Instruct"`. Do not change it without testing the Cerebras provider endpoint.
- `LLMScoreResponse` in `core/pipeline.py` is the strict Pydantic validation layer between raw LLM JSON and a `Signal`. Never skip it.
- If `HUGGINGFACEHUB_API_TOKEN` is unset, all LLM calls fall back to rule-based logic — the UI must never crash.
- `InferenceClient` is instantiated inside `_invoke()` in `pipeline.py`. Patch it at the source module: `patch("huggingface_hub.InferenceClient")`.

---

## Frontend Architecture

**Framework: Dash + Dash Bootstrap Components (DBC). Charts: Plotly.**

- `app.py` is the single Dash application: all tabs, callbacks, and layouts live here.

**Rules:**
- All Dash callbacks must be pure functions — no global state mutation inside a callback.
- Use `no_update` to avoid unnecessary re-renders. Never return `None` where a component is expected.
- DBC layout: use `dbc.Container → dbc.Row → dbc.Col` for all grid structure. No ad-hoc `html.Div` grids.
- Plotly figures must have `template="plotly_dark"` and `paper_bgcolor="rgba(0,0,0,0)"` for the dark war-room aesthetic.
- Never block the main thread inside a callback. Heavy work (LLM calls, DB queries) must use `no_update` optimistically and update on a second callback pass, or accept the latency explicitly.

---

## Scraping & Intelligence Pipeline

**Flow:** `sources.py` → `scraper.py` → `pipeline.py` → `database.py` → `graph_engine.py`

```
PESTEL_SOURCES list
    → _scrape_rss() / _scrape_page()             [scraper.py]
    → ScrapedArticle { url, text }
    → score_and_save(text, db)                   [pipeline.py]
    → LLMScoreResponse (Pydantic validation)
    → Signal (validated, UUID, scores)
    → SignalDB.insert()                          [database.py]
    → run_graph_update(signal)                   [graph_engine.py]
```

**Rules:**
- All new sources go in `core/sources.py` in the `PESTEL_SOURCES` list. Never hardcode URLs in scrapers or the scheduler.
- `scrape_mode` must be one of: `"rss"`, `"page"`. Adding a new mode requires a corresponding handler in `scraper.py`.
- Every `ScrapedArticle` must have a non-empty `source_url`. This propagates to `Signal.source_url` — the EU Data Act 2026 provenance requirement.
- All external HTTP calls use `retry_with_backoff` from `core/utils.py`. Never use a bare `requests.get()` without retry logic.
- Inputs shorter than 200 characters are rejected by `_call_llm()` before hitting the LLM.

---

## Scheduler

`core/scheduler.py` runs the Scout cycle every 6 hours via APScheduler.

- Access health state from anywhere: `from core.scheduler import HEALTH, engine`
- `HEALTH` is a module-level dict. Read it; never write to it from outside `scheduler.py`.
- The scheduler starts automatically when `app.py` imports `engine`. Do not call `engine.start()` twice.
- Heartbeat fires every 30 seconds. Do not reduce this interval — it keeps the UI health badge live.

---

## Logging

```python
from core.logger import get_logger
log = get_logger(__name__)
```

- Call `get_logger(__name__)` once at module top-level. Never use `print()` for operational output.
- Logs write to `logs/agent.log` (rotating, 5 MB × 3 backups) and to stderr.
- Override console level with `LOG_LEVEL=DEBUG|INFO|WARNING|ERROR`.
- Never call `logging.basicConfig()` — `core/logger.py` owns root handler configuration.

---

## Development Rules

### Python Standards
- **Python 3.11+**. Use `from __future__ import annotations` in every module.
- **Pydantic v2** for all data models. Use `model_validate()`, not the deprecated `parse_obj()`.
- **Type annotations** on all public functions. Return types are mandatory.
- No bare `except:` clauses. Catch specific exception types.
- Use `Path` (pathlib) for all file paths. No `os.path.join()`.

### Package Boundaries
- `core/` is the domain layer. It must have **zero imports from `app.py`**.
- `app.py` may import from `core/`. It may not import from other app-level files.
- `run_pipeline.py` is a CLI thin wrapper. It imports from `core/` only.
- Never add business logic inside a Dash callback. Callbacks call `core/` functions.

### Environment Variables
| Variable | Required | Purpose |
|----------|----------|---------|
| `HUGGINGFACEHUB_API_TOKEN` | Yes | HuggingFace scoring + summaries + agent chat |
| `ASTRA_DB_TOKEN` | Yes | Astra DB vector store |
| `ASTRA_DB_ENDPOINT` | Yes | Astra DB API endpoint |
| `FIRECRAWL_API_KEY` | Optional | HTML page scraping (falls back to `requests`) |
| `LOG_LEVEL` | Optional | Console log verbosity (default: `INFO`) |

Load via `python-dotenv` at app entry points. Never hardcode keys. Never commit `.env`.

### Testing
- Tests live in `tests/`. Run with `pytest`.
- Test `core/` modules in isolation. Mock `huggingface_hub.InferenceClient` and `astrapy` in unit tests.
- Use `patch("huggingface_hub.InferenceClient")` + `patch("core.pipeline._HF_TOKEN", "fake-token")` to enable the LLM path in tests.
- Astra DB integration tests (those using a live `SignalDB`) must skip automatically when `ASTRA_DB_TOKEN` is not set.
- Do not test Dash callbacks directly — test the underlying `core/` functions they call.

### Repository Hygiene
- Do not create new `.md` files in the repo root. Update `README.md` only.
- `docs/autopsy-architecture.md` is a read-only historical record. Do not modify it.
- `_archive_legacy/` is frozen. No imports, no edits, no additions.
- `data/graph.json` is gitignored. Never commit it.
- `logs/` is gitignored. Never commit log files.

---

## EU Data Act 2026 Compliance

Every `Signal` persisted to Astra DB must have:
1. `source_url` — a valid, non-empty URL pointing to the original article.
2. `content` — minimum 20 characters of synthesised text (not just a headline).
3. No PII — entities are organisation/product names only, never personal names tied to private individuals.

The Critic review is enforced at pipeline validation time via `LLMScoreResponse` and `Signal` Pydantic validators. If either fails, the signal is rejected and logged at `ERROR` — it is never silently dropped.
