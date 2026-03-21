# Architectural Autopsy: Fendt PESTEL-EL Sentinel
**Phase 1 of 4 — Findings & Target State**
*Principal Staff Engineer Review · 2026-03-09*

---

## Executive Summary

The repository contains **five critical architectural defects** that, taken together, mean the system as documented cannot run end-to-end in production. The "autonomous daily intelligence pipeline" described in `README.md` does not exist as executable code. The AI backend is split across three incompatible providers (Claude Code CLI, Google Gemini, pure Python) with no abstraction. Two separate storage systems run in parallel and are invisible to each other. The dashboard renders a live product illusion built on a data island that has no automated feed.

These are not style issues. They are structural failures that must be resolved before any feature work has lasting value.

---

## Section 1: The Five Critical Defects

### Defect 1 — `sentinel.py` Does Not Exist (BLOCKER)

**What the README promises:**
```bash
python sentinel.py --run-once          # Full Scout → Analyst → Critic → Writer pipeline
python sentinel.py --agent scout       # Run single agent
python sentinel.py --autonomous 24     # Autonomous 24-hour loop
```

**What exists in the repo:** No `sentinel.py`. The `.github/workflows/sentinel.yml` GitHub Action that is supposed to run this daily is therefore **broken at the entry point**. The system has no automated execution path.

**Impact:** Every call-to-action in `README.md` and `QUICKSTART.md` is broken. The entire "autonomous" claim is false.

---

### Defect 2 — Dual Pipeline, Dual Storage (CRITICAL COUPLING)

The codebase contains two complete, parallel implementations of the same system that **never communicate**:

| Layer | Generation 1 (Legacy) | Generation 2 (Current) |
|-------|-----------------------|------------------------|
| Pipeline | `q2_solution/q2_pipeline.py` | `q2_solution/pipeline.py` |
| Storage | `q2_solution/database.py` (`SignalDatabase`) | `q2_solution/storage.py` (`SignalStore`) |
| Models | Raw `Dict` objects | Pydantic `RawSignal`, `ScoredSignal` |
| Agents | Direct component calls | `ClassifierAgent`, `EvaluatorAgent` |

**The fatal consequence:** `pipeline.py` (Generation 2) persists signals into `JSONSignalStore` (a flat JSON file). `dashboard.py` reads from `database.py` (Generation 1 SQLite). **A signal processed by the new pipeline is completely invisible to the dashboard.** The two systems share no data.

`database.py` contains the critical temporal velocity calculation. `storage.py` has an abstract `SQLiteSignalStore` class that does NOT implement velocity and is not used by the dashboard. They are two separate SQLite implementations solving the same problem differently.

---

### Defect 3 — Three AI Systems with No Abstraction (CRITICAL COUPLING)

The platform uses three separate AI execution environments with zero shared abstraction:

```
┌─────────────────────────────────────────────────────────────┐
│  SYSTEM 1: Claude Code CLI Agents (.claude/agents/*.md)     │
│  → Scout, Analyst, Critic, Writer, Router                   │
│  → Uses Anthropic Claude via OAuth/API                      │
│  → Tools: Firecrawl MCP, Tavily MCP                         │
│  → Output: JSON files in raw_ingest/                        │
│  → HOW IT RUNS: Human invokes `claude` CLI manually         │
└─────────────────────────────────────────────────────────────┘
         ↓ NO AUTOMATED CONNECTION ↓
┌─────────────────────────────────────────────────────────────┐
│  SYSTEM 2: Python Processing Pipeline (q2_solution/)        │
│  → ClassifierAgent, EvaluatorAgent, SynthesisAgent          │
│  → ZERO LLM CALLS — pure deterministic keyword matching     │
│  → Named "agents" but are Python class wrappers             │
│  → Output: SQLite DB, JSON files                            │
└─────────────────────────────────────────────────────────────┘
         ↓ NO AUTOMATED CONNECTION ↓
┌─────────────────────────────────────────────────────────────┐
│  SYSTEM 3: Dashboard AI (dashboard.py)                      │
│  → BLUF Narrative, Inquisition chat                         │
│  → Uses Google Gemini (gemini-2.5-flash)                    │
│  → Completely separate from both above                      │
└─────────────────────────────────────────────────────────────┘
```

