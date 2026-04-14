"""
tests/test_integration_pipeline.py — End-to-End Pipeline Integration Tests
===========================================================================
Mocks both HuggingFace and Astra DB.
Tests the three-stage chain:
  1. score_text(text)       → Signal
  2. SignalDB.insert(signal) → Astra mock called with signal id
  3. run_graph_update(signal) → graph.json contains the node

Run:
    python -m pytest tests/test_integration_pipeline.py -v
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────
# Shared fake LLM response
# ─────────────────────────────────────────────────────────────

_FAKE_LLM_RESPONSE = {
    "title": "EU Tractor Autonomy Mandate Reshapes Agricultural OEM Market by 2028",
    "pestel_dimension": "LEGAL",
    "content": "The European Commission has proposed binding autonomy readiness standards "
               "for all tractors sold in the EU after 2028, creating immediate compliance "
               "urgency for OEMs including Fendt and John Deere.",
    "source_url": "https://ec.europa.eu/test-autonomy",
    "impact_score": 0.88,
    "novelty_score": 0.74,
    "velocity_score": 0.69,
    "entities": ["European Commission", "Fendt", "John Deere"],
    "themes": ["autonomy", "compliance", "OEM regulation"],
    "reasoning": "Binding EU regulation forces immediate roadmap realignment.",
}

_ARTICLE_TEXT = (
    "The European Commission has proposed binding autonomy readiness standards "
    "for all tractors sold in the EU after 2028, creating compliance urgency for "
    "OEMs such as Fendt and John Deere. The regulation requires full GPS-guided "
    "operation capability and real-time telemetry reporting for fleet monitoring."
)


def _make_hf_client(payload: dict):
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat_completion.return_value = mock_resp
    return mock_client


# ─────────────────────────────────────────────────────────────
# Stage 1: score_text
# ─────────────────────────────────────────────────────────────

def test_score_text_returns_valid_signal():
    """score_text returns a Signal with UUID, correct dimension, score in [0,1]."""
    from core.database import PESTELDimension

    mock_client = _make_hf_client(_FAKE_LLM_RESPONSE)

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.pipeline._HF_TOKEN", "fake-hf-token"):
        from core.pipeline import score_text
        signal, scored = score_text(_ARTICLE_TEXT)

    # UUID check
    assert len(signal.id) == 36
    uuid.UUID(signal.id)

    # Dimension
    assert signal.pestel_dimension == PESTELDimension.LEGAL

    # Scores in [0, 1]
    assert 0.0 <= signal.impact_score <= 1.0
    assert 0.0 <= signal.novelty_score <= 1.0
    assert 0.0 <= signal.velocity_score <= 1.0
    assert 0.0 <= signal.disruption_score <= 1.0


# ─────────────────────────────────────────────────────────────
# Stage 2: SignalDB.insert
# ─────────────────────────────────────────────────────────────

def test_score_and_save_calls_db_insert():
    """score_and_save calls SignalDB.insert with the scored signal's id."""
    mock_db = MagicMock()
    mock_db.count.return_value = 0
    mock_db.search.return_value = []

    mock_client = _make_hf_client(_FAKE_LLM_RESPONSE)

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.pipeline._HF_TOKEN", "fake-hf-token"):
        from core.pipeline import score_and_save
        result = score_and_save(_ARTICLE_TEXT, db=mock_db)

    assert result is not None
    signal, _ = result

    mock_db.insert.assert_called_once()
    inserted = mock_db.insert.call_args[0][0]
    assert inserted.id == signal.id


# ─────────────────────────────────────────────────────────────
# Stage 3: run_graph_update
# ─────────────────────────────────────────────────────────────

def test_run_graph_update_adds_node_to_graph_json(tmp_path, monkeypatch):
    """run_graph_update writes the signal as a node in graph.json."""
    monkeypatch.setattr("core.graph_engine._GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr("core.graph_engine._HF_TOKEN", "fake-hf-token")

    # Produce a real Signal via score_text
    mock_client = _make_hf_client(_FAKE_LLM_RESPONSE)

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.pipeline._HF_TOKEN", "fake-hf-token"):
        from core.pipeline import score_text
        signal, _ = score_text(_ARTICLE_TEXT)

    # Mock DB for rag_query (returns no historical signals)
    mock_db = MagicMock()
    mock_db.search.return_value = []

    with patch("core.graph_engine.SignalDB", return_value=mock_db), \
         patch("huggingface_hub.InferenceClient"):
        from core.graph_engine import run_graph_update
        run_graph_update(signal)

    graph_path = tmp_path / "graph.json"
    assert graph_path.exists()
    graph = json.loads(graph_path.read_text())
    node_ids = {n["id"] for n in graph["nodes"]}
    assert signal.id in node_ids


# ─────────────────────────────────────────────────────────────
# End-to-end: all three stages chained
# ─────────────────────────────────────────────────────────────

def test_end_to_end_pipeline(tmp_path, monkeypatch):
    """
    Full chain: score_text → insert → run_graph_update.
    Verifies graph node category matches signal's PESTEL dimension.
    """
    monkeypatch.setattr("core.graph_engine._GRAPH_JSON_PATH", tmp_path / "graph.json")
    monkeypatch.setattr("core.graph_engine._HF_TOKEN", "fake-hf-token")

    # Stage 1 + 2
    mock_db = MagicMock()
    mock_db.count.return_value = 0
    mock_db.search.return_value = []

    mock_client = _make_hf_client(_FAKE_LLM_RESPONSE)

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.pipeline._HF_TOKEN", "fake-hf-token"):
        from core.pipeline import score_and_save
        result = score_and_save(_ARTICLE_TEXT, db=mock_db)

    assert result is not None
    signal, _ = result
    mock_db.insert.assert_called_once()

    # Stage 3
    mock_graph_db = MagicMock()
    mock_graph_db.search.return_value = []

    with patch("core.graph_engine.SignalDB", return_value=mock_graph_db), \
         patch("huggingface_hub.InferenceClient"):
        from core.graph_engine import run_graph_update
        run_graph_update(signal)

    graph = json.loads((tmp_path / "graph.json").read_text())
    node = next((n for n in graph["nodes"] if n["id"] == signal.id), None)
    assert node is not None
    assert node["category"] == signal.pestel_dimension.value
