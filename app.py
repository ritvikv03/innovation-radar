"""
app.py — Fendt PESTEL-EL Sentinel: Strategic War Room Dashboard
===============================================================
Architecture rules (CLAUDE.md):
  - Imports only from core/. Zero business logic in callbacks.
  - Callbacks are pure functions. No global state mutation.
  - All Plotly colors use rgba() — never 8-char hex (#rrggbbaa).
  - All chart builders tested in _preflight() before Dash starts.
  - ChromaDB access only via SignalDB. Never call chroma directly.
  - Styling via CSS className. Inline style only for dynamic values.

Sponsor requirements implemented:
  1. Verifiable source hyperlinks on every signal row.
  2. Bold 12M/24M/36M time-horizon rings; Urgency Matrix at Overview top.
  3. Universal strategic LLM prompt — no company-specific copy.
  4. Default radar filter ≥ 0.50 (HIGH+CRITICAL only).
  5. dcc.Interval wired to DB; sidebar + canvas auto-refresh every 30s.
"""

from __future__ import annotations

import hashlib
import os
import sys
import textwrap
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Silence noisy loggers before Dash import ──────────────────
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("dash").setLevel(logging.ERROR)

import dash
import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, dcc, html, no_update

# ── Load .env ─────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    _env = Path(__file__).parent / ".env"
    if _env.exists():
        for line in _env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent))
from core.database  import PESTELDimension, Signal, SignalDB
from core.scheduler import HEALTH, engine as _scheduler_engine
from core.logger    import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────────────────────────
# HuggingFace — API token + model config
# ─────────────────────────────────────────────────────────────

_HF_TOKEN   = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_OK      = bool(_HF_TOKEN)
_HF_REPO_ID = "mistralai/Mistral-7B-Instruct-v0.3"

# ─────────────────────────────────────────────────────────────
# DB singleton — all access via SignalDB (CLAUDE.md rule)
# ─────────────────────────────────────────────────────────────

_db: Optional[SignalDB] = None

def _get_db() -> SignalDB:
    global _db
    if _db is None:
        _db = SignalDB()
    return _db


def _db_stats() -> dict:
    try:
        signals = _get_db().get_all()
        if not signals:
            return {"total": 0, "critical": 0, "high": 0, "avg_disruption": 0.0, "by_dim": {}}
        scores = [s.disruption_score for s in signals]
        by_dim: dict[str, int] = {}
        for s in signals:
            by_dim[s.pestel_dimension.value] = by_dim.get(s.pestel_dimension.value, 0) + 1
        return {
            "total":          len(signals),
            "critical":       sum(1 for sc in scores if sc >= 0.75),
            "high":           sum(1 for sc in scores if 0.50 <= sc < 0.75),
            "avg_disruption": round(sum(scores) / len(scores), 3),
            "by_dim":         by_dim,
        }
    except Exception as exc:
        log.error("_db_stats failed: %s", exc)
        return {"total": 0, "critical": 0, "high": 0, "avg_disruption": 0.0, "by_dim": {}}


# ─────────────────────────────────────────────────────────────
# Design Tokens
# ─────────────────────────────────────────────────────────────

_DIM_COLOUR = {
    "POLITICAL":     "#64b5f6",
    "ECONOMIC":      "#a5d6a7",
    "SOCIAL":        "#ffcc80",
    "TECHNOLOGICAL": "#ce93d8",
    "ENVIRONMENTAL": "#80deea",
    "LEGAL":         "#ef9a9a",
}

_DIM_PILL_CODE = {
    "POLITICAL": "P", "ECONOMIC": "E", "SOCIAL": "S",
    "TECHNOLOGICAL": "T", "ENVIRONMENTAL": "En", "LEGAL": "L",
}

_SEV_COLOUR = {"critical": "#ff1744", "high": "#ffab00", "moderate": "#00e5ff", "low": "#3d4f62"}


def _hex_to_rgba(hex_colour: str, alpha: float = 0.30) -> str:
    """Convert '#rrggbb' → 'rgba(r,g,b,alpha)'. Plotly rejects 8-char hex."""
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _sev(score: float) -> str:
    if score >= 0.75: return "critical"
    if score >= 0.50: return "high"
    if score >= 0.30: return "moderate"
    return "low"


# Shared Plotly layout defaults
_CHART_BASE = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_family="Inter, -apple-system, system-ui, sans-serif",
    font_color="#7d8fa8",
    margin=dict(l=36, r=16, t=44, b=36),
    hoverlabel=dict(
        bgcolor="rgba(6,8,13,0.97)",
        bordercolor="rgba(255,255,255,0.08)",
        font_size=11,
        font_family="Inter, sans-serif",
    ),
)

# Axis presets
_AXIS_Y = dict(
    gridcolor="rgba(255,255,255,0.04)",
    zerolinecolor="rgba(255,255,255,0.06)",
    showline=False,
    tickfont=dict(size=10, color="#3d4f62"),
)
_AXIS_X = dict(
    gridcolor="rgba(0,0,0,0)",
    zerolinecolor="rgba(0,0,0,0)",
    showline=False,
    tickfont=dict(size=10, color="#3d4f62"),
)
_AXIS_NONE = dict(showgrid=False, zeroline=False, showline=False,
                  tickfont=dict(size=10, color="#3d4f62"))


# ─────────────────────────────────────────────────────────────
# Chart Builders — pure functions, no side-effects
# ─────────────────────────────────────────────────────────────

