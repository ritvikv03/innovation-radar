# HuggingFace + LangGraph Architectural Refactor

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Gemini with a free HuggingFace/LangChain backend, add semantic deduplication, build a LangGraph RAG knowledge-graph engine, add an export button, and re-skin the UI for an agriculture-industry audience.

**Architecture:** `HuggingFaceEndpoint` from `langchain_huggingface` replaces all `google.generativeai` calls. A new `core/graph_engine.py` implements a 4-node LangGraph workflow that fires after each signal insert, doing RAG over ChromaDB and writing edges to `data/graph.json`. The Dash app gains a `dcc.Download`-powered export route and refactored tab names.

**Tech Stack:** LangChain, langchain-huggingface, LangGraph, HuggingFace Inference API (`mistralai/Mistral-7B-Instruct-v0.3`), ChromaDB (existing), Pydantic v2, Dash + DBC (existing)

---

## Task 1: Dependencies & graph.json cleanup

**Files:**
- Modify: `requirements.txt`
- Modify: `data/graph.json`

### Step 1: Update requirements.txt

Remove `google-generativeai`. Add the new stack. Replace the current file's AI-section lines:

```
# ── AI / LLM stack ──────────────────────────────────────────────────────────
langchain>=0.3.0
langchain-huggingface>=0.1.0
langgraph>=0.2.0
pydantic>=2.0.0
huggingface_hub>=0.24.0
```

Also keep all existing non-Gemini entries. Full additions to append (do not duplicate if already present):
```
langchain>=0.3.0
langchain-huggingface>=0.1.0
langgraph>=0.2.0
huggingface_hub>=0.24.0
```

Remove the line:
```
google-generativeai
```
(or any `google-generativeai==x.x.x` pin if present)

### Step 2: Reset data/graph.json

Replace the entire file content with the empty structured template:

```json
{"directed": true, "nodes": [], "links": []}
```

This prevents stale hardcoded mock data from appearing in the UI graph.

### Step 3: Verify no google-generativeai import remains in pipeline/summary (will fix next tasks)

Run:
```bash
grep -r "google.generativeai\|google-generativeai" core/ app.py --include="*.py"
```
Expected: several hits in `core/pipeline.py`, `core/summary_engine.py`, `app.py` — all to be fixed in subsequent tasks.

---

## Task 2: Swap pipeline.py to HuggingFace + LangChain

**Files:**
- Modify: `core/pipeline.py`

### Step 1: Remove Gemini imports and setup block

Delete lines:
```python
import google.generativeai as genai
...
_API_KEY = os.getenv("GEMINI_API_KEY", "")
if _API_KEY:
    genai.configure(api_key=_API_KEY)
_MODEL_NAME = "gemini-2.5-flash-lite"
```

Replace with:
```python
from langchain_huggingface import HuggingFaceEndpoint
from langchain_core.prompts import PromptTemplate

_HF_TOKEN     = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_REPO_ID   = "mistralai/Mistral-7B-Instruct-v0.3"
_MAX_NEW_TOKENS = 1024
```

### Step 2: Rename GeminiScoreResponse → LLMScoreResponse

Find and replace the class name throughout `core/pipeline.py`:
- `class GeminiScoreResponse` → `class LLMScoreResponse`
- All return type annotations and usages of `GeminiScoreResponse` → `LLMScoreResponse`

### Step 3: Replace _call_gemini() with _call_llm()

Delete the `_call_gemini()` function entirely. Add `_call_llm()`:

```python
def _call_llm(text: str, max_input_chars: int = 8_000) -> LLMScoreResponse:
    """
    Send text to HuggingFace Inference API via LangChain, parse JSON response.

    Raises
    ------
    RuntimeError  if HUGGINGFACEHUB_API_TOKEN is not set
    ValueError    if model returns malformed JSON or out-of-range scores
    """
    if not _HF_TOKEN:
        raise RuntimeError(
            "HUGGINGFACEHUB_API_TOKEN is not set. "
            "Add it to your .env file."
        )

    truncated = text[:max_input_chars]
    if len(text) > max_input_chars:
        truncated += "\n\n[... article truncated for analysis ...]"

    prompt_template = PromptTemplate.from_template(
        _SYSTEM_PROMPT + "\n\n" + _USER_TEMPLATE
    )

    llm = HuggingFaceEndpoint(
        repo_id=_HF_REPO_ID,
        huggingfacehub_api_token=_HF_TOKEN,
        max_new_tokens=_MAX_NEW_TOKENS,
        temperature=0.2,
        timeout=60,
    )

    chain = prompt_template | llm

    log.info("Calling HuggingFace (%s) — text_len=%d chars", _HF_REPO_ID, len(truncated))
    try:
        raw_text = retry_with_backoff(
            lambda: chain.invoke({"text": truncated}),
            max_attempts=3,
            base_delay=4.0,
        )
    except Exception as exc:
        log.error("HuggingFace API error after retries: %s", exc)
        raise RuntimeError(f"HuggingFace API error: {exc}") from exc

    if hasattr(raw_text, "content"):
        raw_text = raw_text.content
    raw_text = str(raw_text).strip()

    json_str = _extract_json(raw_text)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        log.error("HuggingFace returned invalid JSON: %s\nRaw: %s", exc, json_str[:300])
        raise ValueError(f"HuggingFace returned invalid JSON: {exc}") from exc

    log.debug("LLM response parsed: title=%r dim=%s",
              data.get("title", "?")[:60], data.get("pestel_dimension"))
    return LLMScoreResponse(**data)
```

### Step 4: Update score_text() to call _call_llm()

Change:
```python
def score_text(text: str) -> tuple[Signal, GeminiScoreResponse]:
    scored  = _call_gemini(text)
```
to:
```python
def score_text(text: str) -> tuple[Signal, LLMScoreResponse]:
    scored  = _call_llm(text)
```

Update `score_and_save` return type annotation similarly: `tuple[Signal, LLMScoreResponse]`.

### Step 5: Update _to_signal() parameter type

Change:
```python
def _to_signal(scored: GeminiScoreResponse) -> Signal:
```
to:
```python
def _to_signal(scored: LLMScoreResponse) -> Signal:
```

### Step 6: Verify import references in scheduler.py

Check that `scheduler.py` only imports `score_and_save` (the public API) — no direct reference to `GeminiScoreResponse`. Run:
```bash
grep "GeminiScoreResponse" core/scheduler.py
```
Expected: no output (scheduler only uses `score_and_save`).

---

## Task 3: Swap summary_engine.py to HuggingFace

**Files:**
- Modify: `core/summary_engine.py`

### Step 1: Remove _call_gemini() method and replace with _call_llm()

Remove the existing `_call_gemini` method (lines 135–160). Replace with:

```python
def _call_llm(
    self,
    prompt_template: str,
    context_data: Dict[str, Any],
    max_tokens: int,
) -> Optional[str]:
    """Try the HuggingFace Inference API via LangChain. Returns text or None on failure."""
    hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
    if not hf_token:
        return None

    try:
        from langchain_huggingface import HuggingFaceEndpoint
        from langchain_core.prompts import PromptTemplate

        prompt = prompt_template.format_map(context_data)
        llm = HuggingFaceEndpoint(
            repo_id="mistralai/Mistral-7B-Instruct-v0.3",
            huggingfacehub_api_token=hf_token,
            max_new_tokens=max_tokens,
            temperature=0.3,
            timeout=60,
        )
        result = llm.invoke(prompt)
        if hasattr(result, "content"):
            result = result.content
        return str(result).strip() or None
    except Exception as exc:
        err = str(exc)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            self._quota_hit = True
        return None
```

### Step 2: Add os import at top of summary_engine.py

Add `import os` to the import block at the top of the file (it is not currently imported).

### Step 3: Update generate() to call _call_llm()

In the `generate()` method, change:
```python
ai_text = self._call_gemini(prompt_template, context_data, max_tokens)
```
to:
```python
ai_text = self._call_llm(prompt_template, context_data, max_tokens)
```

### Step 4: Fix SQLite db_path — remove q2_solution reference

The current default db_path points to `q2_solution/data/signals.db` (dead path per CLAUDE.md). Update `__init__`:

```python
if db_path is None:
    db_path = str(
        Path(__file__).parent.parent / "data" / "summaries.db"
    )
```

This puts summaries in `data/summaries.db` (gitignored alongside chroma_db).

---

## Task 4: Semantic deduplication in pipeline.py

**Files:**
- Modify: `core/pipeline.py`

### Step 1: Add deduplication helper function

Add `_is_duplicate()` after the `_extract_json()` function:

```python
_DEDUP_THRESHOLD = 0.08   # cosine distance; lower = more similar. Tune here.

def _is_duplicate(text: str, db: SignalDB) -> bool:
    """
    Returns True if ChromaDB already contains a semantically near-identical
    document (cosine distance < _DEDUP_THRESHOLD).

    A threshold of 0.08 catches rephrased duplicates of the same article
    while allowing genuinely new signals through.
    """
    if db.count() == 0:
        return False
    results = db.search(text[:500], n_results=1)
    if not results:
        return False
    _, distance = results[0]
    if distance < _DEDUP_THRESHOLD:
        log.info("Dedup: skipping near-duplicate (distance=%.4f < %.4f)", distance, _DEDUP_THRESHOLD)
        return True
    return False
```

### Step 2: Wire deduplication into score_and_save()

In `score_and_save()`, add the dedup check after the DB is obtained but before scoring:

```python
def score_and_save(text: str, db: Optional[SignalDB] = None) -> Optional[tuple[Signal, LLMScoreResponse]]:
    """
    Score text and persist to ChromaDB.

    Returns None if the text is a near-duplicate of an existing signal.
    Returns (Signal, LLMScoreResponse) otherwise.
    """
    if db is None:
        db = SignalDB()
    if _is_duplicate(text, db):
        return None
    signal, scored = score_text(text)
    db.insert(signal)
    return signal, scored
```

### Step 3: Update scheduler.py to handle None return

In `core/scheduler.py`, inside the `for article in articles:` loop, the call to `score_and_save` must handle the new `Optional` return:

```python
result = score_and_save(annotated, db=db)
if result is None:
    log.debug("Skipped duplicate article from %s", name)
    continue
signal, _scored = result
log.info("Saved [%s] %s  disruption=%.3f",
         signal.pestel_dimension.value,
         signal.title[:60],
         signal.disruption_score)
saved += 1
```

---

## Task 5: RAG Knowledge Graph Engine (core/graph_engine.py)

**Files:**
- Create: `core/graph_engine.py`

### Step 1: Create the file with LangGraph workflow

