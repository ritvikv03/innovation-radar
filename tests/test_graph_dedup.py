from __future__ import annotations

import json


def _make_state(sig_id, source_url, title="Test"):
    return {
        "signal": {
            "id": sig_id,
            "title": title,
            "pestel_dimension": "ECONOMIC",
            "date_ingested": "2026-04-22T00:00:00",
            "source_url": source_url,
        },
        "relationship_edges": [],
        "semantic_matches": [],
    }


def test_no_duplicate_source_nodes(tmp_path, monkeypatch):
    from core import graph_engine
    monkeypatch.setattr(graph_engine, "_GRAPH_JSON_PATH", tmp_path / "graph.json")

    graph_engine.update_graph(_make_state("uuid-1", "http://source-a.com"))
    graph_engine.update_graph(_make_state("uuid-2", "http://source-a.com", "Another article"))

    graph = json.loads((tmp_path / "graph.json").read_text())
    sources = [n["source"] for n in graph["nodes"]]
    assert sources.count("http://source-a.com") == 1, "Duplicate source node found"
    assert len(graph["nodes"]) == 1


def test_distinct_sources_each_get_a_node(tmp_path, monkeypatch):
    from core import graph_engine
    monkeypatch.setattr(graph_engine, "_GRAPH_JSON_PATH", tmp_path / "graph.json")

    graph_engine.update_graph(_make_state("uuid-1", "http://source-a.com"))
    graph_engine.update_graph(_make_state("uuid-2", "http://source-b.com"))

    graph = json.loads((tmp_path / "graph.json").read_text())
    assert len(graph["nodes"]) == 2


def test_empty_source_url_not_deduped(tmp_path, monkeypatch):
    """Signals with empty source_url should still be inserted (can't dedup on '')."""
    from core import graph_engine
    monkeypatch.setattr(graph_engine, "_GRAPH_JSON_PATH", tmp_path / "graph.json")

    graph_engine.update_graph(_make_state("uuid-1", ""))
    graph_engine.update_graph(_make_state("uuid-2", ""))

    graph = json.loads((tmp_path / "graph.json").read_text())
    assert len(graph["nodes"]) == 2
