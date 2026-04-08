"""
tests/test_phase1.py — Phase 1 Integration Tests
=================================================
Tests scheduler health state, scraper resilience, pipeline
validation, and DB persistence. All external APIs (Gemini,
Firecrawl) are mocked so these run fully offline.

Run:
    cd /path/to/innovation-radar
    python -m pytest tests/test_phase1.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─────────────────────────────────────────────────────────────
# 1. Logger
# ─────────────────────────────────────────────────────────────

def test_logger_creates_log_file():
    """Importing get_logger should create logs/agent.log."""
    from core.logger import get_logger, _LOG_FILE
    log = get_logger("test.logger")
    log.info("Phase 1 test run")
    assert _LOG_FILE.exists(), "logs/agent.log must exist after first log call"


def test_logger_returns_named_logger():
    from core.logger import get_logger
    import logging
    log = get_logger("test.named")
    assert isinstance(log, logging.Logger)
    assert log.name == "test.named"


# ─────────────────────────────────────────────────────────────
# 2. Signal model (Pydantic)
# ─────────────────────────────────────────────────────────────

from core.database import PESTELDimension, Signal


def _make_signal(**overrides) -> Signal:
    defaults = dict(
        title="EU Nitrates Directive Mandates GPS Spraying",
        pestel_dimension=PESTELDimension.LEGAL,
        content="The revised EU Nitrates Directive requires precision application systems "
                "on all farms over 50 ha in Nitrate Vulnerable Zones by January 2026.",
        source_url="https://eur-lex.europa.eu/test",
        impact_score=0.82,
        novelty_score=0.71,
        velocity_score=0.65,
    )
    defaults.update(overrides)
    return Signal(**defaults)


def test_signal_valid():
    s = _make_signal()
    assert s.pestel_dimension == PESTELDimension.LEGAL
    assert 0.0 <= s.disruption_score <= 1.0


def test_signal_disruption_formula():
    """disruption_score = Impact×0.5 + Novelty×0.3 + Velocity×0.2"""
    s = _make_signal(impact_score=0.8, novelty_score=0.6, velocity_score=0.4)
    expected = round(0.8 * 0.5 + 0.6 * 0.3 + 0.4 * 0.2, 4)
    assert s.disruption_score == expected


def test_signal_rejects_short_title():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _make_signal(title="Hi")


def test_signal_rejects_score_out_of_range():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _make_signal(impact_score=1.5)


def test_signal_rejects_bad_url():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _make_signal(source_url="not-a-url")


def test_signal_rejects_content_equals_title():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _make_signal(
            title="EU Nitrates Directive Mandates GPS Spraying",
            content="EU Nitrates Directive Mandates GPS Spraying",
        )


def test_signal_metadata_roundtrip():
    """to_metadata() → from_metadata() must reproduce an equal Signal."""
    s = _make_signal(entities=["Fendt", "EU"], themes=["precision", "compliance"])
    meta = s.to_metadata()

    # All metadata values must be primitive types safe for ChromaDB
    for v in meta.values():
        assert isinstance(v, (str, int, float, bool)), f"Non-primitive metadata value: {v!r}"

    restored = Signal.from_metadata(meta)
    assert restored.id == s.id
    assert restored.title == s.title
    assert restored.entities == s.entities
    assert abs(restored.disruption_score - s.disruption_score) < 0.001


# ─────────────────────────────────────────────────────────────
# 3. SignalDB
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    """Isolated ChromaDB instance per test."""
    from core.database import SignalDB
    return SignalDB(db_dir=tmp_path)


def test_db_insert_and_count(tmp_db):
    s = _make_signal()
    tmp_db.insert(s)
    assert tmp_db.count() == 1


def test_db_get_by_id(tmp_db):
    s = _make_signal()
    tmp_db.insert(s)
    fetched = tmp_db.get_by_id(s.id)
    assert fetched is not None
    assert fetched.title == s.title


def test_db_search_returns_results(tmp_db):
    s = _make_signal()
    tmp_db.insert(s)
    results = tmp_db.search("GPS precision farming compliance", n_results=3)
    assert len(results) >= 1
    assert isinstance(results[0][1], float)  # distance is float


def test_db_search_ranking(tmp_db):
    """Top result should be the most semantically similar signal."""
    legal = _make_signal(
        title="EU Nitrates Directive Mandates GPS Spraying",
        pestel_dimension=PESTELDimension.LEGAL,
        content="Legal compliance requirement for precision sprayers in NVZs.",
        source_url="https://eur-lex.europa.eu/legal",
    )
    tech = _make_signal(
        title="CORDIS Grant for Battery Swap Infrastructure on Farms",
        pestel_dimension=PESTELDimension.TECHNOLOGICAL,
        content="EU Horizon Europe grants fund prototype battery-swap stations for tractors.",
        source_url="https://cordis.europa.eu/tech",
        impact_score=0.79, novelty_score=0.91, velocity_score=0.84,
    )
    tmp_db.insert_many([legal, tech])
    results = tmp_db.search("EU legal compliance requirement")
    top_signal, _dist = results[0]
    assert top_signal.pestel_dimension == PESTELDimension.LEGAL


def test_db_upsert_does_not_duplicate(tmp_db):
    s = _make_signal()
    tmp_db.insert(s)
    tmp_db.insert(s)   # same id → upsert
    assert tmp_db.count() == 1


def test_db_clear(tmp_db):
    tmp_db.insert(_make_signal())
    tmp_db.clear()
    assert tmp_db.count() == 0


# ─────────────────────────────────────────────────────────────
# 4. Pipeline (Gemini mocked)
# ─────────────────────────────────────────────────────────────

_FAKE_GEMINI_RESPONSE = {
    "title": "John Deere Autonomous 8R Launches Q3 2026 — Fendt Faces 2-Year Gap",
    "pestel_dimension": "TECHNOLOGICAL",
    "content": "John Deere has announced commercial availability of a fully autonomous "
               "tractor in North America, creating a competitive gap for Fendt whose "
               "autonomy roadmap targets 2028.",
    "source_url": "https://example.com/deere-autonomous",
    "impact_score": 0.90,
    "novelty_score": 0.80,
    "velocity_score": 0.70,
    "severity_score": 0.85,
    "entities": ["John Deere", "Fendt", "AGCO"],
    "themes": ["autonomous tractor", "competitive gap"],
    "reasoning": "First commercial autonomous tractor sets 2-year competitive clock.",
}


def _mock_gemini_response(text_content: str):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(text_content) if isinstance(text_content, dict) else text_content
    return mock_resp


@patch("core.pipeline.genai")
def test_score_text_returns_signal_and_response(mock_genai):
    """score_text() must return (Signal, GeminiScoreResponse) with valid data."""
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response(_FAKE_GEMINI_RESPONSE)
    mock_genai.GenerativeModel.return_value = mock_model
    mock_genai.GenerationConfig = MagicMock()

    # Set the key so pipeline doesn't bail early
    import core.pipeline as pl
    original_key = pl._API_KEY
    pl._API_KEY = "fake-key"

    try:
        from core.pipeline import score_text
        signal, scored = score_text("John Deere launches autonomous tractor in 2026.")
    finally:
        pl._API_KEY = original_key

    assert signal.title == _FAKE_GEMINI_RESPONSE["title"]
    assert signal.pestel_dimension == PESTELDimension.TECHNOLOGICAL
    assert signal.disruption_score > 0
    assert scored.severity_score == 0.85


@patch("core.pipeline.genai")
def test_score_and_save_persists(mock_genai, tmp_db):
    """score_and_save() must write to ChromaDB."""
    mock_model = MagicMock()
    mock_model.generate_content.return_value = _mock_gemini_response(_FAKE_GEMINI_RESPONSE)
    mock_genai.GenerativeModel.return_value = mock_model
    mock_genai.GenerationConfig = MagicMock()

    import core.pipeline as pl
    original_key = pl._API_KEY
    pl._API_KEY = "fake-key"

    try:
        from core.pipeline import score_and_save
        signal, _ = score_and_save("Article text", db=tmp_db)
    finally:
        pl._API_KEY = original_key

    assert tmp_db.count() == 1
    fetched = tmp_db.get_by_id(signal.id)
    assert fetched is not None


# ─────────────────────────────────────────────────────────────
# 5. Scraper resilience
# ─────────────────────────────────────────────────────────────

def test_scraper_returns_empty_on_network_error():
    """scrape_source must return [] on any network failure, not raise."""
    from core.scraper import scrape_source
    bad_source = {
        "url":         "http://localhost:9999/does-not-exist",
        "dimension":   "POLITICAL",
        "source_name": "Dead Server",
        "scrape_mode": "rss",
    }
    result = scrape_source(bad_source)
    assert result == [], "scrape_source must return [] on failure, not raise"


def test_scraper_unknown_mode_returns_empty():
    from core.scraper import scrape_source
    result = scrape_source({
        "url": "http://example.com",
        "dimension": "SOCIAL",
        "source_name": "Test",
        "scrape_mode": "nonexistent_mode",
    })
    assert result == []


# ─────────────────────────────────────────────────────────────
# 6. Scheduler health state
# ─────────────────────────────────────────────────────────────

def test_scheduler_health_defaults():
    """HEALTH dict must be importable and have correct default keys."""
    from core.scheduler import HEALTH
    required = {"scheduler_alive", "scout_running", "last_run_utc",
                "signals_this_run", "total_signals", "errors_today"}
    assert required.issubset(set(HEALTH.keys()))
    assert HEALTH["scheduler_alive"] is False  # not started yet


def test_scheduler_start_sets_alive():
    """After engine.start(), scheduler_alive must be True."""
    from core.scheduler import SchedulerEngine, HEALTH
    eng = SchedulerEngine(interval_hours=24)   # long interval — won't fire
    try:
        eng.start()
        time.sleep(0.5)
        assert eng.running is True
        assert HEALTH["scheduler_alive"] is True
    finally:
        eng.stop()


def test_scheduler_stop_clears_alive():
    from core.scheduler import SchedulerEngine, HEALTH
    eng = SchedulerEngine(interval_hours=24)
    eng.start()
    time.sleep(0.2)
    eng.stop()
    time.sleep(0.2)
    assert eng.running is False