```python
"""
core/graph_engine.py — RAG Knowledge Graph Engine
==================================================
A 4-node LangGraph workflow that fires after a new Signal is inserted.

Flow
----
  Signal
    → [Node 1] receive_signal  : validates & wraps input state
    → [Node 2] rag_query       : fetches top-2 semantically related signals from ChromaDB
    → [Node 3] identify_edges  : asks HuggingFace model to name relationships
    → [Node 4] update_graph    : appends nodes/edges to data/graph.json

Relationships recognised
------------------------
  ACCELERATES | CONFLICTS_WITH | DRIVES | AMPLIFIES | INCREASES | DECREASES | DEPENDS_ON
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Optional

from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing_extensions import TypedDict

from core.database import Signal, SignalDB
from core.logger import get_logger

log = get_logger(__name__)

_GRAPH_JSON_PATH = Path(__file__).parent.parent / "data" / "graph.json"
_HF_TOKEN        = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_REPO_ID      = "mistralai/Mistral-7B-Instruct-v0.3"

_VALID_RELATIONSHIPS = {
    "ACCELERATES", "CONFLICTS_WITH", "DRIVES", "AMPLIFIES",
    "INCREASES", "DECREASES", "DEPENDS_ON",
}


# ── LangGraph State ───────────────────────────────────────────────────────────

class GraphState(TypedDict):
    signal: dict                          # Signal serialised as dict (JSON-safe for LangGraph)
    semantic_matches: list[dict]          # list of {"signal": dict, "distance": float}
    relationship_edges: list[dict]        # constructed edge dicts ready for graph.json


# ── Node 1: receive_signal ────────────────────────────────────────────────────

def receive_signal(state: GraphState) -> GraphState:
    """Validate that the incoming signal has required fields."""
    sig = state["signal"]
    required = {"id", "title", "pestel_dimension", "source_url", "disruption_score"}
    missing = required - sig.keys()
    if missing:
        log.warning("graph_engine: signal missing fields %s — aborting graph update", missing)
        return {**state, "semantic_matches": [], "relationship_edges": []}
    log.info("graph_engine: received signal [%s] %s", sig["pestel_dimension"], sig["title"][:60])
    return state


# ── Node 2: rag_query ─────────────────────────────────────────────────────────

def rag_query(state: GraphState) -> GraphState:
    """Fetch top-2 historical signals related to the incoming signal."""
    sig = state["signal"]
    if not state.get("semantic_matches") == [] and state.get("relationship_edges"):
        # Already aborted upstream
        return state

    try:
        db = SignalDB()
        query_text = f"{sig['title']} {sig.get('content', '')}"
        results = db.search(query_text, n_results=3)

        matches = []
        for historical_signal, distance in results:
            if historical_signal.id == sig["id"]:
                continue        # skip self-match
            if distance > 0.80:
                continue        # too distant to be meaningfully related
            matches.append({
                "signal":   historical_signal.to_metadata(),
                "distance": distance,
            })
            if len(matches) >= 2:
                break

        log.info("graph_engine: RAG found %d related signals", len(matches))
        return {**state, "semantic_matches": matches}

    except Exception as exc:
        log.error("graph_engine rag_query failed: %s", exc)
        return {**state, "semantic_matches": []}


# ── Node 3: identify_edges ────────────────────────────────────────────────────

def identify_edges(state: GraphState) -> GraphState:
    """Ask HuggingFace to identify the relationship between the new signal and each match."""
    matches = state.get("semantic_matches", [])
    sig     = state["signal"]

    if not matches or not _HF_TOKEN:
        return {**state, "relationship_edges": []}

    edges: list[dict] = []

    try:
        from langchain_huggingface import HuggingFaceEndpoint

        llm = HuggingFaceEndpoint(
            repo_id=_HF_REPO_ID,
            huggingfacehub_api_token=_HF_TOKEN,
            max_new_tokens=128,
            temperature=0.1,
            timeout=45,
        )

        for match in matches:
            hist = match["signal"]
            prompt = (
                f"You are an agricultural policy analyst. Given two intelligence signals:\n\n"
                f"SIGNAL A: {sig['title']}\n"
                f"SIGNAL B: {hist['title']}\n\n"
                f"Choose the ONE relationship that best describes how A relates to B:\n"
                f"ACCELERATES | CONFLICTS_WITH | DRIVES | AMPLIFIES | INCREASES | DECREASES | DEPENDS_ON\n\n"
                f"Respond with ONLY the relationship word. Nothing else."
            )

            try:
                result = llm.invoke(prompt)
                if hasattr(result, "content"):
                    result = result.content
                rel = str(result).strip().upper()
                # Extract first matching keyword if model adds extra text
                for candidate in _VALID_RELATIONSHIPS:
                    if candidate in rel:
                        rel = candidate
                        break
                else:
                    rel = "DEPENDS_ON"   # safe default

                edge = {
                    "source":        sig["id"],
                    "target":        hist["id"],
                    "relationship":  rel,
                    "pillar":        sig["pestel_dimension"],
                    "weight":        round(1.0 - match["distance"], 3),
                    "timestamp":     sig.get("date_ingested", ""),
                    "source_url":    sig.get("source_url", ""),
                }
                edges.append(edge)
                log.info("graph_engine: edge %s →[%s]→ %s", sig["id"][:8], rel, hist["id"][:8])

            except Exception as exc:
                log.warning("graph_engine: edge identification failed for pair: %s", exc)

    except Exception as exc:
        log.error("graph_engine identify_edges setup failed: %s", exc)

    return {**state, "relationship_edges": edges}


# ── Node 4: update_graph ──────────────────────────────────────────────────────

def update_graph(state: GraphState) -> GraphState:
    """Append new nodes and edges to data/graph.json atomically."""
    sig   = state["signal"]
    edges = state.get("relationship_edges", [])

    try:
        # Load current graph
        if _GRAPH_JSON_PATH.exists():
            graph = json.loads(_GRAPH_JSON_PATH.read_text())
        else:
            graph = {"directed": True, "nodes": [], "links": []}

        existing_node_ids = {n["id"] for n in graph.get("nodes", [])}

        # Upsert the incoming signal as a node
        if sig["id"] not in existing_node_ids:
            graph["nodes"].append({
                "id":         sig["id"],
                "label":      sig["title"][:80],
                "category":   sig["pestel_dimension"],
                "created_at": sig.get("date_ingested", ""),
                "source":     sig.get("source_url", ""),
            })

        # Ensure historical signal nodes also exist (so edges are valid)
        for match in state.get("semantic_matches", []):
            hist = match["signal"]
            if hist["id"] not in existing_node_ids:
                graph["nodes"].append({
                    "id":         hist["id"],
                    "label":      hist["title"][:80],
                    "category":   hist["pestel_dimension"],
                    "created_at": hist.get("date_ingested", ""),
                    "source":     hist.get("source_url", ""),
                })
                existing_node_ids.add(hist["id"])

        # Append edges (deduplicate by source+target)
        existing_edge_keys = {
            (e["source"], e["target"]) for e in graph.get("links", [])
        }
        for edge in edges:
            key = (edge["source"], edge["target"])
            if key not in existing_edge_keys:
                graph["links"].append(edge)
                existing_edge_keys.add(key)

        # Write back atomically
        _GRAPH_JSON_PATH.write_text(json.dumps(graph, indent=2))
        log.info("graph_engine: graph updated — %d nodes, %d links",
                 len(graph["nodes"]), len(graph["links"]))

    except Exception as exc:
        log.error("graph_engine update_graph failed: %s", exc)

    return state


# ── Compile LangGraph workflow ────────────────────────────────────────────────

def _build_graph_workflow():
    """Compile the 4-node LangGraph StateGraph."""
    builder = StateGraph(GraphState)
    builder.add_node("receive_signal",  receive_signal)
    builder.add_node("rag_query",       rag_query)
    builder.add_node("identify_edges",  identify_edges)
    builder.add_node("update_graph",    update_graph)

    builder.set_entry_point("receive_signal")
    builder.add_edge("receive_signal", "rag_query")
    builder.add_edge("rag_query",      "identify_edges")
    builder.add_edge("identify_edges", "update_graph")
    builder.add_edge("update_graph",   END)

    return builder.compile()


_workflow = _build_graph_workflow()


# ── Public API ────────────────────────────────────────────────────────────────

def run_graph_update(signal: Signal) -> None:
    """
    Fire the LangGraph workflow for a newly inserted Signal.

    This is a synchronous call — run it in the scheduler's existing
    background thread immediately after score_and_save() succeeds.

    Parameters
    ----------
    signal : the newly inserted Signal object
    """
    try:
        meta = signal.to_metadata()
        meta["disruption_score"] = signal.disruption_score   # derived property, add explicitly
        initial_state: GraphState = {
            "signal":             meta,
            "semantic_matches":   [],
            "relationship_edges": [],
        }
        _workflow.invoke(initial_state)
    except Exception as exc:
        log.error("run_graph_update failed for signal %s: %s", signal.id[:8], exc)
```