There is no event-driven connection, no message queue, no file watcher, and no scheduled job linking these three systems. The `raw_ingest/` JSON files (Scout output) are never automatically fed into the Python pipeline. The Python pipeline output is never automatically served to the dashboard.

**Side effect:** `q2_solution/agents.py` contains `ClassifierAgent`, `EvaluatorAgent`, `SynthesisAgent` — all named "agents" but none make a single LLM call. They are pure Python wrappers around keyword-matching and arithmetic. This naming creates a false mental model for every developer reading the code.

---

### Defect 4 — API Keys Exposed in Tracked Files (SECURITY)

The `.env` file contains three live API keys with no evidence of rotation policy:

```
FIRECRAWL_API_KEY=fc-4976...     # Live web scraping key
TAVILY_API_KEY=tvly-dev-2L8a...  # Live search key
GEMINI_API_KEY=AIzaSy...         # Live LLM inference key
```

**Additional exposures:**
- The dashboard loads Gemini API key via `os.getenv("GEMINI_API_KEY")` and passes it directly to `genai.configure(api_key=api_key)` on every chat turn — the key lives in Python process memory for the lifetime of the Streamlit worker
- `ANTHROPIC_API_KEY` is commented out in `.env` with a placeholder comment explaining how to uncomment it — this is documentation-as-code for secret management
- No key rotation schedule, no least-privilege scoping, no environment-specific keys (dev vs prod share the same credentials)

**The `.env` must not be committed to version control and all three keys above must be rotated immediately.**

---

### Defect 5 — SQLite Without WAL Mode or Connection Safety (DATA INTEGRITY)

`database.py` opens SQLite connections without enabling WAL (Write-Ahead Logging) mode:

```python
def _get_connection(self):
    conn = sqlite3.connect(self.db_path)   # Default journal mode: DELETE
    conn.row_factory = sqlite3.Row
    return conn
```

**Consequences:**
1. **Concurrent read/write contention**: Streamlit dashboard reads and pipeline writes are exclusive. Dashboard users see `database is locked` errors during pipeline execution.
2. **No connection timeout**: `sqlite3.connect()` with no `timeout` parameter defaults to 5 seconds before raising `OperationalError`, surfacing as a dashboard crash.
3. **No context manager enforcement**: Connections are opened in `_get_connection()` but callers are responsible for closing them. A crash mid-query leaks the connection.

---

## Section 2: Additional Structural Problems

### 2.1 Output Directory Proliferation

Four separate output directories with inconsistent ownership:

| Directory | Owner | Contains |
|-----------|-------|---------|
| `/output/` | Legacy (unused) | `briefs/`, `frameworks/` — empty |
| `/outputs/` | Dashboard reader | `reports/sample_rd_alignment_brief.md` |
| `/q2_solution/outputs/` | Q2 Pipeline writer | Charts, scored signals JSON, reports |
| `/q2_solution/test_outputs/` | Test suite | Test artifacts |

The dashboard's Tab 6 reads from `/outputs/reports/`. The pipeline writes to `/q2_solution/outputs/reports/`. They are different directories. **Reports generated by the pipeline are never displayed by the dashboard.**

### 2.2 `graph_utils.py` Module Placement

The Knowledge Graph engine lives at `/graph_utils.py` (repo root). All other business logic is in `/q2_solution/`. The dashboard adds `q2_solution/` to `sys.path`, meaning it cannot import `graph_utils` through that path. The Knowledge Graph tab in the dashboard reads `./data/graph.json` directly via `json.load()` instead of using `graph_utils.py` — bypassing all validation, entity resolution, and decay logic.

### 2.3 Vendored Frontend Libraries in Repository

`/lib/` contains:
- `vis-9.1.2/vis-network.min.js` + CSS (Pyvis dependency)
- `tom-select/` JS + CSS
- `bindings/utils.js`

These are `pip install pyvis` artifacts checked directly into git. They bloat the repository and will conflict when pyvis is upgraded.

### 2.4 Non-Deterministic Radar Positioning

