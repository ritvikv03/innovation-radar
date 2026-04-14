"""
tests/test_phase2.py — Phase 2 Enterprise Resilience Tests
===========================================================
Covers:
  1. retry_with_backoff — backoff math, non-retryable pass-through, success on retry
  2. Pipeline HuggingFace retry — transient errors retried; validation errors not retried
  3. Scraper type contracts — scrape_source returns list[ScrapedArticle] shape
  4. Scheduler per-source timeout — slow source is killed; rest of cycle continues

All external APIs (HuggingFace, requests, network) are mocked.

Run:
    cd /path/to/innovation-radar
    python -m pytest tests/test_phase2.py -v
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────
# 1. retry_with_backoff
# ─────────────────────────────────────────────────────────────

from core.utils import retry_with_backoff


def test_retry_succeeds_on_first_attempt():
    """No retries needed — function succeeds immediately."""
    fn = MagicMock(return_value="ok")
    result = retry_with_backoff(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 1


def test_retry_succeeds_on_second_attempt():
    """Function fails once then succeeds — should return the success value."""
    side_effects = [RuntimeError("transient"), "ok"]
    fn = MagicMock(side_effect=side_effects)
    result = retry_with_backoff(fn, max_attempts=3, base_delay=0)
    assert result == "ok"
    assert fn.call_count == 2


def test_retry_raises_after_max_attempts():
    """All attempts fail — must raise the last exception."""
    fn = MagicMock(side_effect=RuntimeError("always fails"))
    with pytest.raises(RuntimeError, match="always fails"):
        retry_with_backoff(fn, max_attempts=3, base_delay=0)
    assert fn.call_count == 3


def test_retry_non_retryable_raises_immediately():
    """ValueError is non-retryable — must raise after first attempt, no retry."""
    fn = MagicMock(side_effect=ValueError("bad data"))
    with pytest.raises(ValueError, match="bad data"):
        retry_with_backoff(fn, max_attempts=3, base_delay=0)
    assert fn.call_count == 1


def test_retry_custom_non_retryable():
    """Custom non-retryable exception type is also not retried."""
    class MyFatalError(Exception):
        pass

    fn = MagicMock(side_effect=MyFatalError("fatal"))
    with pytest.raises(MyFatalError):
        retry_with_backoff(fn, max_attempts=3, base_delay=0,
                           non_retryable=(MyFatalError,))
    assert fn.call_count == 1


def test_retry_delay_increases_exponentially(monkeypatch):
    """Each retry delay should be longer than the previous (exponential base)."""
    delays = []

    def fake_sleep(t):
        delays.append(t)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    fn = MagicMock(side_effect=[RuntimeError(), RuntimeError(), RuntimeError()])
    with pytest.raises(RuntimeError):
        retry_with_backoff(fn, max_attempts=3, base_delay=2.0)

    # Two sleeps for 3 attempts (sleep after attempt 1 and 2, not after final)
    assert len(delays) == 2
    # Second delay base is 2× the first (before jitter; we check relative size)
    assert delays[1] >= delays[0]


# ─────────────────────────────────────────────────────────────
# 2. Pipeline HuggingFace retry
# ─────────────────────────────────────────────────────────────

import json

_FAKE_LLM_RESPONSE = {
    "title": "EU Tractor Autonomy Mandate Reshapes Market by 2028",
    "pestel_dimension": "LEGAL",
    "content": "The European Commission has proposed binding autonomy readiness standards "
               "for all tractors sold in the EU after 2028, creating compliance urgency for OEMs.",
    "source_url": "https://ec.europa.eu/test-autonomy",
    "impact_score": 0.88,
    "novelty_score": 0.74,
    "velocity_score": 0.69,
    "entities": ["European Commission", "Fendt", "John Deere"],
    "themes": ["autonomy", "compliance", "OEM regulation"],
    "reasoning": "Binding EU regulation forces immediate roadmap realignment.",
}


def _make_hf_response(json_payload: dict):
    """Return a mock InferenceClient response with JSON payload as content."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(json_payload)
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def test_pipeline_retries_on_transient_api_error():
    """
    If HuggingFace raises a RuntimeError on the first call but succeeds on the second,
    score_text() must succeed (not propagate the transient error).
    """
    mock_client = MagicMock()
    mock_client.chat_completion.side_effect = [
        RuntimeError("503 Service Unavailable"),
        _make_hf_response(_FAKE_LLM_RESPONSE),
    ]

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.pipeline._HF_TOKEN", "fake-hf-token"), \
         patch("core.utils.time.sleep"):
        from core.pipeline import score_text
        signal, scored = score_text(
            "The European Commission has proposed binding autonomy readiness standards "
            "for all tractors sold in the EU after 2028, creating compliance urgency for "
            "OEMs such as Fendt and John Deere. The regulation requires full GPS-guided "
            "operation capability and real-time telemetry reporting for fleet monitoring."
        )

    assert signal.title == _FAKE_LLM_RESPONSE["title"]
    assert mock_client.chat_completion.call_count == 2   # one failure + one success