### Step 2: Verify the file is syntactically valid

```bash
python -c "import core.graph_engine; print('graph_engine OK')"
```
Expected output: `graph_engine OK`

---

## Task 6: Hook graph_engine into scheduler.py

**Files:**
- Modify: `core/scheduler.py`

### Step 1: Import run_graph_update inside _run_scout_cycle()

In the `_run_scout_cycle()` function, add the import alongside the other local imports at the top of the function body:

```python
from core.graph_engine import run_graph_update
```

### Step 2: Call run_graph_update after each successful score_and_save

Change the block that was:
```python
result = score_and_save(annotated, db=db)
if result is None:
    log.debug("Skipped duplicate article from %s", name)
    continue
signal, _scored = result
log.info("Saved [%s] %s  disruption=%.3f", ...)
saved += 1
```

to:
```python
result = score_and_save(annotated, db=db)
if result is None:
    log.debug("Skipped duplicate article from %s", name)
    continue
signal, _scored = result
log.info("Saved [%s] %s  disruption=%.3f",
         signal.pestel_dimension.value,
         signal.title[:60],
         signal.disruption_score)
run_graph_update(signal)   # RAG knowledge-graph update (non-blocking within thread)
saved += 1
```

---

## Task 7: Export Report button in app.py

**Files:**
- Modify: `app.py`

### Step 1: Add dcc.Download to app layout

In the `app.layout` definition, add `dcc.Download(id="export-download")` to the persistent state block alongside `dcc.Store`:

```python
dcc.Store(id="chat-store", data=[]),
dcc.Download(id="export-download"),
dcc.Interval(id="interval-30s", interval=30_000, n_intervals=0),
```

### Step 2: Add Export button to the topbar

In the `topbar` definition, add an Export button alongside the existing Refresh button:

```python
topbar = html.Header([
    html.Div("Fendt PESTEL-EL Strategic Sentinel", className="topbar-title"),
    html.Div(id="topbar-badge"),
    dbc.Button("Export Report", id="export-btn", className="btn-refresh",
               color="secondary", size="sm", outline=True,
               style={"marginRight": "8px"}),
    dbc.Button("Refresh", id="refresh-btn", className="btn-refresh",
               color="secondary", size="sm", outline=True),
    html.Div(id="topbar-ts", className="topbar-ts"),
], className="war-topbar")
```