def _chart_velocity(signals: list[Signal]) -> go.Figure:
    """Stacked area: signal ingest per day per dimension, last 30 days."""
    now = datetime.now(timezone.utc)
    day_dim: dict[str, list[int]] = {d: [0] * 30 for d in _DIM_COLOUR}

    for s in signals:
        ts = s.date_ingested
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = (now - ts).days
        if 0 <= delta < 30:
            day_dim[s.pestel_dimension.value][29 - delta] += 1

    fig = go.Figure()
    for dim, col in _DIM_COLOUR.items():
        fig.add_trace(go.Scatter(
            x=list(range(30)),
            y=day_dim[dim],
            name=dim,
            mode="lines",
            stackgroup="one",
            line=dict(width=0.5, color=col),
            fillcolor=_hex_to_rgba(col, 0.25),
            hovertemplate=f"{dim}: %{{y}}<extra></extra>",
        ))

    fig.update_layout(
        **_CHART_BASE,
        title=dict(text=f"Signal Ingest · Last 30 Days  ({len(signals)} total)",
                   font_size=11, x=0.01, y=0.96, font_color="#3d4f62"),
        xaxis=dict(title="", **_AXIS_X,
                   tickvals=[0, 9, 19, 29], ticktext=["30d ago", "20d ago", "10d ago", "Today"]),
        yaxis=dict(title="Signals", **_AXIS_Y),
        legend=dict(orientation="h", y=-0.20, font_size=10, bgcolor="rgba(0,0,0,0)"),
        height=260,
    )
    return fig


def _chart_pestel_bar(signals: list[Signal]) -> go.Figure:
    """Horizontal bar: avg disruption per dimension."""
    dim_scores: dict[str, list[float]] = defaultdict(list)
    for s in signals:
        dim_scores[s.pestel_dimension.value].append(s.disruption_score)

    dims = ["LEGAL", "TECHNOLOGICAL", "POLITICAL", "ECONOMIC", "ENVIRONMENTAL", "SOCIAL"]
    avgs = [round(sum(dim_scores[d]) / len(dim_scores[d]), 3) if dim_scores[d] else 0.0
            for d in dims]
    cols = [_DIM_COLOUR[d] for d in dims]

    fig = go.Figure(go.Bar(
        x=avgs, y=dims, orientation="h",
        marker=dict(color=cols, opacity=0.80,
                    line=dict(color="rgba(0,0,0,0)", width=0)),
        hovertemplate="%{y}: %{x:.3f}<extra></extra>",
    ))
    fig.update_layout(
        **_CHART_BASE,
        title=dict(text="Avg Disruption by Dimension", font_size=11, x=0.01, y=0.96, font_color="#3d4f62"),
        xaxis=dict(range=[0, 1], title="", **_AXIS_X),
        yaxis=dict(**_AXIS_X),
        showlegend=False,
        height=240,
    )
    return fig


def _chart_histogram(signals: list[Signal]) -> go.Figure:
    """Disruption score distribution."""
    scores = [s.disruption_score for s in signals]

    fig = go.Figure()
    if not scores:
        fig.add_annotation(text="No signals yet — run the Scout pipeline.",
                           x=0.5, y=0.5, xref="paper", yref="paper",
                           showarrow=False, font=dict(size=12, color="#3d4f62"))
    else:
        fig.add_trace(go.Histogram(
            x=scores, nbinsx=20,
            marker=dict(color=scores, colorscale="Plasma",
                        line=dict(color="rgba(0,0,0,0.3)", width=0.4)),
            hovertemplate="Score: %{x:.2f} — Count: %{y}<extra></extra>",
        ))

    fig.update_layout(
        **_CHART_BASE,
        title=dict(text=f"Disruption Distribution · {len(scores)} signals",
                   font_size=11, x=0.01, y=0.96, font_color="#3d4f62"),
        xaxis=dict(title="Composite Score", range=[0, 1], **_AXIS_X),
        yaxis=dict(title="Count", **_AXIS_Y),
        bargap=0.06,
        height=220,
        showlegend=False,
    )
    return fig


