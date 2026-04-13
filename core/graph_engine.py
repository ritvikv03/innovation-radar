"""
core/graph_engine.py — RAG Knowledge Graph Engine (Triples Ontology)
=====================================================================
A 4-node LangGraph workflow that fires after a new Signal is inserted.

Flow
----
  Signal
    → [Node 1] receive_signal  : validates & wraps input state
    → [Node 2] rag_query       : fetches top-2 semantically related signals from Astra DB
    → [Node 3] identify_edges  : asks HuggingFace model to name relationships
    → [Node 4] update_graph    : writes SPO triples + nodes/links to data/graph.json

Graph schema (schema_version=2)
--------------------------------
  nodes   — [{id, label, category, ...}]  ← Cytoscape-compatible
  links   — [{source, target, relationship, weight, ...}]  ← Cytoscape-compatible
  triples — [{id, subject:{}, predicate, object:{}, metadata:{causal_chain,causal_depth}}]

Causal Chain Tracking
---------------------
  Each triple carries a causal_chain: an ordered list of PESTEL pillars
  tracing how a disruption in one dimension cascades through the network.

  Example:
    A (POLITICAL) → DRIVES → B (ECONOMIC)   chain: [POLITICAL, ECONOMIC]
    B (ECONOMIC)  → INCREASES → C (SOCIAL)  chain: [POLITICAL, ECONOMIC, SOCIAL]

  When a new edge sig → hist is added, the engine checks whether sig is
  already the subject of inbound triples (i.e., something caused sig) and
  inherits the longest such chain, extending it by hist's pillar.

Relationships recognised
------------------------
  ACCELERATES | CONFLICTS_WITH | DRIVES | AMPLIFIES | INCREASES | DECREASES | DEPENDS_ON
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from core.database import Signal, SignalDB
from core.logger import get_logger

log = get_logger(__name__)

_GRAPH_JSON_PATH = Path(__file__).parent.parent / "data" / "graph.json"
_HF_TOKEN        = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_REPO_ID      = "meta-llama/Llama-3.2-3B-Instruct"
_SCHEMA_VERSION  = 2

_VALID_RELATIONSHIPS = {
    "ACCELERATES", "CONFLICTS_WITH", "DRIVES", "AMPLIFIES",
    "INCREASES", "DECREASES", "DEPENDS_ON",
}


# ── Label helper ─────────────────────────────────────────────────────────────

def _short(title: str) -> str:
    """Truncate title to 35 chars for graph node labels."""
    return title[:35] + "..." if len(title) > 35 else title


# ── Causal chain helpers ──────────────────────────────────────────────────────

def _compute_causal_chain(
    subject_id: str,
    subject_pillar: str,
    object_pillar: str,
    existing_triples: list[dict],
) -> list[str]:
    """
    Derive the causal chain for a new triple (subject → object).

    Looks up triples where `subject_id` appears as the object (i.e., what
    was already causing the subject signal).  If found, inherits the
    longest such chain and extends it with `object_pillar`.

    Otherwise returns a two-node chain [subject_pillar, object_pillar].

    Parameters
    ----------
    subject_id      : UUID of the new edge's subject signal
    subject_pillar  : PESTEL dimension of subject
    object_pillar   : PESTEL dimension of object
    existing_triples: all triples already in graph.json
    """
    # Triples where subject_id is the *object* — meaning someone caused it
    inbound_chains = [
        t.get("metadata", {}).get("causal_chain", [])
        for t in existing_triples
        if t.get("object", {}).get("id") == subject_id
    ]
    if not inbound_chains:
        return [subject_pillar, object_pillar]

    # Inherit the longest incoming chain (deepest causal history)
    longest = max(inbound_chains, key=len)
    # Avoid duplicate consecutive pillars in the chain
    if longest and longest[-1] == object_pillar:
        return longest
    return list(longest) + [object_pillar]


def _build_triple(
    sig: dict,
    hist: dict,
    relationship: str,
    weight: float,
    existing_triples: list[dict],
) -> dict:
    """
    Construct a full SPO triple with causal chain metadata.

    Parameters
    ----------
    sig      : new signal metadata dict (subject)
    hist     : historical signal metadata dict (object)
    relationship : PESTEL relationship predicate
    weight   : edge weight (1.0 − cosine distance)
    existing_triples : current triples for causal chain lookup
    """
    chain = _compute_causal_chain(
        subject_id=sig["id"],
        subject_pillar=sig.get("pestel_dimension", "UNKNOWN"),
        object_pillar=hist.get("pestel_dimension", "UNKNOWN"),
        existing_triples=existing_triples,
    )
    # Remove consecutive duplicate pillars for clean display
    deduped_chain: list[str] = []
    for pillar in chain:
        if not deduped_chain or deduped_chain[-1] != pillar:
            deduped_chain.append(pillar)

    return {
        "id":        f"{sig['id'][:8]}_{hist['id'][:8]}",
        "subject": {
            "id":     sig["id"],
            "label":  _short(sig.get("title", sig["id"])),
            "type":   "Signal",
            "pillar": sig.get("pestel_dimension", "UNKNOWN"),
        },
        "predicate": relationship,
        "object": {
            "id":     hist["id"],
            "label":  _short(hist.get("title", hist["id"])),
            "type":   "Signal",
            "pillar": hist.get("pestel_dimension", "UNKNOWN"),
        },
        "metadata": {
            "weight":        round(weight, 3),
            "timestamp":     sig.get("date_ingested", ""),
            "source_url":    sig.get("source_url", ""),
            "causal_chain":  deduped_chain,
            "causal_depth":  max(0, len(deduped_chain) - 1),
        },
    }


# ── LangGraph State ───────────────────────────────────────────────────────────

class GraphState(TypedDict):
    signal: dict                          # Signal serialised as dict
    semantic_matches: list[dict]          # list of {"signal": dict, "distance": float}
    relationship_edges: list[dict]        # constructed edge dicts ready for graph.json
    aborted: bool                         # True if receive_signal validation failed


# ── Node 1: receive_signal ────────────────────────────────────────────────────

def receive_signal(state: GraphState) -> GraphState:
    """Validate that the incoming signal has required fields."""
    sig      = state["signal"]
    required = {"id", "title", "pestel_dimension", "source_url", "disruption_score"}
    missing  = required - sig.keys()
    if missing:
        log.warning("graph_engine: signal missing fields %s — aborting", missing)
        return {**state, "semantic_matches": [], "relationship_edges": [], "aborted": True}
    log.info("graph_engine: received signal [%s] %.60s",
             sig["pestel_dimension"], sig["title"])
    return {**state, "aborted": False}


# ── Node 2: rag_query ─────────────────────────────────────────────────────────

def rag_query(state: GraphState) -> GraphState:
    """Fetch top-2 historical signals related to the incoming signal via Astra DB."""
    if state.get("aborted", False):
        return state

    sig = state["signal"]
    try:
        db         = SignalDB()
        query_text = f"{sig['title']} {sig.get('content', '')}"
        results    = db.search(query_text, n_results=3)

        matches: list[dict] = []
        for historical_signal, distance in results:
            if historical_signal.id == sig["id"]:
                continue
            if distance > 0.80:
                continue
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
        from huggingface_hub import InferenceClient
        client = InferenceClient(api_key=_HF_TOKEN)

        for match in matches:
            hist     = match["signal"]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an agricultural policy analyst. "
                        "Respond with ONLY a single relationship word from the list. "
                        "No explanation, no punctuation — just the word."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Signal A: {sig['title']}\n"
                        f"Signal B: {hist['title']}\n\n"
                        f"Choose ONE: ACCELERATES | CONFLICTS_WITH | DRIVES | AMPLIFIES | "
                        f"INCREASES | DECREASES | DEPENDS_ON"
                    ),
                },
            ]

            try:
                response = client.chat_completion(
                    model=_HF_REPO_ID,
                    messages=messages,
                    max_tokens=16,
                    temperature=0.1,
                )
                raw_rel = response.choices[0].message.content.strip().upper()

                matched_rel = "DEPENDS_ON"
                for candidate in _VALID_RELATIONSHIPS:
                    if candidate in raw_rel:
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
                    # carry signal metadata for triple construction
                    "_sig":         sig,
                    "_hist":        hist,
                }
                edges.append(edge)
                log.info(
                    "graph_engine: edge %s →[%s]→ %s",
                    sig["id"][:8], matched_rel, hist["id"][:8],
                )

            except Exception as exc:
                log.warning("graph_engine: edge identification failed: %s", exc)

    except Exception as exc:
        log.error("graph_engine identify_edges setup failed: %s", exc)

    return {**state, "relationship_edges": edges}


# ── Node 4: update_graph ──────────────────────────────────────────────────────

def update_graph(state: GraphState) -> GraphState:
    """
    Write nodes, links (Cytoscape-compatible) and SPO triples to graph.json.

    - Existing schema_version=1 files are migrated transparently by
      adding the `triples` key and bumping schema_version to 2.
    - Causal chains are computed by inspecting existing triples so that
      multi-hop cascades accumulate automatically over time.
    """
    sig   = state["signal"]
    edges = state.get("relationship_edges", [])

    try:
        # ── Load current graph ────────────────────────────────────────────────
        if _GRAPH_JSON_PATH.exists():
            graph = json.loads(_GRAPH_JSON_PATH.read_text())
        else:
            graph = {"directed": True, "nodes": [], "links": [], "triples": []}

        # Migrate legacy schema_version=1 (no triples key)
        if "triples" not in graph:
            graph["triples"] = []
        graph["schema_version"] = _SCHEMA_VERSION

        existing_node_ids: set[str]        = {n["id"] for n in graph.get("nodes", [])}
        existing_edge_keys: set[tuple]     = {
            (e["source"], e["target"]) for e in graph.get("links", [])
        }
        existing_triple_ids: set[str]      = {t["id"] for t in graph["triples"]}
        existing_triples: list[dict]       = graph["triples"]

        # ── Upsert incoming signal as a node ──────────────────────────────────
        if sig["id"] not in existing_node_ids:
            graph["nodes"].append({
                "id":         sig["id"],
                "label":      _short(sig.get("title", sig["id"])),
                "category":   sig["pestel_dimension"],
                "created_at": sig.get("date_ingested", ""),
                "source":     sig.get("source_url", ""),
            })
            existing_node_ids.add(sig["id"])

        # ── Ensure historical signal nodes exist ──────────────────────────────
        for match in state.get("semantic_matches", []):
            hist = match["signal"]
            if hist["id"] not in existing_node_ids:
                graph["nodes"].append({
                    "id":         hist["id"],
                    "label":      _short(hist.get("title", hist["id"])),
                    "category":   hist["pestel_dimension"],
                    "created_at": hist.get("date_ingested", ""),
                    "source":     hist.get("source_url", ""),
                })
                existing_node_ids.add(hist["id"])

        # ── Write edges (links + triples) ─────────────────────────────────────
        for edge in edges:
            key       = (edge["source"], edge["target"])
            sig_meta  = edge.pop("_sig", sig)
            hist_meta = edge.pop("_hist", {})

            # Cytoscape-compatible link (backward-compat)
            if key not in existing_edge_keys:
                graph["links"].append({
                    "source":       edge["source"],
                    "target":       edge["target"],
                    "relationship": edge["relationship"],
                    "pillar":       edge.get("pillar", ""),
                    "weight":       edge["weight"],
                    "timestamp":    edge.get("timestamp", ""),
                    "source_url":   edge.get("source_url", ""),
                })
                existing_edge_keys.add(key)

            # SPO triple with causal chain
            triple     = _build_triple(
                sig=sig_meta,
                hist=hist_meta,
                relationship=edge["relationship"],
                weight=edge["weight"],
                existing_triples=existing_triples,
            )
            if triple["id"] not in existing_triple_ids:
                graph["triples"].append(triple)
                existing_triple_ids.add(triple["id"])
                log.info(
                    "graph_engine: triple %s →[%s]→ %s  chain=%s",
                    triple["subject"]["pillar"],
                    triple["predicate"],
                    triple["object"]["pillar"],
                    " → ".join(triple["metadata"]["causal_chain"]),
                )

        # ── Persist ───────────────────────────────────────────────────────────
        _GRAPH_JSON_PATH.write_text(json.dumps(graph, indent=2))
        log.info(
            "graph_engine: updated — %d nodes, %d links, %d triples",
            len(graph["nodes"]), len(graph["links"]), len(graph["triples"]),
        )

    except Exception as exc:
        log.error("graph_engine update_graph failed: %s", exc)

    return state


# ── Compile LangGraph workflow ────────────────────────────────────────────────

def _build_graph_workflow():
    builder = StateGraph(GraphState)
    builder.add_node("receive_signal", receive_signal)
    builder.add_node("rag_query",      rag_query)
    builder.add_node("identify_edges", identify_edges)
    builder.add_node("update_graph",   update_graph)

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

    Synchronous — runs in the scheduler's background thread immediately
    after score_and_save() succeeds.
    """
    try:
        meta = signal.to_metadata()
        meta["disruption_score"] = signal.disruption_score
        initial_state: GraphState = {
            "signal":             meta,
            "semantic_matches":   [],
            "relationship_edges": [],
            "aborted":            False,
        }
        _workflow.invoke(initial_state)
    except Exception as exc:
        log.error("run_graph_update failed for signal %s: %s", signal.id[:8], exc)


def get_causal_chains(top_n: int = 10) -> list[dict]:
    """
    Return the top-N longest causal chains from the current graph.json.

    Useful for dashboard display of cascade paths.

    Returns
    -------
    List of dicts with keys: chain (list[str]), depth (int), triple_id (str)
    """
    if not _GRAPH_JSON_PATH.exists():
        return []
    try:
        graph   = json.loads(_GRAPH_JSON_PATH.read_text())
        triples = graph.get("triples", [])
        chains  = [
            {
                "triple_id": t["id"],
                "chain":     t["metadata"].get("causal_chain", []),
                "depth":     t["metadata"].get("causal_depth", 0),
                "predicate": t.get("predicate", ""),
                "subject":   t.get("subject", {}).get("label", ""),
                "object":    t.get("object", {}).get("label", ""),
            }
            for t in triples
            if t.get("metadata", {}).get("causal_depth", 0) > 0
        ]
        return sorted(chains, key=lambda c: c["depth"], reverse=True)[:top_n]
    except Exception as exc:
        log.warning("get_causal_chains: %s", exc)
        return []