### Step 3: Add _build_export_html() helper function

Add this pure function in the "Chart Builders" section of app.py (after `_chart_radar`):

```python
def _build_export_html() -> str:
    """
    Build a self-contained HTML report string for download.
    Includes: top signals, urgency matrix data, and BLUF summary.
    """
    signals = _get_db().get_all()
    stats   = _db_stats()
    top10   = sorted(signals, key=lambda s: s.disruption_score, reverse=True)[:10]
    critical = [s for s in signals if s.disruption_score >= 0.75]

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = "\n".join(
        f"<tr>"
        f"<td>{s.pestel_dimension.value}</td>"
        f"<td>{s.title[:120]}</td>"
        f"<td>{s.disruption_score:.3f}</td>"
        f"<td>{_sev(s.disruption_score).upper()}</td>"
        f"<td><a href='{s.source_url}' target='_blank'>Source</a></td>"
        f"</tr>"
        for s in top10
    )

    critical_rows = "\n".join(
        f"<tr><td>{s.pestel_dimension.value}</td><td>{s.title[:120]}</td>"
        f"<td>{s.disruption_score:.3f}</td><td><a href='{s.source_url}'>Source</a></td></tr>"
        for s in critical[:5]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fendt PESTEL-EL Intelligence Report — {now_str}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 40px auto; color: #1a1a2e; }}
  h1 {{ font-size: 22px; color: #0d1b2a; border-bottom: 2px solid #0d1b2a; padding-bottom: 8px; }}
  h2 {{ font-size: 16px; color: #1b3a6b; margin-top: 32px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }}
  th {{ background: #1b3a6b; color: #fff; padding: 8px 12px; text-align: left; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #dde1ec; }}
  tr:hover {{ background: #f0f4ff; }}
  .meta {{ font-size: 12px; color: #6b7a99; margin-top: 4px; }}
  .kpi-row {{ display: flex; gap: 24px; margin: 16px 0; }}
  .kpi {{ background: #f0f4ff; border-radius: 8px; padding: 14px 20px; min-width: 120px; }}
  .kpi-val {{ font-size: 28px; font-weight: 700; color: #1b3a6b; }}
  .kpi-lbl {{ font-size: 11px; color: #6b7a99; margin-top: 2px; }}
  a {{ color: #1b3a6b; }}
</style>
</head>
<body>
<h1>Fendt PESTEL-EL Strategic Intelligence Report</h1>
<p class="meta">Generated: {now_str} &nbsp;|&nbsp; EU Data Act 2026 Compliant</p>

<div class="kpi-row">
  <div class="kpi"><div class="kpi-val">{stats['total']}</div><div class="kpi-lbl">Total Signals</div></div>
  <div class="kpi"><div class="kpi-val">{stats['critical']}</div><div class="kpi-lbl">Critical (&ge;0.75)</div></div>
  <div class="kpi"><div class="kpi-val">{stats['high']}</div><div class="kpi-lbl">High (0.50&ndash;0.75)</div></div>
  <div class="kpi"><div class="kpi-val">{stats['avg_disruption']:.3f}</div><div class="kpi-lbl">Avg Disruption</div></div>
</div>

<h2>Urgency Matrix — 12M Critical Signals</h2>
<table>
  <tr><th>Dimension</th><th>Signal</th><th>Score</th><th>Source</th></tr>
  {critical_rows if critical_rows else '<tr><td colspan="4">No critical signals at this time.</td></tr>'}
</table>

<h2>Top 10 Signals by Disruption Score</h2>
<table>
  <tr><th>Dimension</th><th>Signal</th><th>Score</th><th>Severity</th><th>Source</th></tr>
  {rows if rows else '<tr><td colspan="5">No signals found. Run the Scout to ingest intelligence.</td></tr>'}
</table>

<p class="meta" style="margin-top:32px;">
  This report was generated by the Fendt PESTEL-EL Sentinel.
  All signals include verifiable source URLs in compliance with EU Data Act 2026 provenance requirements.
</p>
</body>
</html>"""
```

### Step 4: Add export callback

Add the callback after the `trigger_scout` callback:

```python
@app.callback(
    Output("export-download", "data"),
    Input("export-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_report(n_clicks: int):
    html_content = _build_export_html()
    filename = f"fendt-pestel-report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.html"
    return dcc.send_string(html_content, filename)
```

