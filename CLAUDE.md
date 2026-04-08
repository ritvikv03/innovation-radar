# CLAUDE.md — Fendt PESTEL-EL Sentinel: Enterprise Architecture Rules

This is the single source of truth for how this codebase is structured, what each module owns, and how to develop against it correctly.

---

## Strategic Context

The **Fendt PESTEL-EL Sentinel** is a production intelligence platform for AGCO/Fendt. It monitors macro-environmental signals across six PESTEL dimensions, scores them with AI, stores them in a vector database, and presents them in a C-suite Dash dashboard.

---

## Repository Map

```
innovation-radar/
├── app.py                   — Primary Dash app (Gemini chat + Plotly visualisations)
├── app_dash.py              — Premium Dash war-room dashboard (DBC layout)
├── run_pipeline.py          — CLI: score text or URL, persist to ChromaDB
├── run_daily_intelligence.sh — Cron wrapper for scheduled pipeline runs
│
├── core/                    — THE SINGLE SOURCE OF TRUTH for all data + AI logic
│   ├── __init__.py
│   ├── database.py          — ChromaDB façade + Signal Pydantic model
│   ├── pipeline.py          — Gemini scoring pipeline (raw text → Signal)
│   ├── scraper.py           — RSS / HTML / EC Press API scraping
│   ├── sources.py           — PESTEL source registry (single list of URLs)
│   ├── scheduler.py         — APScheduler background engine (6-hour cycle)
│   ├── summary_engine.py    — Gemini summaries with SQLite persistence + fallback
│   ├── logger.py            — Centralised rotating file + console logger
│   └── utils.py             — retry_with_backoff (shared across all modules)
│
├── data/
│   └── chroma_db/           — ChromaDB persistent store (DO NOT manually edit)
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

**The disruption score** is derived from these three sub-scores. No signal is valid without all three.

---

## Storage Architecture

**One vector database. One embedding model. No alternatives.**

| Concern | Solution |
|---------|----------|
| Signal storage | ChromaDB at `data/chroma_db/` |
| Embedding model | `all-MiniLM-L6-v2` via ChromaDB (offline, no API key) |
| Summary persistence | SQLite via `SummaryEngine` (summary cache only) |
| Dashboard cache | `SummaryEngine.get_latest()` — never re-hit Gemini on page reload |

**Rules:**
- All reads/writes go through `SignalDB` in `core/database.py`. Never call ChromaDB directly from app code.
- `@vercel/postgres`, SQLite for signals, or any second vector store are forbidden. ChromaDB is the store.
- The `_archive_legacy/` SQLite databases (`signals.db`, `sentinel.db`) are dead. Do not reference them.

---

## AI Layer

**One LLM: Google Gemini. One model: `gemini-2.5-flash-lite`.**

| Task | Module | How |
|------|--------|-----|
| Score raw article text → Signal | `core/pipeline.py` | `score_text(text)` or `score_and_save(text, db)` |
| Generate BLUF executive summary | `core/summary_engine.py` | `SummaryEngine.generate(...)` with `fallback_fn` |
| Dashboard chat (Inquisition) | `app.py` | Direct `genai` call inside callback |

**Rules:**
- Always provide a `fallback_fn` to `SummaryEngine.generate()`. Gemini quota errors must never crash the UI.
- The Gemini model string is `"gemini-2.5-flash-lite"`. Do not upgrade it without testing quota limits.
- `GeminiScoreResponse` in `core/pipeline.py` is the strict Pydantic validation layer between raw LLM JSON and a `Signal`. Never skip it.
- Never call `genai.configure()` more than once per process. The app-level call in `app.py` is authoritative.

---

## Frontend Architecture

**Framework: Dash + Dash Bootstrap Components (DBC). Charts: Plotly.**

| App | Purpose |
|-----|---------|
| `app.py` | Primary app: signal feed, Gemini chat, radar chart |
| `app_dash.py` | Premium war-room: full DBC layout, DataTable, tabs |

**Rules:**
- All Dash callbacks must be pure functions — no global state mutation inside a callback.
- Use `no_update` to avoid unnecessary re-renders. Never return `None` where a component is expected.
- DBC layout: use `dbc.Container → dbc.Row → dbc.Col` for all grid structure. No ad-hoc `html.Div` grids.
- Plotly figures must have `template="plotly_dark"` and `paper_bgcolor="rgba(0,0,0,0)"` for the dark war-room aesthetic.
- Never block the main thread inside a callback. Heavy work (Gemini calls, DB queries) must use `no_update` optimistically and update on a second callback pass, or accept the latency explicitly.

---

## Scraping & Intelligence Pipeline

**Flow:** `sources.py` → `scraper.py` → `pipeline.py` → `database.py`

```
PESTEL_SOURCES list
    → _scrape_rss() / _scrape_page() / _scrape_ec_press()  [scraper.py]
    → ScrapedArticle { url, text }
    → score_and_save(text, db)                              [pipeline.py]
    → GeminiScoreResponse (Pydantic validation)
    → Signal (validated, UUID, scores)
    → SignalDB.insert()                                     [database.py]
```

**Rules:**
- All new sources go in `core/sources.py` in the `PESTEL_SOURCES` list. Never hardcode URLs in scrapers or the scheduler.
- `scrape_mode` must be one of: `"rss"`, `"page"`, `"api_ec_press"`. Adding a new mode requires a corresponding handler in `scraper.py`.
- Every `ScrapedArticle` must have a non-empty `source_url`. This propagates to `Signal.source_url` — the EU Data Act 2026 provenance requirement.
- All external HTTP calls use `retry_with_backoff` from `core/utils.py`. Never use a bare `requests.get()` without retry logic.

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
- `core/` is the domain layer. It must have **zero imports from `app.py` or `app_dash.py`**.
- `app.py` and `app_dash.py` may import from `core/`. They may not import from each other.
- `run_pipeline.py` is a CLI thin wrapper. It imports from `core/` only.
- Never add business logic inside a Dash callback. Callbacks call `core/` functions.

### Environment Variables
| Variable | Required | Purpose |
|----------|----------|---------|
| `GEMINI_API_KEY` | Yes | Gemini scoring + summaries |
| `FIRECRAWL_API_KEY` | Optional | HTML page scraping (falls back to `requests`) |
| `LOG_LEVEL` | Optional | Console log verbosity (default: `INFO`) |

Load via `python-dotenv` at app entry points. Never hardcode keys. Never commit `.env`.

### Testing
- Tests live in `tests/`. Run with `pytest`.
- Test `core/` modules in isolation. Mock `genai` and ChromaDB in unit tests.
- Do not test Dash callbacks directly — test the underlying `core/` functions they call.

### Repository Hygiene
- Do not create new `.md` files in the repo root. Update `README.md` only.
- `docs/autopsy-architecture.md` is a read-only historical record. Do not modify it.
- `_archive_legacy/` is frozen. No imports, no edits, no additions.
- `data/chroma_db/` is gitignored. Never commit database files.
- `logs/` is gitignored. Never commit log files.

---

## EU Data Act 2026 Compliance

Every `Signal` persisted to ChromaDB must have:
1. `source_url` — a valid, non-empty URL pointing to the original article.
2. `content` — minimum 20 characters of synthesised text (not just a headline).
3. No PII — entities are organisation/product names only, never personal names tied to private individuals.

The Critic review is enforced at pipeline validation time via `GeminiScoreResponse` and `Signal` Pydantic validators. If either fails, the signal is rejected and logged at `ERROR` — it is never silently dropped.