def _chart_radar(signals: list[Signal],
                 dim_filter: str = "All",
                 min_score: float = 0.50) -> go.Figure:
    """
    Innovation Radar — disruption score → 12M/24M/36M time ring.
    Default min_score=0.50 shows only HIGH+CRITICAL (sponsor requirement #4).
    """
    filtered = [
        s for s in signals
        if s.disruption_score >= min_score
        and (dim_filter == "All" or s.pestel_dimension.value == dim_filter)
    ]

    fig = go.Figure()

    # Ring shading — stronger reds near 12M
    for x0, x1, fill in [
        (0,  12, "rgba(255,23,68,0.08)"),
        (12, 24, "rgba(255,171,0,0.05)"),
        (24, 37, "rgba(0,230,118,0.03)"),
    ]:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=fill, line_width=0, layer="below")

    if not filtered:
        fig.add_annotation(
            text="No signals at this threshold. Lower the filter or run the Scout.",
            x=18, y=0.5, showarrow=False,
            font=dict(size=13, color="#3d4f62"),
        )
    else:
        for dim, col in _DIM_COLOUR.items():
            sigs = [s for s in filtered if s.pestel_dimension.value == dim]
            if not sigs:
                continue
            xs, ys, sizes, labels = [], [], [], []
            for s in sigs:
                seed = int(hashlib.md5(s.id.encode()).hexdigest(), 16) % (2 ** 32)
                rng  = np.random.default_rng(seed)
                j    = rng.uniform(-3.0, 3.0)
                if s.disruption_score >= 0.75:
                    x = float(np.clip(6.5 + j, 2, 11))
                elif s.disruption_score >= 0.50:
                    x = float(np.clip(18.0 + j, 13, 23))
                else:
                    x = float(np.clip(30.0 + j, 25, 35))
                xs.append(x)
                ys.append(s.disruption_score)
                sizes.append(max(10, s.disruption_score * 36))
                labels.append(s.title[:55] + ("…" if len(s.title) > 55 else ""))
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=dim, mode="markers",
                marker=dict(size=sizes, color=col, opacity=0.85,
                            line=dict(color="rgba(255,255,255,0.15)", width=1)),
                text=labels,
                customdata=[[s.disruption_score, s.pestel_dimension.value, s.source_url]
                            for s in sigs],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Dimension: %{customdata[1]}<br>"
                    "Disruption: %{customdata[0]:.3f}<br>"
                    "<a href='%{customdata[2]}'>Source →</a>"
                    "<extra></extra>"
                ),
            ))

    # Bold, prominent time-horizon ring lines (sponsor requirement #2)
    for x, lbl, col in [
        (12, "▐ 12M · CRITICAL", "#ff1744"),
        (24, "▐ 24M · HIGH",     "#ffab00"),
        (36, "▐ 36M · MONITOR",  "#00e676"),
    ]:
        fig.add_vline(
            x=x,
            line=dict(color=col, width=2.5, dash="solid"),
            annotation_text=lbl,
            annotation=dict(
                font_size=10, font_color=col, y=1.04, yref="paper",
                bgcolor=_hex_to_rgba(col, 0.12),
                bordercolor=col, borderwidth=1, borderpad=4,
            ),
        )

    fig.update_layout(
        **_CHART_BASE,
        title=dict(
            text=f"Innovation Radar · {len(filtered)} of {len(signals)} signals · score ≥ {min_score:.2f}",
            font_size=11, x=0.01, y=0.97, font_color="#3d4f62",
        ),
        xaxis=dict(title="Time to Impact (months)", range=[0, 38], **_AXIS_NONE),
        yaxis=dict(title="Disruption Score", range=[0, 1.10], **_AXIS_NONE),
        legend=dict(orientation="v", x=1.01, font_size=10, bgcolor="rgba(0,0,0,0)"),
        height=480,
    )
    return fig


