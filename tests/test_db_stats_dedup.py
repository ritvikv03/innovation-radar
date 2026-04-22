from __future__ import annotations

from types import SimpleNamespace


def _make_signal(sid, url, score, dim="ECONOMIC"):
    class _Dim:
        value = dim
    return SimpleNamespace(
        id=sid,
        source_url=url,
        disruption_score=score,
        pestel_dimension=_Dim(),
    )


def _dedup_by_source(signals):
    """Mirror of the dedup block in _db_stats_cached."""
    seen: set[str] = set()
    unique = []
    for s in sorted(signals, key=lambda s: s.disruption_score, reverse=True):
        if s.source_url not in seen:
            seen.add(s.source_url)
            unique.append(s)
    return unique


def _compute_stats(signals):
    signals = _dedup_by_source(signals)
    scores = [s.disruption_score for s in signals]
    by_dim: dict[str, int] = {}
    for s in signals:
        by_dim[s.pestel_dimension.value] = by_dim.get(s.pestel_dimension.value, 0) + 1
    return {
        "total":    len(signals),
        "critical": sum(1 for sc in scores if sc >= 0.75),
        "high":     sum(1 for sc in scores if 0.50 <= sc < 0.75),
        "by_dim":   by_dim,
    }


def test_duplicate_source_counted_once():
    signals = [
        _make_signal("a", "http://src-a.com", 0.9, "POLITICAL"),
        _make_signal("b", "http://src-a.com", 0.6, "POLITICAL"),  # same source, lower score
        _make_signal("c", "http://src-b.com", 0.8, "ECONOMIC"),
    ]
    stats = _compute_stats(signals)
    assert stats["total"] == 2
    assert stats["by_dim"]["POLITICAL"] == 1
    assert stats["by_dim"]["ECONOMIC"] == 1


def test_highest_score_kept_per_source():
    signals = [
        _make_signal("a", "http://src-a.com", 0.6, "POLITICAL"),
        _make_signal("b", "http://src-a.com", 0.9, "POLITICAL"),  # higher score
    ]
    stats = _compute_stats(signals)
    assert stats["total"] == 1
    assert stats["critical"] == 1   # 0.9 kept, not 0.6


def test_distinct_sources_all_counted():
    signals = [
        _make_signal("a", "http://src-a.com", 0.9),
        _make_signal("b", "http://src-b.com", 0.7),
        _make_signal("c", "http://src-c.com", 0.4),
    ]
    stats = _compute_stats(signals)
    assert stats["total"] == 3
    assert stats["critical"] == 1
    assert stats["high"] == 1


def test_empty_signals():
    assert _compute_stats([])["total"] == 0