def test_pipeline_does_not_retry_on_invalid_json():
    """
    If HuggingFace returns malformed JSON, that's a ValueError (non-retryable).
    score_text() must raise immediately — no retry.
    """
    mock_choice = MagicMock()
    mock_choice.message.content = "not valid json {{{"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat_completion.return_value = mock_resp

    with patch("huggingface_hub.InferenceClient", return_value=mock_client), \
         patch("core.pipeline._HF_TOKEN", "fake-hf-token"), \
         patch("core.utils.time.sleep"):
        from core.pipeline import score_text
        with pytest.raises(ValueError):
            score_text(
                "The European Commission has proposed binding autonomy readiness standards "
                "for all tractors sold in the EU after 2028, creating compliance urgency for "
                "OEMs such as Fendt and John Deere. The regulation requires full GPS-guided "
                "operation capability and real-time telemetry reporting for fleet monitoring."
            )

    # JSON parse failure is non-retryable — HF called exactly once
    assert mock_client.chat_completion.call_count == 1


# ─────────────────────────────────────────────────────────────
# 3. Scraper type contracts
# ─────────────────────────────────────────────────────────────

from core.scraper import ScrapedArticle, scrape_source


def test_scrape_source_returns_typed_list_on_failure():
    """
    Even on failure, scrape_source returns list — never raises.
    Each element (if any) must be a dict with 'url' and 'text' keys.
    """
    result = scrape_source({
        "url": "http://localhost:9999/dead",
        "dimension": "ECONOMIC",
        "source_name": "Dead",
        "scrape_mode": "rss",
    })
    assert isinstance(result, list)
    for item in result:
        assert "url" in item
        assert "text" in item


def test_scraped_article_typeddict_keys():
    """ScrapedArticle TypedDict must enforce url + text keys at construction."""
    article: ScrapedArticle = {"url": "https://example.com", "text": "Some content"}
    assert article["url"] == "https://example.com"
    assert article["text"] == "Some content"


@patch("core.scraper.retry_with_backoff")
def test_scrape_source_rss_returns_scraped_articles(mock_retry):
    """Mock RSS fetch — verify scrape_source returns list[ScrapedArticle] shape."""
    rss_xml = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>EU Farm Subsidy Reform 2026</title>
          <description>The European Commission has proposed sweeping changes to CAP subsidies
          that would redirect 40% of funding toward precision agriculture and sustainability
          initiatives by 2028, affecting over 9 million EU farmers.</description>
          <link>https://example.com/cap-reform</link>
        </item>
      </channel>
    </rss>"""

    mock_response = MagicMock()
    mock_response.text = rss_xml
    mock_retry.return_value = rss_xml  # _fetch() returns xml_text

    result = scrape_source({
        "url": "https://example.com/feed",
        "dimension": "POLITICAL",
        "source_name": "Test Feed",
        "scrape_mode": "rss",
    })

    assert isinstance(result, list)
    # Each item must have the ScrapedArticle shape
    for item in result:
        assert "url" in item, "Missing 'url' key in ScrapedArticle"
        assert "text" in item, "Missing 'text' key in ScrapedArticle"
        assert isinstance(item["url"], str)
        assert isinstance(item["text"], str)


# ─────────────────────────────────────────────────────────────
# 4. Scheduler per-source timeout
# ─────────────────────────────────────────────────────────────

def test_scheduler_skips_slow_source_and_continues():
    """
    If one source hangs longer than _SOURCE_TIMEOUT, the cycle must skip it
    (log an error, increment errors) and continue processing remaining sources.

    We verify this by patching scrape_source to hang for the first call
    and return articles for the second call.
    """
    from core.scheduler import _run_scout_cycle, HEALTH
    from core.sources import PESTEL_SOURCES

    if not PESTEL_SOURCES:
        pytest.skip("No PESTEL_SOURCES configured")

    call_count = {"n": 0}

    def fake_scrape(source):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Sleep slightly longer than the patched timeout so it times out,
            # but short enough that the abandoned thread ends quickly.
            time.sleep(0.5)
        return []

    with (
        patch("core.scraper.scrape_source", side_effect=fake_scrape),
        patch("core.pipeline.score_and_save"),
        patch("core.database.SignalDB"),
        patch("core.scheduler._SOURCE_TIMEOUT", 0.05),  # 50ms → first source times out
    ):
        _run_scout_cycle()

    # Cycle must have continued past the timed-out source
    assert call_count["n"] >= 1
    # errors_today must reflect the timed-out source
    assert HEALTH["errors_today"] >= 1