`innovation_radar.py:create_radar()` uses `random.uniform()` without a seed for signal placement. Every dashboard refresh moves every signal dot to a different position. For a C-suite strategic tool, this is disorienting — signals appear to change position between meetings.

```python
import random  # ← import inside loop (anti-pattern)
angle = random.uniform(quad_config['angle_start'] + 5, quad_config['angle_end'] - 5)
```

### 2.5 Inquisition Chat History is Unbounded

`st.session_state.inquisition_messages` grows without limit. Each Gemini API call sends the full conversation history. At 20 turns, a typical strategic session sends ~15,000 tokens of context per message. Token costs grow quadratically. No maximum conversation length is enforced.

### 2.6 `dashboard.py` is 1,206 Lines with No Component Boundaries

All 6 tabs, all caching logic, all Gemini API calls, and all state management coexist in a single file. There are no separation-of-concerns boundaries. A change to the Inquisition chat requires reading past the full radar tab, signal feed, and knowledge graph implementations.

### 2.7 `sentinel.py` Reference in `.github/workflows/sentinel.yml`

The GitHub Actions workflow calls `python sentinel.py --run-once`. This job has been silently failing (or never been tested) since the file does not exist. Every CI run of this workflow produces an unhandled `FileNotFoundError`.

---

## Section 3: What Is Actually Working

These components are correct and should be preserved:

| Component | Assessment |
|-----------|-----------|
| `database.py` temporal velocity formula | Mathematically sound; the momentum calculation is the core innovation |
| `graph_utils.py` provenance validation | Correctly enforces EU Data Act 2026 requirements |
| `graph_utils.py` temporal decay (90-day half-life) | Correct exponential decay implementation |
| `models.py` Pydantic schemas | Well-defined; `RawSignal → ClassifiedSignal → ScoredSignal` chain is clean |
| `.claude/agents/` definitions | Scout, Analyst, Critic, Writer are well-specified with correct tool declarations |
| Phase 2 scorer fixes | Temporal urgency, INNOVATION pillar, novelty fingerprint, tie-breaking (all from Phase 2) |
| `PESTEL_COLORS` constant | Clean single-source-of-truth after Phase 3 |
| Test suite (38 tests) | All passing; solid foundation for Phase 3 expansion |

---

## Section 4: Target Architecture