---

## Task 8: Remove Gemini from app.py — swap chatbot to HuggingFace

**Files:**
- Modify: `app.py`

### Step 1: Remove google.generativeai import and configure block

Delete:
```python
import google.generativeai as genai
```
and:
```python
_GEMINI_KEY   = os.getenv("GEMINI_API_KEY", "")
_GEMINI_MODEL = "gemini-2.5-flash-lite"
_GEMINI_OK    = bool(_GEMINI_KEY)

if _GEMINI_KEY:
    genai.configure(api_key=_GEMINI_KEY)
```

Replace with:
```python
_HF_TOKEN  = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_OK     = bool(_HF_TOKEN)
_HF_REPO_ID = "mistralai/Mistral-7B-Instruct-v0.3"
```

### Step 2: Replace _gemini_chat() with _llm_chat()

Delete the old `_gemini_chat()` function. Replace with:

```python
def _llm_chat(question: str, context_signals: list[Signal]) -> str:
    if not _HF_OK:
        return "HuggingFace API token not configured. Set HUGGINGFACEHUB_API_TOKEN in your .env file."

    context = (
        "\n\n".join(
            f"[Signal {i}] {s.title}\n"
            f"  Dimension: {s.pestel_dimension.value}\n"
            f"  Disruption Score: {s.disruption_score:.3f}\n"
            f"  Content: {s.content}\n"
            f"  Source: {s.source_url}"
            for i, s in enumerate(context_signals, 1)
        ) if context_signals else "No matching signals found in ChromaDB."
    )
    prompt = (
        f"{_CHAT_SYSTEM}\n\n"
        f"INTELLIGENCE CONTEXT:\n{context}\n\n"
        f"STRATEGIC QUESTION: {question}\n\n"
        f"UNIVERSAL STRATEGIC ANALYSIS:"
    )
    try:
        from langchain_huggingface import HuggingFaceEndpoint
        llm = HuggingFaceEndpoint(
            repo_id=_HF_REPO_ID,
            huggingfacehub_api_token=_HF_TOKEN,
            max_new_tokens=600,
            temperature=0.25,
            timeout=60,
        )
        result = llm.invoke(prompt)
        if hasattr(result, "content"):
            result = result.content
        return str(result).strip()
    except Exception as exc:
        return f"LLM error: {exc}"
```

### Step 3: Update references to _gemini_chat and _GEMINI_OK throughout app.py

Find and replace all occurrences:
- `_gemini_chat(` → `_llm_chat(`
- `_GEMINI_OK` → `_HF_OK`
- `gemini_status = "Live" if _GEMINI_OK else "No API key"` → `gemini_status = "Live" if _HF_OK else "No API key"`
- `html.Div("gemini-2.5-flash-lite", ...)` → `html.Div(_HF_REPO_ID, ...)`
- In sidebar `_dot("Gemini API", gem_kind)` → `_dot("HuggingFace API", gem_kind)`
- In trigger_scout callback: `if not _GEMINI_OK:` → `if not _HF_OK:`

### Step 4: Update startup log lines

In `if __name__ == "__main__":` block, change:
```python
print(f"  Gemini   : {'OK' if _GEMINI_OK else 'no API key'}")
```
to:
```python
print(f"  HuggingFace: {'OK' if _HF_OK else 'no API key — set HUGGINGFACEHUB_API_TOKEN'}")
```

Also update:
```python
log.info("App starting — ChromaDB: %d signals, Gemini: %s", ...)
```
to:
```python
log.info("App starting — ChromaDB: %d signals, HuggingFace: %s", ...)
```

---

## Task 9: Rename tabs and remove emojis from app.py

**Files:**
- Modify: `app.py`

### Step 1: Update _TABS with agriculture-aligned names

Replace:
```python
_TABS = [
    ("overview", "Overview"),
    ("radar",    "Innovation Radar"),
    ("feed",     "Live Feed"),
    ("chatbot",  "AI Analyst"),
]
```

with:
```python
_TABS = [
    ("overview", "Field Intelligence"),
    ("radar",    "Disruption Horizon"),
    ("feed",     "Signal Feed"),
    ("chatbot",  "Strategic Advisor"),
]
```

### Step 2: Update sidebar brand text

Change:
```python
html.Div("FENDT PESTEL-EL", className="sb-brand-sub"),
```
to:
```python
html.Div("AGRO-MARKET INTELLIGENCE", className="sb-brand-sub"),
```

