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
from pathlib import Path

from langgraph.graph import StateGraph, END
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
    aborted: bool                         # True if receive_signal validation failed


# ── Node 1: receive_signal ────────────────────────────────────────────────────

def receive_signal(state: GraphState) -> GraphState:
    """Validate that the incoming signal has required fields."""
    sig = state["signal"]
    required = {"id", "title", "pestel_dimension", "source_url", "disruption_score"}
    missing = required - sig.keys()
    if missing:
        log.warning("graph_engine: signal missing fields %s — aborting graph update", missing)
        return {**state, "semantic_matches": [], "relationship_edges": [], "aborted": True}
    log.info("graph_engine: received signal [%s] %.60s", sig["pestel_dimension"], sig["title"])
    return {**state, "aborted": False}


# ── Node 2: rag_query ─────────────────────────────────────────────────────────

def rag_query(state: GraphState) -> GraphState:
    """Fetch top-2 historical signals related to the incoming signal."""
    sig = state["signal"]

    # If receive_signal validation failed, propagate abort
    if state.get("aborted", False):
        return state

    try:
        db = SignalDB()
        query_text = f"{sig['title']} {sig.get('content', '')}"
        results = db.search(query_text, n_results=3)

        matches: list[dict] = []
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
            max_new_tokens=32,
            temperature=0.1,
            timeout=45,
        )

        for match in matches:
            hist = match["signal"]
            prompt = (
                f"[INST] You are an agricultural policy analyst. Given two intelligence signals:\n\n"
                f"SIGNAL A: {sig['title']}\n"
                f"SIGNAL B: {hist['title']}\n\n"
                f"Choose the ONE relationship word that best describes how A relates to B:\n"
                f"ACCELERATES | CONFLICTS_WITH | DRIVES | AMPLIFIES | INCREASES | DECREASES | DEPENDS_ON\n\n"
                f"Respond with ONLY the relationship word. Nothing else. [/INST]"
            )

            try:
                result = llm.invoke(prompt)
                if hasattr(result, "content"):
                    result = result.content
                if isinstance(result, list):
                    result = " ".join(str(p) for p in result)
                rel = str(result).strip().upper()

                # Extract first matching keyword if model adds extra text
                matched_rel = "DEPENDS_ON"
                for candidate in _VALID_RELATIONSHIPS:
                    if candidate in rel:
                        matched_rel = candidate
                        break

                edge = {
                    "source":       sig["id"],
                    "target":       hist["id"],
                    "relationship": matched_rel,
                    "pillar":       sig["pestel_dimension"],
                    "weight":       round(1.0 - match["distance"], 3),
                    "timestamp":    sig.get("date_ingested", ""),
                    "source_url":   sig.get("source_url", ""),
                }
                edges.append(edge)
                log.info("graph_engine: edge %s →[%s]→ %s",
                         sig["id"][:8], matched_rel, hist["id"][:8])

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

        existing_node_ids: set[str] = {n["id"] for n in graph.get("nodes", [])}

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
        existing_edge_keys: set[tuple[str, str]] = {
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
        meta["disruption_score"] = signal.disruption_score   # derived property
        initial_state: GraphState = {
            "signal":             meta,
            "semantic_matches":   [],
            "relationship_edges": [],
            "aborted":            False,
        }
        _workflow.invoke(initial_state)
    except Exception as exc:
        log.error("run_graph_update failed for signal %s: %s", signal.id[:8], exc)
