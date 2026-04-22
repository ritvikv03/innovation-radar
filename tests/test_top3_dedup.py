from __future__ import annotations

from types import SimpleNamespace


def _pick_top3_distinct_sources(signals):
    """Pick top-3 highest-scoring signals with distinct source_url."""
    sorted_sigs = sorted(signals, key=lambda s: s.disruption_score, reverse=True)
    top3, seen = [], set()
    for s in sorted_sigs:
        if s.source_url not in seen:
            seen.add(s.source_url)
            top3.append(s)
        if len(top3) == 3:
            break
    return top3


def _sig(score, url):
    return SimpleNamespace(disruption_score=score, source_url=url)


def test_dedup_picks_distinct_sources():
    signals = [
        _sig(0.9, "http://a.com"),
        _sig(0.85, "http://a.com"),
        _sig(0.8, "http://b.com"),
        _sig(0.7, "http://c.com"),
    ]
    result = _pick_top3_distinct_sources(signals)
    assert len(result) == 3
    assert [s.source_url for s in result] == ["http://a.com", "http://b.com", "http://c.com"]


def test_dedup_fewer_than_3_unique_sources():
    signals = [_sig(0.9, "http://a.com"), _sig(0.8, "http://a.com")]
    result = _pick_top3_distinct_sources(signals)
    assert len(result) == 1


def test_dedup_empty():
    assert _pick_top3_distinct_sources([]) == []