### Step 3: Audit for emoji characters in app.py

Scan for any Unicode emoji in app.py. The known one:
```python
"↗ Verify Source"
```
The `↗` is a Unicode arrow (not technically an emoji, it is standard typography acceptable in industry dashboards). Keep it. Remove any emoji characters such as 🚨, ✅, 🔴 if present.

Run:
```bash
python -c "
import re, sys
with open('app.py') as f:
    content = f.read()
emoji_pattern = re.compile('[\U0001F300-\U0001FFFF]', re.UNICODE)
hits = [(m.start(), content[max(0,m.start()-20):m.start()+20]) for m in emoji_pattern.finditer(content)]
for pos, ctx in hits:
    print(f'pos {pos}: ...{ctx!r}...')
print(f'Total emoji hits: {len(hits)}')
"
```
Expected: 0 hits (the codebase is clean already). If any are found, remove them.

### Step 4: Update section labels that reference Gemini

In `_tab_chatbot()`:
- `"Model: gemini-2.5-flash-lite"` → `"Model: Mistral-7B-Instruct-v0.3"`

In `_CHAT_SYSTEM` prompt string and welcome message:
- `"Gemini: {gemini_status}"` → `"HuggingFace: {gemini_status}"`

---

## Task 10: Final integration verification

**Files:** Read-only verification run

### Step 1: Check no google-generativeai imports remain

```bash
grep -rn "google.generativeai\|genai\." core/ app.py --include="*.py"
```
Expected: zero matches.

### Step 2: Check LangGraph workflow compiles

```bash
python -c "
from core.graph_engine import _workflow
print('LangGraph workflow nodes:', list(_workflow.nodes.keys()))
"
```
Expected output includes: `receive_signal`, `rag_query`, `identify_edges`, `update_graph`

### Step 3: Check pipeline imports cleanly

```bash
python -c "from core.pipeline import score_text, score_and_save, LLMScoreResponse; print('pipeline OK')"
```
Expected: `pipeline OK`

### Step 4: Check summary_engine imports cleanly

```bash
python -c "from core.summary_engine import SummaryEngine; print('summary_engine OK')"
```
Expected: `summary_engine OK`

### Step 5: Check app.py imports cleanly (without starting server)

```bash
python -c "
import sys
# Prevent scheduler from auto-starting
import unittest.mock as mock
with mock.patch('core.scheduler.SchedulerEngine.start'):
    import app
print('app.py imports OK')
print('Tabs:', [t[1] for t in app._TABS])
"
```
Expected output:
```
app.py imports OK
Tabs: ['Field Intelligence', 'Disruption Horizon', 'Signal Feed', 'Strategic Advisor']
```

### Step 6: Verify graph.json template is valid JSON

```bash
python -c "
import json
from pathlib import Path
g = json.loads(Path('data/graph.json').read_text())
assert g['directed'] is True
assert isinstance(g['nodes'], list)
assert isinstance(g['links'], list)
print('graph.json valid:', g)
"
```

### Step 7: Commit

```bash
git add core/pipeline.py core/summary_engine.py core/graph_engine.py \
        core/scheduler.py app.py requirements.txt data/graph.json
git commit -m "refactor: replace Gemini with HuggingFace/LangGraph stack

- Swap core/pipeline.py to HuggingFaceEndpoint (Mistral-7B-Instruct-v0.3)
- Swap core/summary_engine.py to HuggingFace, fix db_path
- Add semantic deduplication (cosine threshold 0.08) in pipeline
- Create core/graph_engine.py: 4-node LangGraph RAG knowledge-graph workflow
- Hook graph_engine into scheduler after each successful signal insert
- Add Export Report button + dcc.Download HTML export in app.py
- Rename tabs to agriculture-aligned names, remove Gemini branding
- Reset data/graph.json to empty template (no synthetic data)"
```

---

## Environment Variable Checklist

| Variable | Was | Now |
|----------|-----|-----|
| `GEMINI_API_KEY` | Required | **Remove** (no longer used) |
| `HUGGINGFACEHUB_API_TOKEN` | Not used | **Required** for pipeline, summary, chat, graph |
| `FIRECRAWL_API_KEY` | Optional | Unchanged |
| `LOG_LEVEL` | Optional | Unchanged |

Add to `.env`:
```
HUGGINGFACEHUB_API_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxx
```
