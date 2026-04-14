"""
tests/test_summary_engine.py — Summary Engine Tests
====================================================
Covers:
  1. SummaryEngine.generate() — LLM path, fallback, quota guard
  2. SummaryEngine.get_latest() — empty DB, most-recent ordering
  3. generate_brief_markdown() — rule-based fallback, dict inputs, empty list

All HuggingFace calls are mocked. SQLite uses tmp_path.

Run:
    python -m pytest tests/test_summary_engine.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.summary_engine import SummaryEngine, generate_brief_markdown


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _engine(tmp_path: Path, use_case_id: str = "test-case") -> SummaryEngine:
    return SummaryEngine(use_case_id=use_case_id, db_path=str(tmp_path / "summaries.db"))


def _mock_hf_response(content: str):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def _fallback(ctx: dict) -> str:
    return f"Rule-based: {ctx.get('total', 0)} signals."


# ─────────────────────────────────────────────────────────────
# 1. SummaryEngine.generate()
# ─────────────────────────────────────────────────────────────

def test_generate_falls_back_when_no_token(tmp_path):
    """Without HUGGINGFACEHUB_API_TOKEN, falls back to fallback_fn."""
    engine = _engine(tmp_path)
    with patch.dict("os.environ", {}, clear=False):
        # Ensure token is absent
        import os
        os.environ.pop("HUGGINGFACEHUB_API_TOKEN", None)

        text, source = engine.generate(
            context_data={"total": 5},
            prompt_template="Summarize {total} signals.",
            fallback_fn=_fallback,
        )
    assert source == "rule_based"
    assert "5" in text


def test_generate_uses_llm_when_token_set(tmp_path):
    """With a valid token, LLM result is returned."""
    engine = _engine(tmp_path)
    mock_client = MagicMock()
    mock_client.chat_completion.return_value = _mock_hf_response("AI summary text.")

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch.dict("os.environ", {"HUGGINGFACEHUB_API_TOKEN": "fake-token"}):
        text, source = engine.generate(
            context_data={"total": 3},
            prompt_template="Summarize {total} signals.",
            fallback_fn=_fallback,
        )

    assert source == "ai"
    assert "AI summary" in text


def test_generate_falls_back_on_llm_exception(tmp_path):
    """LLM exception → falls back gracefully without raising."""
    engine = _engine(tmp_path)
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = RuntimeError("500 Internal Server Error")

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch.dict("os.environ", {"HUGGINGFACEHUB_API_TOKEN": "fake-token"}):
        text, source = engine.generate(
            context_data={"total": 2},
            prompt_template="Summarize {total} signals.",
            fallback_fn=_fallback,
        )

    assert source == "rule_based"
    assert "2" in text


def test_generate_sets_quota_hit_on_429(tmp_path):
    """429 error sets _quota_hit=True and short-circuits second call."""
    engine = _engine(tmp_path)
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = Exception("Error 429: rate limit exceeded")

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch.dict("os.environ", {"HUGGINGFACEHUB_API_TOKEN": "fake-token"}):
        engine.generate(
            context_data={"total": 1},
            prompt_template="Summarize {total} signals.",
            fallback_fn=_fallback,
        )
        assert engine._quota_hit is True

        # Second call — LLM should NOT be called again
        mock_client.chat_completion.reset_mock()
        engine.generate(
            context_data={"total": 2},
            prompt_template="Summarize {total} signals.",
            fallback_fn=_fallback,
        )
        mock_client.chat_completion.assert_not_called()


def test_generate_returns_no_data_message_on_empty_context(tmp_path):
    """Empty context_data returns the no-data message."""
    engine = _engine(tmp_path)
    text, source = engine.generate(
        context_data={},
        prompt_template="Summarize {total} signals.",
        fallback_fn=_fallback,
    )
    assert source == "rule_based"
    assert "No data available" in text


def test_generate_swallows_fallback_exceptions(tmp_path):
    """If fallback_fn itself raises, the no-data message is returned."""
    engine = _engine(tmp_path)

    def bad_fallback(ctx: dict) -> str:
        raise ValueError("fallback exploded")

    import os
    os.environ.pop("HUGGINGFACEHUB_API_TOKEN", None)
    text, source = engine.generate(
        context_data={"total": 1},
        prompt_template="Summarize {total} signals.",
        fallback_fn=bad_fallback,
    )
    assert source == "rule_based"
    assert isinstance(text, str)


# ─────────────────────────────────────────────────────────────
# 2. SummaryEngine.get_latest()
# ─────────────────────────────────────────────────────────────

def test_get_latest_returns_none_when_empty(tmp_path):
    engine = _engine(tmp_path)
    assert engine.get_latest() is None


def test_get_latest_returns_most_recent(tmp_path):
    """Multiple generate calls — get_latest returns the last one."""
    engine = _engine(tmp_path)
    import os
    os.environ.pop("HUGGINGFACEHUB_API_TOKEN", None)

    engine.generate(
        context_data={"total": 1},
        prompt_template="{total}",
        fallback_fn=lambda c: "first",
    )
    engine.generate(
        context_data={"total": 2},
        prompt_template="{total}",
        fallback_fn=lambda c: "second",
    )
    latest = engine.get_latest()
    assert latest == "second"


# ─────────────────────────────────────────────────────────────
# 3. generate_brief_markdown()
# ─────────────────────────────────────────────────────────────

def test_generate_brief_rule_based_no_token():
    """No token → rule-based brief with correct headers."""
    import os
    os.environ.pop("HUGGINGFACEHUB_API_TOKEN", None)

    signals = [
        {"title": "EU CAP Subsidy Reform 2026", "pestel_dimension": "POLITICAL",
         "content": "Major reform redirecting 40% of CAP funds.", "disruption_score": 0.82},
        {"title": "Precision Ag Robot Launch", "pestel_dimension": "TECHNOLOGICAL",
         "content": "New autonomous spraying robot from Fendt.", "disruption_score": 0.75},
    ]
    result = generate_brief_markdown(signals)

    assert "## Executive Summary" in result
    assert "EU CAP Subsidy Reform 2026" in result


def test_generate_brief_accepts_dicts():
    """Accepts plain dicts (not only Signal objects)."""
    import os
    os.environ.pop("HUGGINGFACEHUB_API_TOKEN", None)

    signals = [
        {"title": "Signal Alpha", "pestel_dimension": "ECONOMIC",
         "content": "Economic analysis content.", "disruption_score": 0.65},
    ]
    result = generate_brief_markdown(signals)
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_brief_empty_list():
    """Empty signals list returns a non-empty string without raising."""
    import os
    os.environ.pop("HUGGINGFACEHUB_API_TOKEN", None)

    result = generate_brief_markdown([])
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_brief_uses_llm_when_available():
    """With token set, LLM output is returned."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "## Executive Summary\nLLM-generated brief."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat_completion.return_value = mock_resp

    signals = [
        {"title": "Test Signal", "pestel_dimension": "LEGAL",
         "content": "Some legal content for testing.", "disruption_score": 0.78},
    ]

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch.dict("os.environ", {"HUGGINGFACEHUB_API_TOKEN": "fake-token"}):
        result = generate_brief_markdown(signals)

    assert "LLM-generated brief" in result
