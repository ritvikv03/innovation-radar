"""
tests/test_graph_engine.py — Graph Engine Tests
================================================
Covers:
  1. _compute_causal_chain — pure-function logic
  2. _build_triple         — output structure
  3. get_causal_chains     — file reading (monkeypatched path)
  4. infer_hidden_relationships — BFS inference
  5. run_graph_update      — mocked DB + InferenceClient

All Astra DB and HuggingFace calls are mocked.

Run:
    python -m pytest tests/test_graph_engine.py -v
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.graph_engine import (
    _build_triple,
    _compute_causal_chain,
    get_causal_chains,
    infer_hidden_relationships,
    run_graph_update,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sig(pillar: str = "POLITICAL", title: str | None = None) -> dict:
    """Minimal signal metadata dict."""
    sig_id = str(uuid.uuid4())
    return {
        "id": sig_id,
        "title": title or f"{pillar} Signal {sig_id[:6]}",
        "pestel_dimension": pillar,
        "source_url": "https://example.com",
        "disruption_score": 0.75,
        "date_ingested": "2026-01-01T00:00:00+00:00",
    }


# ─────────────────────────────────────────────────────────────
# 1. _compute_causal_chain
# ─────────────────────────────────────────────────────────────

def test_causal_chain_no_inbound():
    """No inbound chains → two-element result."""
    chain = _compute_causal_chain(
        subject_id="abc",
        subject_pillar="POLITICAL",
        object_pillar="ECONOMIC",
        existing_triples=[],
    )
    assert chain == ["POLITICAL", "ECONOMIC"]


def test_causal_chain_inherits_longest():
    """Inherits the longest inbound chain and appends object pillar."""
    subject_id = "subject-uuid"
    existing = [
        {
            "object": {"id": subject_id},
            "metadata": {"causal_chain": ["LEGAL", "POLITICAL"]},
        },
        {
            "object": {"id": subject_id},
            "metadata": {"causal_chain": ["LEGAL"]},
        },
    ]
    chain = _compute_causal_chain(
        subject_id=subject_id,
        subject_pillar="POLITICAL",
        object_pillar="ECONOMIC",
        existing_triples=existing,
    )
    assert chain == ["LEGAL", "POLITICAL", "ECONOMIC"]


def test_causal_chain_avoids_duplicate_tail():
    """If inbound chain ends with same pillar as object, no duplicate appended."""
    subject_id = "dup-uuid"
    existing = [
        {
            "object": {"id": subject_id},
            "metadata": {"causal_chain": ["LEGAL", "ECONOMIC"]},
        },
    ]
    chain = _compute_causal_chain(
        subject_id=subject_id,
        subject_pillar="POLITICAL",
        object_pillar="ECONOMIC",   # same as tail of inbound chain
        existing_triples=existing,
    )
    # Should not append ECONOMIC again
    assert chain == ["LEGAL", "ECONOMIC"]


# ─────────────────────────────────────────────────────────────
# 2. _build_triple
# ─────────────────────────────────────────────────────────────

def test_build_triple_structure():
    """_build_triple returns correct keys and id format."""
    sig  = _sig("POLITICAL")
    hist = _sig("ECONOMIC")
    triple = _build_triple(sig, hist, "DRIVES", 0.8, [])

    assert triple["id"] == f"{sig['id'][:8]}_{hist['id'][:8]}"
    assert triple["subject"]["id"] == sig["id"]
    assert triple["object"]["id"] == hist["id"]
    assert triple["predicate"] == "DRIVES"
    assert "causal_chain" in triple["metadata"]
    assert "causal_depth" in triple["metadata"]
    assert "weight" in triple["metadata"]


def test_build_triple_causal_chain_content():
    """Two-pillar chain when no existing triples."""
    sig  = _sig("POLITICAL")
    hist = _sig("ECONOMIC")
    triple = _build_triple(sig, hist, "DRIVES", 0.9, [])
    assert triple["metadata"]["causal_chain"] == ["POLITICAL", "ECONOMIC"]
    assert triple["metadata"]["causal_depth"] == 1


# ─────────────────────────────────────────────────────────────
# 3. get_causal_chains (monkeypatched file path)
# ─────────────────────────────────────────────────────────────

def test_get_causal_chains_missing_file(tmp_path, monkeypatch):
    """Returns [] when graph.json does not exist."""
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    assert get_causal_chains() == []


def test_get_causal_chains_returns_sorted(tmp_path, monkeypatch):
    """Results are sorted by depth descending."""
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    graph = {
        "nodes": [], "links": [],
        "triples": [
            {
                "id": "t1",
                "predicate": "DRIVES",
                "subject": {"label": "A"},
                "object":  {"label": "B"},
                "metadata": {"causal_chain": ["POLITICAL", "ECONOMIC"], "causal_depth": 1},
            },
            {
                "id": "t2",
                "predicate": "DRIVES",
                "subject": {"label": "B"},
                "object":  {"label": "C"},
                "metadata": {"causal_chain": ["POLITICAL", "ECONOMIC", "SOCIAL"], "causal_depth": 2},
            },
        ],
    }
    (tmp_path / "graph.json").write_text(json.dumps(graph))

    chains = get_causal_chains(top_n=10)
    assert len(chains) == 2
    assert chains[0]["depth"] >= chains[1]["depth"]


def test_get_causal_chains_respects_top_n(tmp_path, monkeypatch):
    """top_n parameter is respected."""
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    triples = [
        {
            "id": f"t{i}",
            "predicate": "DRIVES",
            "subject": {"label": f"A{i}"},
            "object":  {"label": f"B{i}"},
            "metadata": {"causal_chain": ["POLITICAL", "ECONOMIC"], "causal_depth": 1},
        }
        for i in range(5)
    ]
    (tmp_path / "graph.json").write_text(json.dumps({"triples": triples}))
    assert len(get_causal_chains(top_n=2)) == 2


# ─────────────────────────────────────────────────────────────
# 4. infer_hidden_relationships
# ─────────────────────────────────────────────────────────────

def test_infer_returns_zero_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    result = infer_hidden_relationships()
    assert result == {"inferred_added": 0, "total_triples": 0}


def test_infer_returns_zero_with_fewer_than_two_triples(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    (tmp_path / "graph.json").write_text(json.dumps({"triples": []}))
    result = infer_hidden_relationships()
    assert result["inferred_added"] == 0


def test_infer_detects_cross_pestel_cascade(tmp_path, monkeypatch):
    """A→B→C cross-PESTEL path produces an inferred triple."""
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    c_id = str(uuid.uuid4())

    triples = [
        {
            "id": "t1",
            "subject": {"id": a_id, "label": "A", "type": "Signal", "pillar": "POLITICAL"},
            "predicate": "DRIVES",
            "object":    {"id": b_id, "label": "B", "type": "Signal", "pillar": "ECONOMIC"},
            "metadata":  {"causal_chain": ["POLITICAL", "ECONOMIC"], "causal_depth": 1},
        },
        {
            "id": "t2",
            "subject": {"id": b_id, "label": "B", "type": "Signal", "pillar": "ECONOMIC"},
            "predicate": "INCREASES",
            "object":    {"id": c_id, "label": "C", "type": "Signal", "pillar": "SOCIAL"},
            "metadata":  {"causal_chain": ["ECONOMIC", "SOCIAL"], "causal_depth": 1},
        },
    ]
    (tmp_path / "graph.json").write_text(json.dumps({"triples": triples}))

    result = infer_hidden_relationships(max_hops=3)
    assert result["inferred_added"] >= 1
    assert result["total_triples"] > 2


def test_infer_skips_same_pestel_pillar(tmp_path, monkeypatch):
    """Paths where start and end share the same PESTEL pillar are skipped."""
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    c_id = str(uuid.uuid4())

    triples = [
        {
            "id": "t1",
            "subject": {"id": a_id, "label": "A", "type": "Signal", "pillar": "POLITICAL"},
            "predicate": "DRIVES",
            "object":    {"id": b_id, "label": "B", "type": "Signal", "pillar": "ECONOMIC"},
            "metadata":  {"causal_chain": ["POLITICAL", "ECONOMIC"], "causal_depth": 1},
        },
        {
            "id": "t2",
            "subject": {"id": b_id, "label": "B", "type": "Signal", "pillar": "ECONOMIC"},
            "predicate": "DRIVES",
            "object":    {"id": c_id, "label": "C", "type": "Signal", "pillar": "POLITICAL"},
            "metadata":  {"causal_chain": ["ECONOMIC", "POLITICAL"], "causal_depth": 1},
        },
    ]
    (tmp_path / "graph.json").write_text(json.dumps({"triples": triples}))

    result = infer_hidden_relationships(max_hops=3)
    # A (POLITICAL) → B → C (POLITICAL) — same start/end pillar, should be skipped
    assert result["inferred_added"] == 0


def test_infer_is_idempotent(tmp_path, monkeypatch):
    """Running inference twice does not add duplicate triples."""
    monkeypatch.setattr(
        "core.graph_engine._GRAPH_JSON_PATH",
        tmp_path / "graph.json",
    )
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    c_id = str(uuid.uuid4())

    triples = [
        {
            "id": "t1",
            "subject": {"id": a_id, "label": "A", "type": "Signal", "pillar": "POLITICAL"},
            "predicate": "DRIVES",
            "object":    {"id": b_id, "label": "B", "type": "Signal", "pillar": "ECONOMIC"},
            "metadata":  {"causal_chain": ["POLITICAL", "ECONOMIC"], "causal_depth": 1},
        },
        {
            "id": "t2",
            "subject": {"id": b_id, "label": "B", "type": "Signal", "pillar": "ECONOMIC"},
            "predicate": "INCREASES",
            "object":    {"id": c_id, "label": "C", "type": "Signal", "pillar": "SOCIAL"},
            "metadata":  {"causal_chain": ["ECONOMIC", "SOCIAL"], "causal_depth": 1},
        },
    ]
    (tmp_path / "graph.json").write_text(json.dumps({"triples": triples}))

    r1 = infer_hidden_relationships()
    r2 = infer_hidden_relationships()
    # Second run must add zero new triples
    assert r2["inferred_added"] == 0
    assert r2["total_triples"] == r1["total_triples"]


# ─────────────────────────────────────────────────────────────
# 5. run_graph_update (mocked DB + InferenceClient)
# ─────────────────────────────────────────────────────────────

def _make_signal_obj():
    """Return a minimal Signal-like object using the real Signal model."""
    from core.database import PESTELDimension, Signal
    return Signal(
        title="EU Tractor Autonomy Regulation 2028 Requires OEM Compliance",
        pestel_dimension=PESTELDimension.LEGAL,
        content="The European Commission has proposed binding autonomy readiness standards "
                "for all tractors sold in the EU after 2028, creating compliance urgency.",
        source_url="https://ec.europa.eu/test",
        impact_score=0.85,
        novelty_score=0.70,
        velocity_score=0.65,
    )


def test_run_graph_update_writes_node(tmp_path, monkeypatch):
    """run_graph_update writes at least one node to graph.json for a valid signal."""
    graph_path = tmp_path / "graph.json"
    monkeypatch.setattr("core.graph_engine._GRAPH_JSON_PATH", graph_path)
    monkeypatch.setattr("core.graph_engine._HF_TOKEN", "fake-hf-token")

    signal = _make_signal_obj()

    # Mock DB: search returns no historical signals (empty graph case)
    mock_db = MagicMock()
    mock_db.search.return_value = []

    with patch("core.graph_engine.SignalDB", return_value=mock_db), \
         patch("huggingface_hub.InferenceClient"):
        run_graph_update(signal)

    assert graph_path.exists()
    graph = json.loads(graph_path.read_text())
    assert any(n["id"] == signal.id for n in graph["nodes"])


def test_run_graph_update_aborts_on_missing_fields(tmp_path, monkeypatch, caplog):
    """If the signal dict is missing required fields, graph stays empty and no error raised."""
    graph_path = tmp_path / "graph.json"
    monkeypatch.setattr("core.graph_engine._GRAPH_JSON_PATH", graph_path)

    # Craft an incomplete signal (no id, title, etc.)
    bad_signal = MagicMock()
    bad_signal.to_metadata.return_value = {}    # empty dict — missing all required fields
    bad_signal.disruption_score = 0.5
    bad_signal.id = "bad-id"

    with patch("core.graph_engine.SignalDB"):
        run_graph_update(bad_signal)   # must not raise