The target state resolves all five critical defects with minimal new code:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ENTRY POINT: sentinel.py                     │
│                                                                 │
│  --run-once:  invoke Scout → Router → PESTEL Analysts →         │
│               Analyst → Critic → process → Writer               │
│  --dashboard: streamlit run dashboard/app.py                    │
│  --score:     pipe text through cli_scorer.py                   │
└─────────────────────────────────────────────────────────────────┘
         ↓ raw_ingest/*.json (provenance-validated)
┌─────────────────────────────────────────────────────────────────┐
│              PROCESSING LAYER (q2_solution/)                    │
│                                                                 │
│  signal_classifier.py  →  disruption_scorer.py                 │
│  ↓                         ↓                                    │
│  [models.py Pydantic types at every boundary]                   │
│  ↓                                                              │
│  database.py (SINGLE storage — SQLite + WAL mode)              │
│  ↓                                                              │
│  strategic_report_generator.py → outputs/reports/              │
└─────────────────────────────────────────────────────────────────┘
         ↓ reads same database.py
┌─────────────────────────────────────────────────────────────────┐
│              DASHBOARD (dashboard/)                             │
│                                                                 │
│  app.py (entry point, page config, sidebar)                     │
│  pages/tab_executive.py                                         │
│  pages/tab_radar.py                                             │
│  pages/tab_feed.py                                              │
│  pages/tab_inquisition.py                                       │
│  pages/tab_graph.py                                             │
│  pages/tab_reports.py                                           │
│  components/empty_state.py, metric_card.py                      │
│  state.py (session state management)                            │
│  ai_client.py (LLM abstraction — swap Gemini ↔ Claude)         │
└─────────────────────────────────────────────────────────────────┘
````

### Key Architectural Decisions

**Decision 1: Retire `pipeline.py`, `storage.py`, and `q2_pipeline.py` as pipeline entry points.**
`sentinel.py` becomes the single orchestrator. It calls `signal_classifier.py` and `disruption_scorer.py` directly (the tested, working components) and persists into `database.py` (the dashboard-facing store). `pipeline.py` and `storage.py` are deleted. `q2_pipeline.py` is retired (but kept for demo mode).

**Decision 2: Keep SQLite, enable WAL mode.**
SQLite with WAL mode handles the concurrency requirements (one writer, multiple dashboard readers) and costs zero infrastructure. PostgreSQL is not needed at this signal volume (<10,000 signals). Neo4j is not needed because the Knowledge Graph is sparse and graph algorithms are not the primary access pattern. The recommendation is to add `PRAGMA journal_mode=WAL` and connection timeout in `_get_connection()`.

**Decision 3: Abstract the LLM client.**
Create `dashboard/ai_client.py` with a single `generate(prompt: str) -> str` interface. Swap the provider (Gemini → Claude Haiku) without touching tab code. This also makes the API key a single configuration point.

**Decision 4: `graph_utils.py` moves to `q2_solution/`.**
Consolidate all business logic under one importable package root. Dashboard imports via `from q2_solution.graph_utils import update_graph`.

**Decision 5: Deterministic radar via hash-based positioning.**
Replace `random.uniform()` with a position derived from `hash(signal_title) % sector_width`. Same signal = same position across all renders.

---

## Section 5: Immediate Security Actions Required

These must happen before any code changes, independently of the refactor:

1. **Rotate all three API keys** in `.env` — they have been read by an exploration process and may be in logs
2. **Confirm `.env` is in `.gitignore`** — verify `git status` shows `.env` as untracked, not staged
3. **Add `.env.example`** with placeholder values for all required keys (already partially done)
4. **Add `ANTHROPIC_API_KEY` to `.env.example`** as a required (not commented-out) key
5. **Enable `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`** in `_get_connection()` before the next write to the database

---

## Section 6: File Deletion Candidates (Phase 3 Preview)

These files have been superseded and should be deleted (detailed justification in `autopsy-purification.md`):

| File | Reason |
|------|--------|
| `q2_solution/pipeline.py` | Superseded by `sentinel.py` + direct component calls |
| `q2_solution/storage.py` | Superseded by `database.py`; the abstraction was never wired to the dashboard |
| `q2_solution/q2_pipeline.py` | Superseded; demo functionality can be a CLI flag on `sentinel.py` |
| `q2_solution/verify_installation.py` | Ad-hoc verification script; should be a pytest fixture |
| `/output/` (directory) | Legacy; empty; confusingly named alongside `/outputs/` |
| `lib/` (directory) | Vendored Pyvis assets; should not be in git |
| `PHASE2_VERIFICATION.sh` | One-time verification script; content belongs in `pytest` |
| `PHASE4_QUICK_TEST.sh` | Same |
| `run_daily_intelligence.sh` | Superseded by `sentinel.py --run-once` |

---

## Appendix: Severity Matrix

| Finding | Severity | Effort to Fix |
|---------|----------|--------------|
| `sentinel.py` missing — no automated pipeline | CRITICAL | Medium (2-3 days) |
| Dual pipeline/storage — dashboard data island | CRITICAL | Medium (1-2 days) |
| Three AI systems, no abstraction | CRITICAL | Low (1 day) |
| Live API keys in `.env` | HIGH | Immediate (minutes) |
| SQLite without WAL mode | HIGH | Low (10 lines) |
| Output directory proliferation | HIGH | Low (rename + symlink) |
| `graph_utils.py` at repo root | MEDIUM | Low (move + update imports) |
| Non-deterministic radar | MEDIUM | Low (hash-based position) |
| Unbounded chat history | MEDIUM | Low (slice to last N turns) |
| `dashboard.py` monolith (1,206 lines) | MEDIUM | High (Phase 4 scope) |
| Python "agents" naming confusion | LOW | Low (rename to `processors`) |
| Vendored `lib/` assets in git | LOW | Low (add to `.gitignore`) |

---

*Next: `/docs/autopsy-methodology.md` — agentic rigor, structured outputs, scoring math hardening.*
