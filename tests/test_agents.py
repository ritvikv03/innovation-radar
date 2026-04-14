"""
tests/test_agents.py — Multi-Agent System Tests
================================================
Covers:
  1. dict_to_string         — pure-function serialisation
  2. Calculator tools       — pure-function aggregation
  3. Router routing logic   — mocked _hf_chat
  4. run_agent_query        — end-to-end with mocked InferenceClient

All HuggingFace calls are mocked.

Run:
    python -m pytest tests/test_agents.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agents import (
    _tool_average_score,
    _tool_count_by_dimension,
    _tool_score_distribution,
    _tool_top_signals,
    dict_to_string,
    run_agent_query,
)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sigs(n: int = 4) -> list[dict]:
    """Return n minimal signal dicts for testing."""
    dims = ["POLITICAL", "ECONOMIC", "SOCIAL", "TECHNOLOGICAL", "ENVIRONMENTAL", "LEGAL"]
    return [
        {
            "id": f"sig-{i}",
            "title": f"Signal {i} — some longer title for testing purposes",
            "pestel_dimension": dims[i % len(dims)],
            "disruption_score": round(0.5 + i * 0.08, 2),
            "content": f"Content for signal {i}.",
        }
        for i in range(n)
    ]


# ─────────────────────────────────────────────────────────────
# 1. dict_to_string
# ─────────────────────────────────────────────────────────────

def test_dict_to_string_flat_dict():
    result = dict_to_string({"key": "value", "number": 42})
    assert "Key: value" in result
    assert "Number: 42" in result


def test_dict_to_string_nested_dict():
    data = {"outer": {"inner": "deep"}}
    result = dict_to_string(data)
    assert "Outer:" in result
    assert "Inner: deep" in result


def test_dict_to_string_list_of_dicts():
    data = [{"title": "A"}, {"title": "B"}]
    result = dict_to_string(data)
    assert "Title: A" in result
    assert "Title: B" in result


def test_dict_to_string_empty_list():
    result = dict_to_string([])
    assert "(none)" in result


def test_dict_to_string_deep_nesting_no_recursion_error():
    # Build deeply nested dict — should not RecursionError
    d: dict = {}
    cursor = d
    for _ in range(15):
        cursor["child"] = {}
        cursor = cursor["child"]
    result = dict_to_string(d)  # must not raise
    assert isinstance(result, str)


def test_dict_to_string_float_precision():
    result = dict_to_string({"score": 0.12345678})
    assert "0.1235" in result   # rounded to 4dp


# ─────────────────────────────────────────────────────────────
# 2. Calculator tools
# ─────────────────────────────────────────────────────────────

def test_tool_average_score_all():
    sigs = _sigs(4)
    result = _tool_average_score(sigs)
    assert "Average disruption score" in result
    assert "Signals analysed: 4" in result


def test_tool_average_score_dimension_filter():
    sigs = [
        {"pestel_dimension": "POLITICAL", "disruption_score": 0.8},
        {"pestel_dimension": "POLITICAL", "disruption_score": 0.6},
        {"pestel_dimension": "ECONOMIC",  "disruption_score": 0.4},
    ]
    result = _tool_average_score(sigs, dimension="POLITICAL")
    assert "Signals analysed: 2" in result
    assert "0.700" in result   # mean of 0.8 and 0.6


def test_tool_average_score_empty_dimension():
    sigs = _sigs(3)
    result = _tool_average_score(sigs, dimension="ENVIRONMENTAL")
    assert "No signals found" in result


def test_tool_count_by_dimension():
    sigs = [
        {"pestel_dimension": "POLITICAL"},
        {"pestel_dimension": "POLITICAL"},
        {"pestel_dimension": "ECONOMIC"},
    ]
    result = _tool_count_by_dimension(sigs)
    assert "Total signals: 3" in result
    assert "POLITICAL" in result
    assert "ECONOMIC" in result


def test_tool_count_by_dimension_empty():
    result = _tool_count_by_dimension([])
    assert "No signals" in result


def test_tool_top_signals_ordering():
    sigs = [
        {"title": "Low",  "pestel_dimension": "POLITICAL", "disruption_score": 0.3},
        {"title": "High", "pestel_dimension": "ECONOMIC",  "disruption_score": 0.9},
        {"title": "Mid",  "pestel_dimension": "SOCIAL",    "disruption_score": 0.6},
    ]
    result = _tool_top_signals(sigs, n=3)
    lines = result.splitlines()
    # First ranked result should contain the highest score
    first_ranked = lines[1]
    assert "High" in first_ranked or "0.900" in first_ranked


def test_tool_top_signals_empty():
    result = _tool_top_signals([], n=5)
    assert "No signals" in result


def test_tool_score_distribution_buckets():
    sigs = [
        {"title": "Critical", "disruption_score": 0.90},
        {"title": "High",     "disruption_score": 0.70},
        {"title": "Medium",   "disruption_score": 0.55},
        {"title": "Low",      "disruption_score": 0.30},
    ]
    result = _tool_score_distribution(sigs)
    assert "CRITICAL" in result
    assert "HIGH" in result
    assert "MEDIUM" in result
    assert "LOW" in result


# ─────────────────────────────────────────────────────────────
# 3. Router routing (mocked _hf_chat)
# ─────────────────────────────────────────────────────────────

def test_router_routes_to_quantitative():
    with patch("core.agents._hf_chat", return_value="QUANTITATIVE"), \
         patch("core.agents._HF_TOKEN", "fake-token"):
        from core.agents import router_node, AgentState
        state: AgentState = {
            "question": "What is the average disruption score?",
            "signals": [],
            "route": "unknown",
            "tool_result": "",
            "final_answer": "",
            "agent_trace": [],
            "confidence": "medium",
        }
        result = router_node(state)
    assert result["route"] == "quantitative"
    assert "router" in result["agent_trace"]


def test_router_routes_to_synthesis():
    with patch("core.agents._hf_chat", return_value="SYNTHESIS"), \
         patch("core.agents._HF_TOKEN", "fake-token"):
        from core.agents import router_node, AgentState
        state: AgentState = {
            "question": "What are the strategic implications of EU autonomy regulations?",
            "signals": [],
            "route": "unknown",
            "tool_result": "",
            "final_answer": "",
            "agent_trace": [],
            "confidence": "medium",
        }
        result = router_node(state)
    assert result["route"] == "synthesis"


def test_router_falls_back_on_missing_token():
    with patch("core.agents._HF_TOKEN", ""):
        from core.agents import router_node, AgentState
        state: AgentState = {
            "question": "Any question",
            "signals": [],
            "route": "unknown",
            "tool_result": "",
            "final_answer": "",
            "agent_trace": [],
            "confidence": "medium",
        }
        result = router_node(state)
    assert result["route"] == "synthesis"


def test_router_falls_back_on_hf_error():
    with patch("core.agents._hf_chat", side_effect=RuntimeError("500")), \
         patch("core.agents._HF_TOKEN", "fake-token"):
        from core.agents import router_node, AgentState
        state: AgentState = {
            "question": "Any question",
            "signals": [],
            "route": "unknown",
            "tool_result": "",
            "final_answer": "",
            "agent_trace": [],
            "confidence": "medium",
        }
        result = router_node(state)
    assert result["route"] == "synthesis"


# ─────────────────────────────────────────────────────────────
# 4. run_agent_query — end-to-end (mocked InferenceClient)
# ─────────────────────────────────────────────────────────────

def _mock_hf_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def test_run_agent_query_quantitative_route():
    """Quantitative route: agent_trace contains 'router' + 'calculator'."""
    call_responses = [
        "QUANTITATIVE",                                 # router response
        json.dumps({"tool": "count_by_dimension"}),     # tool selector
        "There are 4 signals distributed across...",    # narration
    ]
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = [
        _mock_hf_response(r) for r in call_responses
    ]

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.agents._HF_TOKEN", "fake-token"):
        result = run_agent_query("How many signals per dimension?", _sigs(4))

    assert "router" in result["agent_trace"]
    assert "calculator" in result["agent_trace"]
    assert "final_answer" in result
    assert "tool_result" in result


def test_run_agent_query_synthesis_route():
    """Synthesis route: agent_trace contains 'router' + 'analyst'."""
    call_responses = [
        "SYNTHESIS",
        "The key strategic implication is...",
    ]
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = [
        _mock_hf_response(r) for r in call_responses
    ]

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.agents._HF_TOKEN", "fake-token"):
        result = run_agent_query("What are the strategic implications?", _sigs(4))

    assert "router" in result["agent_trace"]
    assert "analyst" in result["agent_trace"]


def test_run_agent_query_missing_token():
    """Without token, final_answer contains guidance about the API token."""
    with patch("core.agents._HF_TOKEN", ""):
        result = run_agent_query("Any question?", _sigs(2))

    assert "HUGGINGFACEHUB_API_TOKEN" in result["final_answer"]


def test_run_agent_query_returns_all_required_keys():
    """Result dict always has all required keys."""
    with patch("core.agents._HF_TOKEN", ""):
        result = run_agent_query("question", [])

    required = {"final_answer", "route", "agent_trace", "confidence", "tool_result"}
    assert required.issubset(set(result.keys()))