def _build_export_html() -> str:
    """Build a self-contained HTML report string for download."""
    signals = _get_db().get_all()
    stats   = _db_stats()
    top10   = sorted(signals, key=lambda s: s.disruption_score, reverse=True)[:10]
    critical = [s for s in signals if s.disruption_score >= 0.75]

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = "\n".join(
        f"<tr>"
        f"<td>{s.pestel_dimension.value}</td>"
        f"<td>{s.title[:120]}</td>"
        f"<td>{s.disruption_score:.3f}</td>"
        f"<td>{_sev(s.disruption_score).upper()}</td>"
        f"<td><a href='{s.source_url}' target='_blank'>Source</a></td>"
        f"</tr>"
        for s in top10
    )

    critical_rows = "\n".join(
        f"<tr><td>{s.pestel_dimension.value}</td><td>{s.title[:120]}</td>"
        f"<td>{s.disruption_score:.3f}</td><td><a href='{s.source_url}'>Source</a></td></tr>"
        for s in critical[:5]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fendt PESTEL-EL Intelligence Report — {now_str}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 40px auto; color: #1a1a2e; }}
  h1 {{ font-size: 22px; color: #0d1b2a; border-bottom: 2px solid #0d1b2a; padding-bottom: 8px; }}
  h2 {{ font-size: 16px; color: #1b3a6b; margin-top: 32px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }}
  th {{ background: #1b3a6b; color: #fff; padding: 8px 12px; text-align: left; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #dde1ec; }}
  tr:hover {{ background: #f0f4ff; }}
  .meta {{ font-size: 12px; color: #6b7a99; margin-top: 4px; }}
  .kpi-row {{ display: flex; gap: 24px; margin: 16px 0; }}
  .kpi {{ background: #f0f4ff; border-radius: 8px; padding: 14px 20px; min-width: 120px; }}
  .kpi-val {{ font-size: 28px; font-weight: 700; color: #1b3a6b; }}
  .kpi-lbl {{ font-size: 11px; color: #6b7a99; margin-top: 2px; }}
  a {{ color: #1b3a6b; }}
</style>
</head>
<body>
<h1>Fendt PESTEL-EL Strategic Intelligence Report</h1>
<p class="meta">Generated: {now_str} &nbsp;|&nbsp; EU Data Act 2026 Compliant</p>

<div class="kpi-row">
  <div class="kpi"><div class="kpi-val">{stats['total']}</div><div class="kpi-lbl">Total Signals</div></div>
  <div class="kpi"><div class="kpi-val">{stats['critical']}</div><div class="kpi-lbl">Critical (&ge;0.75)</div></div>
  <div class="kpi"><div class="kpi-val">{stats['high']}</div><div class="kpi-lbl">High (0.50&ndash;0.75)</div></div>
  <div class="kpi"><div class="kpi-val">{stats['avg_disruption']:.3f}</div><div class="kpi-lbl">Avg Disruption</div></div>
</div>

<h2>Urgency Matrix — 12M Critical Signals</h2>
<table>
  <tr><th>Dimension</th><th>Signal</th><th>Score</th><th>Source</th></tr>
  {critical_rows if critical_rows else '<tr><td colspan="4">No critical signals at this time.</td></tr>'}
</table>

<h2>Top 10 Signals by Disruption Score</h2>
<table>
  <tr><th>Dimension</th><th>Signal</th><th>Score</th><th>Severity</th><th>Source</th></tr>
  {rows if rows else '<tr><td colspan="5">No signals found. Run the Scout to ingest intelligence.</td></tr>'}
</table>

<p class="meta" style="margin-top:32px;">
  This report was generated by the Fendt PESTEL-EL Sentinel.
  All signals include verifiable source URLs in compliance with EU Data Act 2026 provenance requirements.
</p>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────
# Pre-flight — crash before Dash starts if any builder breaks
# ─────────────────────────────────────────────────────────────

def _preflight() -> None:
    signals = _get_db().get_all()
    _chart_velocity(signals)
    _chart_pestel_bar(signals)
    _chart_histogram(signals)
    _chart_radar(signals)
    log.info("Pre-flight passed — all chart builders OK (%d signals)", len(signals))


# ─────────────────────────────────────────────────────────────
# Micro-components (CSS className throughout)
# ─────────────────────────────────────────────────────────────

def _metric(label: str, value: str, sub: str = "", glow: str = "") -> html.Div:
    cls = f"kpi-card{(' glow-' + glow) if glow else ''}"
    return html.Div([
        html.Div(label, className="kpi-label"),
        html.Div(value, className="kpi-value"),
        html.Div(sub, className="kpi-sub") if sub else html.Span(),
    ], className=cls)


def _dot(label: str, kind: str = "idle") -> html.Div:
    return html.Div([
        html.Div(className=f"sb-dot dot-{kind}"),
        html.Span(label),
    ], className="sb-status")


def _feed_card(s: Signal) -> html.Div:
    """Signal feed row with verifiable source link (sponsor requirement #1)."""
    score    = s.disruption_score
    sev      = _sev(score)
    sev_col  = _SEV_COLOUR[sev]
    dim      = s.pestel_dimension.value
    dim_code = _DIM_PILL_CODE.get(dim, "P")
    ts       = s.date_ingested.strftime("%d %b %Y %H:%M UTC")

    return html.Div([
        html.Div([
            html.Span(dim[:3], className=f"dim-pill dp-{dim_code}"),
            html.Span(sev.upper(), className=f"sev-badge sev-{sev}"),
            html.Span(f"{score:.3f}", className="feed-score"),
        ], className="feed-header"),
        html.Div(s.title, className="feed-title"),
        html.Div([
            html.Span(ts, className="feed-meta"),
            html.A("↗ Verify Source", href=s.source_url, target="_blank",
                   className="source-link", style={"marginLeft": "12px"}),
        ]),
    ], className="feed-row", style={"borderLeftColor": sev_col})


def _chat_bubble(text: str, role: str = "assistant") -> html.Div:
    cls = "bubble bubble-user" if role == "user" else "bubble bubble-assistant"
    return html.Div(
        html.Div(text, style={"whiteSpace": "pre-wrap"}),
        className=cls,
    )


# ─────────────────────────────────────────────────────────────
# Urgency Matrix — 12M CRITICAL signals (sponsor requirement #2)
# ─────────────────────────────────────────────────────────────

def _urgency_card(s: Signal) -> html.Div:
    dim_code = _DIM_PILL_CODE.get(s.pestel_dimension.value, "P")
    return html.Div([
        html.Span(s.pestel_dimension.value[:3], className=f"dim-pill dp-{dim_code}"),
        html.Div(f"{s.disruption_score:.3f}", className="urgency-score"),
        html.Div(s.title, className="urgency-title"),
        html.A("↗ Verify Source", href=s.source_url, target="_blank", className="source-link"),
    ], className="urgency-card")


def _urgency_matrix(signals: list[Signal]) -> html.Div:
    critical = sorted(
        [s for s in signals if s.disruption_score >= 0.75],
        key=lambda s: s.disruption_score,
        reverse=True,
    )[:3]

    if not critical:
        return html.Div([
            html.Div("URGENCY MATRIX — 12M CRITICAL", className="section-label"),
            html.Div(
                "No critical signals (score ≥ 0.75). Run the Scout to ingest intelligence.",
                style={"fontSize": "12px", "color": "#3d4f62"},
            ),
        ], className="mb-4")

    return html.Div([
        html.Div("URGENCY MATRIX — 12M CRITICAL SIGNALS", className="section-label"),
        dbc.Row(
            [dbc.Col(_urgency_card(s), md=4) for s in critical],
            className="g-3",
        ),
    ], className="mb-4")


# ─────────────────────────────────────────────────────────────
# Tab Content Builders
# ─────────────────────────────────────────────────────────────

def _tab_overview() -> html.Div:
    signals = _get_db().get_all()
    stats   = _db_stats()
    total   = stats["total"]
    top3    = sorted(signals, key=lambda s: s.disruption_score, reverse=True)[:3]

    return html.Div([
        # ── Urgency Matrix (top, always first) ─────────────────
        _urgency_matrix(signals),

        # ── KPI Tiles ──────────────────────────────────────────
        html.Div("KEY METRICS", className="section-label"),
        dbc.Row([
            dbc.Col(_metric("Total Signals",   str(total) if total else "—",
                            "in ChromaDB", "cyan"), md=3),
            dbc.Col(_metric("Critical",        str(stats["critical"]) if total else "—",
                            "score ≥ 0.75", "red"), md=3),
            dbc.Col(_metric("High",            str(stats["high"]) if total else "—",
                            "score 0.50–0.75", "amber"), md=3),
            dbc.Col(_metric("Avg Disruption",  f'{stats["avg_disruption"]:.3f}' if total else "—",
                            "I×0.5 + N×0.3 + V×0.2", "green" if total else ""), md=3),
        ], className="g-3 mb-4"),

        # ── Charts Row ──────────────────────────────────────────
        dbc.Row([
            dbc.Col(html.Div(
                dcc.Graph(figure=_chart_velocity(signals), config={"displayModeBar": False}),
                className="chart-card",
            ), md=8),
            dbc.Col(html.Div(
                dcc.Graph(figure=_chart_pestel_bar(signals), config={"displayModeBar": False}),
                className="chart-card",
            ), md=4),
        ], className="g-3 mb-4"),

        # ── Distribution + Top Signals ──────────────────────────
        dbc.Row([
            dbc.Col(html.Div(
                dcc.Graph(figure=_chart_histogram(signals), config={"displayModeBar": False}),
                className="chart-card",
            ), md=6),
            dbc.Col(html.Div([
                html.Div("TOP SIGNALS — HIGH + CRITICAL", className="section-label"),
                *([_feed_card(s) for s in top3] if top3 else [
                    html.P("No signals yet. Run the Scout.",
                           style={"color": "#3d4f62", "fontSize": "12px"}),
                ]),
            ], className="war-card"), md=6),
        ], className="g-3"),
    ])


def _tab_radar() -> html.Div:
    """Innovation Radar — default shows only HIGH+CRITICAL (score ≥ 0.50)."""
    return html.Div([
        dbc.Row([
            dbc.Col(html.Div(
                dcc.Loading(
                    dcc.Graph(id="radar-chart", config={"displayModeBar": False}),
                    type="circle", color="#00e5ff",
                ),
                className="chart-card",
            ), md=9),
            dbc.Col(html.Div([
                # Ring guide
                html.Div("RING GUIDE", className="section-label"),
                *[html.Div([
                    html.Div(style={"width": "10px", "height": "10px", "borderRadius": "50%",
                                    "background": col, "flexShrink": "0",
                                    "boxShadow": f"0 0 6px {col}"}),
                    html.Span(f"{ring} — {lbl}", style={"fontSize": "11px", "color": "#7d8fa8"}),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "7px"})
                  for ring, lbl, col in [
                      ("12M", "CRITICAL · Immediate",     "#ff1744"),
                      ("24M", "HIGH · Plan Now",          "#ffab00"),
                      ("36M", "MONITOR · Watch Horizon",  "#00e676"),
                  ]],

                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "16px 0"}),

                # Filters
                html.Div("FILTERS", className="section-label"),
                html.Div("PESTEL Dimension", className="filter-label"),
                dcc.Dropdown(
                    id="radar-dim-filter",
                    options=[{"label": d, "value": d} for d in
                             ["All", "POLITICAL", "ECONOMIC", "SOCIAL",
                              "TECHNOLOGICAL", "ENVIRONMENTAL", "LEGAL"]],
                    value="All", clearable=False,
                    style={"marginBottom": "14px"},
                ),
                html.Div("Min Disruption Score", className="filter-label"),
                dcc.Slider(
                    id="radar-score-slider",
                    min=0, max=1, step=0.05,
                    value=0.50,          # default: HIGH+CRITICAL only (sponsor req #4)
                    marks={0: "0", 0.50: "0.50", 0.75: "0.75", 1: "1"},
                    tooltip={"placement": "bottom"},
                ),
                html.Div(
                    "Default shows HIGH + CRITICAL only (≥ 0.50)",
                    style={"fontSize": "9.5px", "color": "#3d4f62", "marginTop": "8px"},
                ),
            ], className="war-card"), md=3),
        ], className="g-3"),
    ])


def _tab_feed() -> html.Div:
    signals = sorted(_get_db().get_all(), key=lambda s: s.date_ingested, reverse=True)
    stats   = _db_stats()
    by_dim  = stats.get("by_dim", {})

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div(
                    f"{len(signals)} signal(s) · sorted newest first · live from ChromaDB",
                    style={"fontSize": "11px", "color": "#3d4f62", "marginBottom": "16px"},
                ),
                html.Div(
                    [_feed_card(s) for s in signals] if signals else [
                        html.P("No signals. Run the Scout to ingest data.",
                               style={"color": "#3d4f62", "fontSize": "12px"}),
                    ],
                ),
            ], md=8),
            dbc.Col(html.Div([
                html.Div("DATABASE", className="section-label"),
                _metric("Total",    str(stats["total"]) if stats["total"] else "—"),
                html.Div(style={"height": "10px"}),
                _metric("Critical", str(stats["critical"]) if stats["total"] else "—",
                        glow="red"),
                html.Div(style={"height": "10px"}),
                _metric("Avg Score", f'{stats["avg_disruption"]:.3f}' if stats["total"] else "—"),

                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "16px 0"}),
                html.Div("BY DIMENSION", className="section-label"),
                *[html.Div([
                    html.Span(d[:3], style={"fontSize": "10px", "fontWeight": "600",
                                            "color": _DIM_COLOUR.get(d, "#7d8fa8"),
                                            "minWidth": "36px", "display": "inline-block"}),
                    html.Span(str(by_dim.get(d, 0)),
                              style={"fontFamily": "JetBrains Mono, monospace",
                                     "fontSize": "11px", "color": "#e8edf5"}),
                ], style={"marginBottom": "6px"})
                  for d in ["POLITICAL", "ECONOMIC", "SOCIAL",
                             "TECHNOLOGICAL", "ENVIRONMENTAL", "LEGAL"]],
            ], className="war-card"), md=4),
        ], className="g-3"),
    ])


def _tab_chatbot(history: list[dict] | None = None) -> html.Div:
    db_count      = _db_stats()["total"]
    hf_status = "Live" if _HF_OK else "No API key"

    welcome = _chat_bubble(
        f"Fendt Intelligence Assistant\n\n"
        f"{db_count} signal(s) indexed in ChromaDB. HuggingFace: {hf_status}\n\n"
        f"Ask about macro-level strategic decisions, regulatory timelines, "
        f"competitive positioning, or supply chain risks across the EU agricultural market.",
        role="assistant",
    )
    bubbles = [welcome]
    if history:
        for msg in history:
            bubbles.append(_chat_bubble(msg["text"], role=msg["role"]))

    chips = [
        "What immediate supply chain pivots must Tier-1 OEMs make?",
        "Which EU regulations pose the highest 12-month compliance risk?",
        "What M&A targets should agricultural OEMs consider?",
        "How does CAP reform reshape the precision farming market?",
        "Which technology investments have the strongest ROI case?",
    ]

    return html.Div([
        dbc.Row([
            dbc.Col(html.Div([
                html.Div(id="chat-messages", children=bubbles, className="chat-history"),
                html.Div([
                    dcc.Input(
                        id="chat-input", type="text",
                        placeholder="Ask about EU macro trends, OEM strategy, regulatory risk…",
                        debounce=False, n_submit=0,
                        className="chat-input-field",
                    ),
                    dbc.Button("Send", id="chat-send", className="btn-send",
                               color="info", size="sm"),
                ], className="chat-controls"),
            ]), md=8),
            dbc.Col(html.Div([
                html.Div("STRATEGIC PROMPTS", className="section-label"),
                *[html.Div(q, id=f"chip-{i}", n_clicks=0, className="chip")
                  for i, q in enumerate(chips)],
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("MODEL", className="section-label"),
                html.Div(_HF_REPO_ID,
                         style={"fontFamily": "JetBrains Mono, monospace",
                                "fontSize": "10px", "color": "#7d8fa8"}),
                html.Div("Universal Strategic Analysis",
                         style={"fontSize": "10px", "color": "#3d4f62", "marginTop": "4px"}),
            ], className="war-card"), md=4),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────
# HuggingFace Strategic Chat Helper (sponsor requirement #3)
# ─────────────────────────────────────────────────────────────

_CHAT_SYSTEM = textwrap.dedent("""\
    You are a strategic intelligence analyst serving Tier-1 Agricultural OEM leadership
    (AGCO, CNH Industrial, John Deere, Claas, Kubota equivalent).

    ANALYSIS FRAMEWORK — structure every response as:
    1. SIGNAL FINDING: What macro-level force is operating?
    2. INDUSTRY IMPLICATION: How does this affect ALL Tier-1 Agricultural OEMs globally?
    3. STRATEGIC RECOMMENDATION: What universal, actionable decisions must OEM leadership make?

    UNIVERSAL STRATEGIC ACTIONS to consider:
    - Supply chain pivots and dual-sourcing strategies
    - M&A targets and technology partnership candidates
    - TCO positioning and fleet electrification timelines
    - Regulatory compliance investment priorities
    - Precision agriculture platform decisions
    - Market entry/exit timing for EU segments

    STRICT RULES:
    - Cite specific signal titles and disruption scores when referencing data.
    - DO NOT write company-specific marketing copy or brand-specific recommendations.
    - DO NOT name specific companies as "winners" or "losers" without signal evidence.
    - Write decisions that any Tier-1 OEM C-suite can act on universally.
    - Maximum 220 words. Be direct, strategic, and decisive.
""")


def _llm_chat(question: str, context_signals: list[Signal]) -> str:
    """Call HuggingFace model for strategic chat analysis."""
    if not _HF_OK:
        return "HuggingFace API token not configured. Set HUGGINGFACEHUB_API_TOKEN in your .env file."

    context = (
        "\n\n".join(
            f"[Signal {i}] {s.title}\n"
            f"  Dimension: {s.pestel_dimension.value}\n"
            f"  Disruption Score: {s.disruption_score:.3f}\n"
            f"  Content: {s.content}\n"
            f"  Source: {s.source_url}"
            for i, s in enumerate(context_signals, 1)
        ) if context_signals else "No matching signals found in ChromaDB."
    )
    prompt = (
        f"[INST] {_CHAT_SYSTEM}\n\n"
        f"INTELLIGENCE CONTEXT:\n{context}\n\n"
        f"STRATEGIC QUESTION: {question}\n\n"
        f"UNIVERSAL STRATEGIC ANALYSIS: [/INST]"
    )
    try:
        from langchain_huggingface import HuggingFaceEndpoint
        llm = HuggingFaceEndpoint(
            repo_id=_HF_REPO_ID,
            huggingfacehub_api_token=_HF_TOKEN,
            max_new_tokens=600,
            temperature=0.25,
            timeout=60,
        )
        result = llm.invoke(prompt)
        if hasattr(result, "content"):
            result = result.content
        if isinstance(result, list):
            result = " ".join(str(p) for p in result)
        return str(result).strip()
    except Exception as exc:
        return f"LLM error: {exc}"


# ─────────────────────────────────────────────────────────────
# App + Layout
# ─────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700"
        "&family=JetBrains+Mono:wght@400;600&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="Fendt Sentinel",
)

_TABS = [
    ("overview", "Field Intelligence"),
    ("radar",    "Disruption Horizon"),
    ("feed",     "Signal Feed"),
    ("chatbot",  "Strategic Advisor"),
]

# ── Sidebar ────────────────────────────────────────────────────
sidebar = html.Div([
    html.Div([
        html.Div("SENTINEL", className="sb-brand-name"),
        html.Div("AGRO-MARKET INTELLIGENCE", className="sb-brand-sub"),
    ], className="sb-brand"),

    html.Div(id="sidebar-body"),  # live metrics

    html.Div([
        dbc.Button("Run Scout Now", id="run-scout-btn", className="btn-scout",
                   color="success", size="sm", outline=True),
        html.Div(id="run-scout-status", className="sb-run-status"),
    ], className="sb-action"),

    html.Div([
        html.Div("v4.0 · EU Data Act 2026"),
        html.Div("AGCO / Fendt Intelligence Platform"),
    ], className="sb-footer"),
], className="war-sidebar")

# ── Top Bar ────────────────────────────────────────────────────
topbar = html.Header([
    html.Div("Fendt PESTEL-EL Strategic Sentinel", className="topbar-title"),
    html.Div(id="topbar-badge"),
    dbc.Button("Export Report", id="export-btn", className="btn-refresh",
               color="secondary", size="sm", outline=True,
               style={"marginRight": "8px"}),
    dbc.Button("Refresh", id="refresh-btn", className="btn-refresh",
               color="secondary", size="sm", outline=True),
    html.Div(id="topbar-ts", className="topbar-ts"),
], className="war-topbar")

# ── Full Layout ────────────────────────────────────────────────
app.layout = html.Div([
    sidebar,
    html.Div([
        topbar,
        html.Nav(
            dbc.Tabs(
                [dbc.Tab(label=lbl, tab_id=tid) for tid, lbl in _TABS],
                id="main-tabs",
                active_tab="overview",
                className="war-tabs",
            ),
            className="war-tabnav",
        ),
        html.Main(id="page-canvas", className="war-canvas"),
    ], className="war-main"),

    # Persistent state
    dcc.Store(id="chat-store", data=[]),
    dcc.Download(id="export-download"),
    # 30-second auto-refresh (sponsor requirement #5)
    dcc.Interval(id="interval-30s", interval=30_000, n_intervals=0),
], className="war-shell")


# ─────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────

@app.callback(
    Output("page-canvas", "children"),
    Input("main-tabs",    "active_tab"),
    Input("interval-30s", "n_intervals"),
    Input("refresh-btn",  "n_clicks"),
    State("chat-store",   "data"),
)
def render_tab(tab: str, _i: int, _n: int, history: list) -> html.Div:
    triggered = callback_context.triggered_id
    # Chatbot re-renders only on explicit tab switch to avoid clobbering live chat
    if tab == "chatbot":
        return no_update if triggered != "main-tabs" else _tab_chatbot(history or [])
    dispatch = {
        "overview": _tab_overview,
        "radar":    _tab_radar,
        "feed":     _tab_feed,
    }
    try:
        return dispatch.get(tab, _tab_overview)()
    except Exception as exc:
        log.error("render_tab(%s) crashed: %s", tab, exc, exc_info=True)
        return html.Div(
            f"Render error in '{tab}' — check logs for details: {exc}",
            style={"color": "#ff6090", "padding": "24px",
                   "fontFamily": "JetBrains Mono, monospace", "fontSize": "12px"},
        )


@app.callback(
    Output("radar-chart",       "figure"),
    Input("radar-dim-filter",   "value"),
    Input("radar-score-slider", "value"),
    Input("interval-30s",       "n_intervals"),
    Input("refresh-btn",        "n_clicks"),
)
def update_radar(dim_filter: str, min_score: float, _i: int, _n: int) -> go.Figure:
    try:
        return _chart_radar(_get_db().get_all(), dim_filter or "All", min_score or 0.50)
    except Exception as exc:
        log.error("update_radar crashed: %s", exc)
        return go.Figure()


@app.callback(
    Output("sidebar-body", "children"),
    Output("topbar-badge", "children"),
    Output("topbar-ts",    "children"),
    Input("interval-30s",  "n_intervals"),
    Input("refresh-btn",   "n_clicks"),
)
def update_sidebar(_i: int, _n: int):
    stats    = _db_stats()
    total    = stats["total"]
    by_dim   = stats.get("by_dim", {})

    db_kind    = "live" if total else "idle"
    gem_kind   = "live" if _HF_OK else "warn"
    sched_kind = "live" if HEALTH["scheduler_alive"] else "idle"
    scout_kind = "warn" if HEALTH["scout_running"] else sched_kind

    body = html.Div([
        html.Div([
            html.Div("ANALYTICS", className="sb-section-label"),
            html.Div([
                html.Div("Signals", className="sb-kpi-label"),
                html.Div(str(total) if total else "—", className="sb-kpi-value"),
            ], className="sb-kpi"),
            html.Div([
                html.Div("Critical", className="sb-kpi-label"),
                html.Div(str(stats["critical"]) if total else "—", className="sb-kpi-value"),
            ], className="sb-kpi"),
            html.Div([
                html.Div("Avg Score", className="sb-kpi-label"),
                html.Div(f'{stats["avg_disruption"]:.3f}' if total else "—",
                         className="sb-kpi-value"),
            ], className="sb-kpi"),
        ], className="sb-section"),

        html.Div(className="sb-divider"),

        html.Div([
            html.Div("SERVICES", className="sb-section-label"),
            _dot("ChromaDB",   db_kind),
            _dot("HuggingFace API", gem_kind),
            _dot("Scheduler",  sched_kind),
            _dot("Scout",      scout_kind),
        ], className="sb-section"),

        html.Div(className="sb-divider"),

        html.Div([
            html.Div("COVERAGE", className="sb-section-label"),
            *[html.Div([
                html.Span(d[:3], className="sb-cov-dim",
                          style={"color": _DIM_COLOUR.get(d, "#7d8fa8")}),
                html.Span(str(by_dim.get(d, 0)), className="sb-cov-count"),
            ], className="sb-cov-row")
              for d in ["POLITICAL", "ECONOMIC", "SOCIAL",
                        "TECHNOLOGICAL", "ENVIRONMENTAL", "LEGAL"]],
        ], className="sb-section"),
    ])

    badge = html.Div(
        f"{total} signals" if total else "NO DATA",
        className="topbar-badge",
        style={
            "color":       "#00e676" if total else "#ff1744",
            "borderColor": "rgba(0,230,118,0.5)" if total else "rgba(255,23,68,0.5)",
            "background":  "rgba(0,230,118,0.08)" if total else "rgba(255,23,68,0.08)",
        },
    )
    ts = datetime.now(timezone.utc).strftime("UTC %H:%M:%S · auto-refresh 30s")
    return body, badge, ts


@app.callback(
    Output("chat-messages", "children"),
    Output("chat-store",    "data"),
    Output("chat-input",    "value"),
    Input("chat-send",  "n_clicks"),
    Input("chat-input", "n_submit"),
    *[Input(f"chip-{i}", "n_clicks") for i in range(5)],
    State("chat-input", "value"),
    State("chat-store", "data"),
    prevent_initial_call=True,
)
def send_message(n_send, n_sub, *args):
    chip_texts = [
        "What immediate supply chain pivots must Tier-1 OEMs make?",
        "Which EU regulations pose the highest 12-month compliance risk?",
        "What M&A targets should agricultural OEMs consider?",
        "How does CAP reform reshape the precision farming market?",
        "Which technology investments have the strongest ROI case?",
    ]
    chip_clicks = args[:5]
    question    = args[5] or ""
    history     = list(args[6] or [])

    triggered = callback_context.triggered_id
    if triggered and str(triggered).startswith("chip-"):
        question = chip_texts[int(str(triggered).split("-")[1])]

    if not question.strip():
        return no_update, no_update, no_update

    question = question.strip()
    try:
        results = _get_db().search(question, n_results=6)
        context = [sig for sig, _ in results]
    except Exception:
        context = []

    answer = _llm_chat(question, context)

    history.append({"role": "user",      "text": question})
    history.append({"role": "assistant", "text": answer})
    if len(history) > 20:
        history = history[-20:]

    welcome = _chat_bubble(
        f"Fendt Intelligence Assistant · {_db_stats()['total']} signal(s) indexed.",
        role="assistant",
    )
    bubbles = [welcome] + [_chat_bubble(m["text"], m["role"]) for m in history]
    return bubbles, history, ""


@app.callback(
    Output("run-scout-status", "children"),
    Input("run-scout-btn", "n_clicks"),
    prevent_initial_call=True,
)
def trigger_scout(n: int) -> str:
    if not _HF_OK:
        return "HuggingFace API token missing."
    _scheduler_engine.trigger_now()
    log.info("Manual scout triggered via UI (n_clicks=%d)", n)
    return "Scout running in background — check sidebar for updates."


@app.callback(
    Output("export-download", "data"),
    Input("export-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_report(n_clicks: int):
    html_content = _build_export_html()
    filename = f"fendt-pestel-report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.html"
    return dcc.send_string(html_content, filename)


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _preflight()

    _scheduler_engine.start()
    stats = _db_stats()
    log.info("App starting — ChromaDB: %d signals, HuggingFace: %s",
             stats["total"], "OK" if _HF_OK else "NO KEY")

    print(f"\n  Fendt Sentinel  ·  http://localhost:8050")
    print(f"  ChromaDB : {stats['total']} signal(s)")
    print(f"  HuggingFace: {'OK' if _HF_OK else 'no API key — set HUGGINGFACEHUB_API_TOKEN'}")
    print(f"  Scheduler: active (6-hour scout cycle)")
    print(f"  Auto-refresh: 30 seconds\n")

    app.run(debug=False, host="0.0.0.0", port=8050)
    _scheduler_engine.stop()
