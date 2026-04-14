"""
app.py — Fendt PESTEL-EL Sentinel: Strategic War Room Dashboard
===============================================================
Architecture rules (CLAUDE.md):
  - Imports only from core/. Zero business logic in callbacks.
  - Callbacks are pure functions. No global state mutation.
  - All Plotly colors use rgba() — never 8-char hex (#rrggbbaa).
  - All chart builders tested in _preflight() before Dash starts.
  - Astra DB access only via SignalDB. Never call astrapy directly.
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

import json

import dash
import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
import diskcache
from flask_caching import Cache as _FlaskCache

# ── Optional PDF/Markdown rendering ───────────────────────────
try:
    import markdown as _md_lib
    import fpdf as _fpdf_lib
    _PDF_OK = True
except ImportError:
    _PDF_OK = False
import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, dcc, html, no_update
from dash.long_callback import DiskcacheLongCallbackManager

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
from core.database       import PESTELDimension, Signal, SignalDB
from core.scheduler      import HEALTH, engine as _scheduler_engine
from core.logger         import get_logger
from core.summary_engine import generate_brief_markdown
from core.agents         import run_agent_query
from core.graph_engine   import get_causal_chains, rebuild_graph_from_db, infer_hidden_relationships

log = get_logger(__name__)

# ─────────────────────────────────────────────────────────────
# HuggingFace — API token + model config
# ─────────────────────────────────────────────────────────────

_HF_TOKEN   = os.getenv("HUGGINGFACEHUB_API_TOKEN", "")
_HF_OK      = bool(_HF_TOKEN)
_HF_REPO_ID = "meta-llama/Llama-3.1-8B-Instruct"

# ─────────────────────────────────────────────────────────────
# DB singleton — all access via SignalDB (CLAUDE.md rule)
# ─────────────────────────────────────────────────────────────

_db: Optional[SignalDB] = None

def _get_db() -> SignalDB:
    global _db
    if _db is None:
        _db = SignalDB()
    return _db


# _db_stats() replaced by _db_stats_cached() (Flask-Caching, see below)


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
                   font_size=11, x=0.5, xanchor="center", y=0.96, font_color="#c4d2de"),
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
        title=dict(text="Avg Disruption by Dimension", font_size=11, x=0.5, xanchor="center", y=0.96, font_color="#c4d2de"),
        xaxis=dict(range=[0, 1], title="", **_AXIS_X),
        yaxis=dict(**_AXIS_X),
        showlegend=False,
        height=240,
    )
    return fig


def _chart_histogram(signals: list[Signal]) -> go.Figure:
    """Disruption score distribution — stacked bar by PESTEL dimension."""
    # Score buckets: LOW <0.40, MODERATE 0.40–0.60, HIGH 0.60–0.75, CRITICAL ≥0.75
    buckets = ["LOW\n<0.40", "MODERATE\n0.40–0.60", "HIGH\n0.60–0.75", "CRITICAL\n≥0.75"]

    def _bucket(score: float) -> int:
        if score < 0.40:  return 0
        if score < 0.60:  return 1
        if score < 0.75:  return 2
        return 3

    # Count per dimension per bucket
    counts: dict[str, list[int]] = {d: [0, 0, 0, 0] for d in _DIM_COLOUR}
    for s in signals:
        counts[s.pestel_dimension.value][_bucket(s.disruption_score)] += 1

    fig = go.Figure()

    if not signals:
        fig.add_annotation(
            text="No signals yet — run the Scout pipeline.",
            x=0.5, y=0.5, xref="paper", yref="paper",
            showarrow=False, font=dict(size=12, color="#7d8fa8"),
        )
    else:
        for dim, col in _DIM_COLOUR.items():
            fig.add_trace(go.Bar(
                name=dim,
                x=buckets,
                y=counts[dim],
                marker_color=_hex_to_rgba(col, 0.82),
                marker_line_width=0,
                hovertemplate=f"{dim}: %{{y}} signals<extra></extra>",
            ))

    fig.update_layout(
        **_CHART_BASE,
        barmode="stack",
        title=dict(
            text=f"Disruption Distribution · {len(signals)} signals",
            font_size=11, x=0.5, xanchor="center", y=0.96, font_color="#c4d2de",
        ),
        xaxis=dict(title="", **_AXIS_X),
        yaxis=dict(title="Signals", **_AXIS_Y),
        bargap=0.22,
        legend=dict(orientation="h", y=-0.22, font_size=9, bgcolor="rgba(0,0,0,0)",
                    font_color="#c4d2de"),
        height=240,
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
            font_size=11, x=0.5, xanchor="center", y=0.97, font_color="#c4d2de",
        ),
        xaxis=dict(title="Time to Impact (months)", range=[0, 38], **_AXIS_NONE),
        yaxis=dict(title="Disruption Score", range=[0, 1.10], **_AXIS_NONE),
        legend=dict(orientation="v", x=1.01, font_size=10, bgcolor="rgba(0,0,0,0)"),
        height=480,
    )
    return fig


def _build_export_html() -> str:
    """Build a self-contained HTML report string for download."""
    signals = _get_all_signals_cached()
    stats   = _db_stats_cached()
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
    signals = _get_all_signals_cached()
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
                style={"fontSize": "12px", "color": "#7d8fa8"},
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
    signals = _get_all_signals_cached()
    stats   = _db_stats_cached()
    total   = stats["total"]
    top3    = sorted(signals, key=lambda s: s.disruption_score, reverse=True)[:3]

    return html.Div([
        # ── Urgency Matrix (top, always first) ─────────────────
        _urgency_matrix(signals),

        # ── KPI Tiles ──────────────────────────────────────────
        html.Div("KEY METRICS", className="section-label"),
        dbc.Row([
            dbc.Col(_metric("Total Signals",   str(total) if total else "—",
                            "in Astra DB", "cyan"), md=3),
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
                           style={"color": "#7d8fa8", "fontSize": "12px"}),
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
                    style={"fontSize": "9.5px", "color": "#7d8fa8", "marginTop": "8px"},
                ),
            ], className="war-card"), md=3),
        ], className="g-3"),
    ])


def _tab_feed() -> html.Div:
    signals = sorted(_get_all_signals_cached(), key=lambda s: s.date_ingested, reverse=True)
    stats   = _db_stats_cached()
    by_dim  = stats.get("by_dim", {})

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div(
                    f"{len(signals)} signal(s) · sorted newest first · live from Astra DB",
                    style={"fontSize": "11px", "color": "#7d8fa8", "marginBottom": "16px"},
                ),
                html.Div(
                    [_feed_card(s) for s in signals] if signals else [
                        html.P("No signals. Run the Scout to ingest data.",
                               style={"color": "#7d8fa8", "fontSize": "12px"}),
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
    db_count      = _db_stats_cached()["total"]
    hf_status = "Live" if _HF_OK else "No API key"

    welcome = _chat_bubble(
        f"Fendt Intelligence Assistant\n\n"
        f"{db_count} signal(s) indexed in Astra DB. HuggingFace: {hf_status}\n\n"
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
                dcc.Loading(
                    html.Div(id="chat-messages", children=bubbles, className="chat-history"),
                    id="chat-messages-loading",
                    type="dot",
                    color="#00e5ff",
                ),
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
                         style={"fontSize": "10px", "color": "#7d8fa8", "marginTop": "4px"}),
            ], className="war-card"), md=4),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────
# Tab builders — Phase 2 tabs
# ─────────────────────────────────────────────────────────────

_GRAPH_JSON = Path(__file__).parent / "data" / "graph.json"

# Colour map: PESTEL category → node colour
_CAT_COLOUR: dict[str, str] = {
    "POLITICAL":     "#ff6b6b",
    "ECONOMIC":      "#ffd93d",
    "SOCIAL":        "#6bcb77",
    "TECHNOLOGICAL": "#00e5ff",
    "ENVIRONMENTAL": "#a29bfe",
    "LEGAL":         "#fd79a8",
}

_CYTO_STYLESHEET = [
    {
        "selector": "node",
        "style": {
            "label":            "data(label)",
            "background-color": "data(colour)",
            "color":            "#e2e8f0",
            "font-size":        "10px",
            "font-family":      "JetBrains Mono, monospace",
            "text-wrap":        "wrap",
            "text-max-width":   "120px",
            "width":            "28px",
            "height":           "28px",
            "border-width":     "2px",
            "border-color":     "rgba(255,255,255,0.15)",
        },
    },
    {
        "selector": "edge",
        "style": {
            "line-color":          "#9cb3c9",
            "target-arrow-color":  "#9cb3c9",
            "target-arrow-shape":  "triangle",
            "curve-style":         "bezier",
            "opacity":             "0.6",
            "width":               "data(weight_px)",
            "label":               "data(relationship)",
            "font-size":           "9px",
            "color":               "#9cb3c9",
            "text-opacity":        "0.7",
        },
    },
    {
        "selector": "node:selected",
        "style": {
            "border-color": "#00e5ff",
            "border-width": "3px",
        },
    },
]


def _load_graph_elements() -> list[dict]:
    """Load data/graph.json and convert to cytoscape elements format."""
    if not _GRAPH_JSON.exists():
        return []
    raw = json.loads(_GRAPH_JSON.read_text())
    elements: list[dict] = []
    for node in raw.get("nodes", []):
        cat = node.get("category", "")
        elements.append({
            "data": {
                "id":     node["id"],
                "label":  node.get("label", node["id"])[:40],
                "colour": _CAT_COLOUR.get(cat, "#9cb3c9"),
                "category": cat,
            },
        })
    for link in raw.get("links", []):
        weight = link.get("weight", 0.5)
        elements.append({
            "data": {
                "source":       link["source"],
                "target":       link["target"],
                "relationship": link.get("relationship", ""),
                "weight_px":    max(1, int(weight * 6)),
            },
        })
    return elements


def _render_causal_chains() -> list:
    """Build sidebar widgets for the top causal cascade chains."""
    chains = get_causal_chains(top_n=5)
    if not chains:
        return [html.Div(
            "No cascade chains yet — chains build as signals relate to each other.",
            style={"fontSize": "9px", "color": "#7d8fa8", "lineHeight": "1.6"},
        )]
    items = []
    for c in chains:
        arrow_chain = " → ".join(
            f'<span style="color:{_CAT_COLOUR.get(p, "#7d8fa8")}">{p[:3]}</span>'
            for p in c["chain"]
        )
        items.append(html.Div([
            html.Div(
                f"depth {c['depth']}  ·  {c['predicate']}",
                style={"fontSize": "9px", "color": "#7d8fa8", "fontFamily": "JetBrains Mono, monospace"},
            ),
            html.Div(
                dangerously_allow_html=True,
                children=arrow_chain,
                style={"fontSize": "10px", "marginTop": "2px"},
            ),
        ], style={"marginBottom": "8px", "paddingLeft": "4px",
                  "borderLeft": "2px solid rgba(0,229,255,0.3)"}))
    return items


def _render_inferred_relationships() -> list:
    """Build sidebar widgets for inferred cross-PESTEL cascade relationships."""
    if not _GRAPH_JSON.exists():
        return []
    try:
        graph   = json.loads(_GRAPH_JSON.read_text())
        inferred = [
            t for t in graph.get("triples", [])
            if t.get("metadata", {}).get("inferred")
        ]
    except Exception as exc:
        log.warning("_render_inferred_relationships: %s", exc)
        return []

    if not inferred:
        return [html.Div(
            "No inferred cascades yet — click 'Run Inference' to surface hidden cross-PESTEL relationships.",
            style={"fontSize": "9px", "color": "#7d8fa8", "lineHeight": "1.6"},
        )]

    items = []
    for t in inferred[:5]:
        chain   = t.get("metadata", {}).get("causal_chain", [])
        hops    = t.get("metadata", {}).get("hop_count", 0)
        subj    = t.get("subject", {}).get("label", "?")
        obj     = t.get("object", {}).get("label", "?")
        arrow   = " → ".join(
            f'<span style="color:{_CAT_COLOUR.get(p, "#7d8fa8")}">{p[:3]}</span>'
            for p in chain
        )
        items.append(html.Div([
            html.Div(
                f"{hops}-hop cascade",
                style={"fontSize": "9px", "color": "#00e5ff",
                       "fontFamily": "JetBrains Mono, monospace"},
            ),
            html.Div(
                dangerously_allow_html=True,
                children=arrow,
                style={"fontSize": "10px", "marginTop": "2px"},
            ),
            html.Div(
                f"{subj[:28]} → {obj[:28]}",
                style={"fontSize": "9px", "color": "#7d8fa8", "marginTop": "2px"},
            ),
        ], style={"marginBottom": "8px", "paddingLeft": "4px",
                  "borderLeft": "2px solid rgba(0,229,255,0.15)"}))
    return items


def _tab_graph() -> html.Div:
    """Knowledge Graph — causal interdependency visualisation."""
    elements   = _load_graph_elements_cached()
    node_count = sum(1 for e in elements if "source" not in e.get("data", {}))
    edge_count = len(elements) - node_count

    # Shared control buttons (always present)
    graph_controls = html.Div([
        dbc.Button(
            "Rebuild Graph", id="rebuild-graph-btn",
            color="warning", size="sm", outline=True,
            style={"marginRight": "8px", "fontSize": "10px"},
        ),
        dbc.Button(
            "Run Inference", id="run-inference-btn",
            color="info", size="sm", outline=True,
            style={"fontSize": "10px"},
        ),
        html.Div(id="graph-action-status",
                 style={"fontSize": "10px", "color": "#7d8fa8", "marginTop": "6px"}),
    ], style={"marginBottom": "12px"})

    if node_count == 0:
        empty = html.Div([
            html.Div("○", className="empty-state-icon"),
            html.Div("No graph data yet", className="empty-state-title"),
            html.Div(
                "Run the Scout to ingest signals. The Knowledge Graph builds automatically "
                "after each cycle — only nodes derived from live Astra DB signals appear here. "
                "Use 'Rebuild Graph' to reconstruct from the current DB state.",
                className="empty-state-body",
            ),
        ], className="empty-state")
        return html.Div([
            dbc.Row([
                dbc.Col(html.Div(empty, className="chart-card",
                                 style={"minHeight": "400px", "display": "flex",
                                        "alignItems": "center", "justifyContent": "center"}),
                        md=9),
                dbc.Col(html.Div([
                    graph_controls,
                    html.Div("GRAPH INFO", className="section-label"),
                    _metric("Nodes", "—"), html.Div(style={"height": "8px"}),
                    _metric("Edges", "—"),
                    html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                    html.Div("Run the Scout to generate graph data.",
                             style={"fontSize": "10px", "color": "#7d8fa8", "lineHeight": "1.6"}),
                ], className="war-card"), md=3),
            ], className="g-3"),
        ])

    legend = [
        html.Div([
            html.Div(style={"width": "10px", "height": "10px", "borderRadius": "50%",
                            "background": col, "flexShrink": "0",
                            "boxShadow": f"0 0 5px {col}"}),
            html.Span(cat, style={"fontSize": "10px", "color": "#e8edf5"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "6px"})
        for cat, col in _CAT_COLOUR.items()
    ]

    return html.Div([
        dbc.Row([
            dbc.Col(html.Div(
                cyto.Cytoscape(
                    id="knowledge-graph",
                    elements=elements,
                    layout={"name": "cose", "animate": False},
                    stylesheet=_CYTO_STYLESHEET,
                    style={"width": "100%", "height": "560px",
                           "background": "rgba(13,17,23,0.95)",
                           "borderRadius": "8px"},
                ),
                className="chart-card",
            ), md=9),
            dbc.Col(html.Div([
                graph_controls,
                html.Div("GRAPH INFO", className="section-label"),
                _metric("Nodes", str(node_count)),
                html.Div(style={"height": "8px"}),
                _metric("Edges", str(edge_count)),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("INFERRED CASCADES", className="section-label"),
                *_render_inferred_relationships(),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("CAUSAL CHAINS", className="section-label"),
                *_render_causal_chains(),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("DIMENSION KEY", className="section-label"),
                *legend,
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("LAYOUT", className="section-label"),
                html.Div("CoSE (force-directed)",
                         style={"fontFamily": "JetBrains Mono, monospace",
                                "fontSize": "10px", "color": "#e8edf5"}),
                html.Div("Click a node to inspect · Drag to explore",
                         style={"fontSize": "10px", "color": "#7d8fa8", "marginTop": "6px"}),
            ], className="war-card"), md=3),
        ], className="g-3"),
    ])


# ── Reports helpers ───────────────────────────────────────────

_REPORTS_DIR = Path(__file__).parent / "outputs" / "reports"


def _glob_reports() -> list[dict]:
    """Return sorted list of {label, value} dicts for available .md reports."""
    paths = sorted(_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"label": p.stem.replace("_", " ").title(), "value": str(p)} for p in paths]


def _render_report_body(path: str | None) -> html.Div:
    """Build the full styled report viewer for a given .md path."""
    if not path:
        return html.Div([
            html.Div("📄", className="empty-state-icon"),
            html.Div("No reports available", className="empty-state-title"),
            html.Div(
                "Generate a report by running the Sentinel pipeline, then place the .md file "
                "in outputs/reports/ to register it here.",
                className="empty-state-body",
            ),
        ], className="empty-state")

    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        log.error("_render_report_body: cannot read %s: %s", path, exc)
        return html.P(f"Could not read report: {exc}",
                      style={"color": "#ff6090", "fontSize": "12px", "padding": "16px"})

    # Extract title and generated date from first lines if present
    lines     = content.splitlines()
    doc_title = lines[0].lstrip("# ").strip() if lines else Path(path).stem
    doc_date  = ""
    doc_class = "CONFIDENTIAL — C-SUITE ONLY"
    for line in lines[1:6]:
        if line.startswith("**Generated:**"):
            doc_date = line.replace("**Generated:**", "").strip()
        if line.startswith("**Classification:**"):
            doc_class = line.replace("**Classification:**", "").strip()

    # Strip first heading + metadata from content before rendering body
    body_start = 0
    for i, ln in enumerate(lines):
        if i > 0 and ln.startswith("---"):
            body_start = i + 1
            break
    body_md = "\n".join(lines[body_start:]) if body_start else content

    return html.Div([
        # ── Document header ──────────────────────────────────
        html.Div([
            html.Div([
                html.Div(doc_class, className="report-classification"),
                html.Div(doc_title, className="report-title"),
                html.Div([
                    html.Span("Generated: ", style={"color": "#7d8fa8"}),
                    html.Span(doc_date or "—", style={"color": "#7d8fa8"}),
                    html.Span("  ·  Source: Fendt PESTEL-EL Sentinel",
                              style={"color": "#7d8fa8"}),
                ], className="report-meta"),
            ], className="report-doc-header-left"),
        ], className="report-doc-header"),

        # ── Report body ───────────────────────────────────────
        dcc.Markdown(body_md, dangerously_allow_html=True, className="report-markdown"),
    ])


def _md_to_pdf_bytes(content: str) -> bytes:
    """Convert markdown content to a PDF byte string using fpdf2."""
    from fpdf import FPDF  # type: ignore[import]
    import markdown as md_lib  # type: ignore[import]

    html_body = md_lib.markdown(content, extensions=["tables", "fenced_code"])
    # fpdf2's write_html understands <b>/<i> not <strong>/<em>
    html_body = (
        html_body
        .replace("<strong>", "<b>").replace("</strong>", "</b>")
        .replace("<em>", "<i>").replace("</em>", "</i>")
        .replace("<blockquote>", "<p><i>  ").replace("</blockquote>", "</i></p>")
        .replace("<code>", "").replace("</code>", "")
        .replace("<pre>", "<p>").replace("</pre>", "</p>")
        .replace("<del>", "").replace("</del>", "")
    )

    pdf = FPDF()
    pdf.set_margins(25, 22, 25)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.write_html(html_body)
    return bytes(pdf.output())


def _tab_reports() -> html.Div:
    """Strategic Reports — Markdown viewer for AI-generated C-Suite briefs."""
    options = _glob_reports()
    default = options[0]["value"] if options else None
    initial_body = _render_report_body(default)

    return html.Div([
        dbc.Row([
            dbc.Col([
                # ── Toolbar ────────────────────────────────────
                html.Div([
                    html.Div([
                        html.Div("SELECT REPORT", className="section-label",
                                 style={"marginBottom": "6px"}),
                        dcc.Dropdown(
                            id="reports-dropdown",
                            options=options,
                            value=default,
                            clearable=False,
                            placeholder="No reports found in outputs/reports/",
                        ),
                    ], style={"flex": "1"}),
                    dbc.Button(
                        "✦ Generate New Intelligence Brief",
                        id="reports-gen-btn",
                        color="primary", size="sm",
                        className="btn-refresh",
                        style={"alignSelf": "flex-end", "whiteSpace": "nowrap"},
                    ),
                    dbc.Button(
                        "⬇ Export PDF", id="reports-export-pdf-btn",
                        color="secondary", size="sm", outline=True,
                        className="btn-refresh",
                        style={"alignSelf": "flex-end", "whiteSpace": "nowrap",
                               "opacity": "1" if _PDF_OK else "0.35"},
                        disabled=not _PDF_OK,
                    ),
                ], style={"display": "flex", "gap": "16px", "alignItems": "flex-end",
                          "marginBottom": "12px"}),

                # ── Generation status ───────────────────────────
                html.Div("", id="reports-gen-status",
                         style={"fontSize": "11px", "color": "#7d8fa8",
                                "marginBottom": "16px", "minHeight": "18px"}),

                # ── Report body ─────────────────────────────────
                dcc.Loading(
                    html.Div(initial_body, id="reports-body", className="war-card"),
                    id="reports-body-loading",
                    type="circle",
                    color="#00e5ff",
                ),
            ], md=10),

            dbc.Col(html.Div([
                html.Div("REPORTS", className="section-label"),
                _metric("Available", str(len(options))),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("PDF EXPORT", className="section-label"),
                html.Div(
                    "PDF export ready" if _PDF_OK else "Install fpdf2 + markdown to enable PDF export",
                    style={"fontSize": "9px",
                           "color": "#00e676" if _PDF_OK else "#3d4f62",
                           "lineHeight": "1.6"},
                ),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div(
                    "Place .md files in outputs/reports/ to register them here.",
                    style={"fontSize": "9px", "color": "#7d8fa8", "lineHeight": "1.6"},
                ),
            ], className="war-card"), md=2),
        ], className="g-3"),
    ])


# ── Intelligence Lens helpers ─────────────────────────────────

_LENS_PRESETS = [
    "CAP Reform",
    "Electric Tractor Adoption",
    "Precision Farming Regulation",
    "Grain Price Volatility",
    "EU Green Deal Agriculture",
    "Right to Repair Policy",
    "Labour Shortages in Farming",
    "Custom Search…",
]


def _lens_signal_card(sig: "Signal", score: float) -> html.Div:  # type: ignore[name-defined]
    """Render a single signal result card for the Intelligence Lens."""
    relevance_pct = f"{score * 100:.0f}%"
    dim_col = _DIM_COLOUR.get(sig.pestel_dimension.value, "#9cb3c9")
    bar_w   = max(4, int(score * 100))
    return html.Div([
        html.Div([
            html.Span(sig.pestel_dimension.value[:3],
                      style={"color": dim_col, "fontWeight": "700",
                             "fontSize": "10px", "minWidth": "36px"}),
            html.Span(sig.title,
                      style={"color": "#e8edf5", "fontSize": "12.5px", "fontWeight": "600",
                             "flex": "1", "lineHeight": "1.45"}),
            html.Span(f"{relevance_pct}",
                      style={"color": dim_col, "fontSize": "10px",
                             "fontFamily": "JetBrains Mono, monospace",
                             "fontWeight": "700", "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "gap": "10px", "alignItems": "flex-start",
                  "marginBottom": "8px"}),
        # Relevance bar
        html.Div(html.Div(style={
            "height": "2px", "width": f"{bar_w}%",
            "background": dim_col, "borderRadius": "1px",
            "boxShadow": f"0 0 6px {dim_col}",
        }), style={"background": "rgba(255,255,255,0.06)", "borderRadius": "1px",
                   "marginBottom": "10px", "marginLeft": "46px"}),
        html.P(sig.content[:220] + ("…" if len(sig.content) > 220 else ""),
               style={"fontSize": "12px", "color": "#c4d0dc", "margin": "0 0 8px 46px",
                      "lineHeight": "1.7"}),
        html.A(
            "↗ verify source", href=sig.source_url, target="_blank",
            className="source-link", style={"marginLeft": "46px"},
        ),
    ], className="war-card", style={"marginBottom": "10px"})


def _run_lens_search(topic: str | None, custom: str | None = None) -> html.Div:
    """Execute a semantic search and return result cards (or empty state)."""
    is_custom = topic == "Custom Search…"
    query     = (custom or "").strip() if is_custom else (topic or "").strip()

    if not query:
        return html.Div([
            html.Div("🔍", className="empty-state-icon"),
            html.Div("Enter a search query", className="empty-state-title"),
            html.Div("Select a macro-trend topic above or type a custom query.",
                     className="empty-state-body"),
        ], className="empty-state")

    try:
        total_signals = len(_get_all_signals_cached())
        if total_signals == 0:
            return html.Div([
                html.Div("○", className="empty-state-icon"),
                html.Div("No signals in Astra DB", className="empty-state-title"),
                html.Div(
                    'Click "Run Scout Now" in the sidebar to ingest intelligence. '
                    "The Intelligence Lens will populate after the first scout cycle completes.",
                    className="empty-state-body",
                ),
            ], className="empty-state")

        results = _get_db().search(query, n_results=5)
    except Exception as exc:
        log.error("_run_lens_search crashed: %s", exc)
        return html.P(f"Search error: {exc}",
                      style={"color": "#ff6090", "fontSize": "12px"})

    if not results:
        return html.Div([
            html.Div("○", className="empty-state-icon"),
            html.Div(f'No matches for "{query}"', className="empty-state-title"),
            html.Div("Try a broader query or run the Scout to ingest more signals.",
                     className="empty-state-body"),
        ], className="empty-state")

    header = html.Div(
        f'{len(results)} signal(s) matched · query: "{query}"',
        style={"fontSize": "10px", "color": "#7d8fa8",
               "fontFamily": "JetBrains Mono, monospace", "marginBottom": "14px"},
    )
    return html.Div([header, *[_lens_signal_card(sig, score) for sig, score in results]])


def _tab_lens() -> html.Div:
    """Strategic Intelligence Lens — semantic deep-dive via Astra DB."""
    initial_results = _run_lens_search(_LENS_PRESETS[0])

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Div("MACRO-TREND TOPIC", className="section-label"),
                dcc.Dropdown(
                    id="lens-topic-dropdown",
                    options=[{"label": t, "value": t} for t in _LENS_PRESETS],
                    value=_LENS_PRESETS[0],
                    clearable=False,
                    style={"marginBottom": "10px"},
                ),
                dcc.Input(
                    id="lens-custom-input",
                    type="text",
                    placeholder="Type a custom query (active when 'Custom Search…' selected)…",
                    debounce=True,
                    n_submit=0,
                    className="chat-input-field",
                    style={"marginBottom": "16px", "width": "100%"},
                ),
                dcc.Loading(
                    html.Div(initial_results, id="lens-results"),
                    type="circle", color="#00e5ff",
                ),
            ], md=9),
            dbc.Col(html.Div([
                html.Div("HOW IT WORKS", className="section-label"),
                html.P(
                    "Astra DB semantic search surfaces the most relevant signals for any "
                    "macro-trend query. Results are ranked by cosine similarity using the "
                    "all-MiniLM-L6-v2 embedding model.",
                    style={"fontSize": "10.5px", "color": "#c4d0dc", "lineHeight": "1.7"},
                ),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("TOP-K", className="section-label"),
                html.Div("5 signals per query",
                         style={"fontFamily": "JetBrains Mono, monospace",
                                "fontSize": "10px", "color": "#e8edf5"}),
                html.Hr(style={"borderColor": "rgba(255,255,255,0.07)", "margin": "14px 0"}),
                html.Div("TIP", className="section-label"),
                html.Div('Select "Custom Search…" and type any free-form topic.',
                         style={"fontSize": "9.5px", "color": "#7d8fa8", "lineHeight": "1.6"}),
            ], className="war-card"), md=3),
        ], className="g-3"),
    ])


# ─────────────────────────────────────────────────────────────
# Strategic Chat — delegated to Multi-Agent Relational Brain
# (core/agents.py: Router → Calculator Agent | Analyst Agent)
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# App + Layout
# ─────────────────────────────────────────────────────────────

# Background-callback cache (DiskCache — survives hot-reload)
_CACHE_DIR = Path(__file__).parent / "data" / ".dash_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_disk_cache = diskcache.Cache(str(_CACHE_DIR))
_long_callback_manager = DiskcacheLongCallbackManager(_disk_cache)

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.CYBORG,
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700"
        "&family=JetBrains+Mono:wght@400;600&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="Fendt Sentinel",
    long_callback_manager=_long_callback_manager,
)

# ── Flask-Caching — memoize expensive DB + graph calls ────────
# SimpleCache keeps results in-process (no Redis needed for single-worker Dash).
# 30-second TTL aligns with the auto-refresh interval.
_flask_cache = _FlaskCache(
    app.server,
    config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 30},
)


@_flask_cache.memoize(timeout=30)
def _get_all_signals_cached() -> list:
    """Cached get_all() — avoids hitting Astra DB on every tab render."""
    return _get_db().get_all()


@_flask_cache.memoize(timeout=30)
def _db_stats_cached() -> dict:
    """Cached DB stats — avoids a full get_all() on every sidebar tick."""
    try:
        signals = _get_all_signals_cached()
        scores  = [s.disruption_score for s in signals]
        by_dim: dict[str, int] = {}
        for s in signals:
            dim = s.pestel_dimension.value
            by_dim[dim] = by_dim.get(dim, 0) + 1
        return {
            "total":          len(signals),
            "critical":       sum(1 for sc in scores if sc >= 0.75),
            "high":           sum(1 for sc in scores if 0.50 <= sc < 0.75),
            "avg_disruption": round(sum(scores) / len(scores), 3) if scores else 0.0,
            "by_dim":         by_dim,
            "status":         "ok",
        }
    except Exception as exc:
        log.warning("_db_stats_cached failed: %s", exc)
        return {"total": 0, "critical": 0, "high": 0, "avg_disruption": 0.0,
                "by_dim": {}, "status": "error"}


@_flask_cache.memoize(timeout=30)
def _load_graph_elements_cached() -> list[dict]:
    """Cached graph.json parse — prevents re-reading file on every graph tab load."""
    return _load_graph_elements()


_TABS = [
    ("overview", "Field Intelligence"),
    ("radar",    "Disruption Horizon"),
    ("feed",     "Signal Feed"),
    ("chatbot",  "Strategic Advisor"),
    ("graph",    "Knowledge Graph"),
    ("reports",  "Strategic Reports"),
    ("lens",     "Intelligence Lens"),
]

# ── Sidebar ────────────────────────────────────────────────────
sidebar = html.Div([
    html.Div([
        html.Div("SENTINEL", className="sb-brand-name"),
        html.Div("AGRO-MARKET INTELLIGENCE", className="sb-brand-sub"),
    ], className="sb-brand"),

    dcc.Loading(
        html.Div(id="sidebar-body"),
        id="sidebar-body-loading",
        type="dot",
        color="#7d8fa8",
        style={"minHeight": "40px"},
    ),  # live metrics

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
        dcc.Loading(
            html.Main(id="page-canvas", className="war-canvas"),
            id="page-canvas-loading",
            type="circle",
            color="#00e5ff",
            style={"position": "relative"},
        ),
    ], className="war-main"),

    # Persistent state
    dcc.Store(id="chat-store",    data=[]),
    dcc.Store(id="signals-store", data=[], storage_type="memory"),  # cross-tab signal cache
    dcc.Download(id="export-download"),
    dcc.Download(id="reports-pdf-download"),
    # 30-second auto-refresh (sponsor requirement #5)
    dcc.Interval(id="interval-30s", interval=30_000, n_intervals=0),
], className="war-shell")


# ─────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────

@app.callback(
    Output("signals-store", "data"),
    Input("interval-30s",   "n_intervals"),
    Input("refresh-btn",    "n_clicks"),
)
def refresh_signals_store(_i: int, _n: int) -> list[dict]:
    """Populate signals-store with top-50 signals every 30 s for cross-tab access."""
    try:
        db    = _get_db()
        total = db.count()
        if total == 0:
            return []
        results = db.search("EU agricultural market", n_results=min(50, total))
        return [
            {
                "id":    s.id,
                "title": s.title,
                "dim":   s.pestel_dimension.value,
                "score": s.disruption_score,
            }
            for s, _ in results
        ]
    except Exception as exc:
        log.error("refresh_signals_store failed: %s", exc)
        return []


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
        "graph":    _tab_graph,
        "reports":  _tab_reports,
        "lens":     _tab_lens,
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
        return _chart_radar(_get_all_signals_cached(), dim_filter or "All", min_score or 0.50)
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
    stats    = _db_stats_cached()
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
            _dot("Astra DB",  db_kind),
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


@app.long_callback(
    output=[
        Output("chat-messages", "children"),
        Output("chat-store",    "data"),
        Output("chat-input",    "value"),
    ],
    inputs=[
        Input("chat-send",  "n_clicks"),
        Input("chat-input", "n_submit"),
        Input("chip-0", "n_clicks"),
        Input("chip-1", "n_clicks"),
        Input("chip-2", "n_clicks"),
        Input("chip-3", "n_clicks"),
        Input("chip-4", "n_clicks"),
    ],
    state=[
        State("chat-input", "value"),
        State("chat-store", "data"),
    ],
    running=[
        (Output("chat-send",  "disabled"), True, False),
        (Output("chat-input", "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def send_message(n_send, n_sub, c0, c1, c2, c3, c4, question_val, history_data):
    chip_texts = [
        "What immediate supply chain pivots must Tier-1 OEMs make?",
        "Which EU regulations pose the highest 12-month compliance risk?",
        "What M&A targets should agricultural OEMs consider?",
        "How does CAP reform reshape the precision farming market?",
        "Which technology investments have the strongest ROI case?",
    ]

    question = question_val or ""
    history  = list(history_data or [])

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

    # ── Multi-Agent routing ───────────────────────────────────────────────────
    agent_result = run_agent_query(question, context)
    answer       = agent_result.get("final_answer", "Agent returned no answer.")
    route        = agent_result.get("route", "synthesis")
    trace        = agent_result.get("agent_trace", [])
    confidence   = agent_result.get("confidence", "medium")

    # Prepend route badge so the user can see which agent responded
    route_label = "QUANTITATIVE · Calculator" if route == "quantitative" else "SYNTHESIS · Analyst"
    conf_colour = {"high": "#00e676", "medium": "#ffd93d", "low": "#ff6090"}.get(confidence, "#7d8fa8")
    badge_text  = f"[{route_label}  ·  confidence={confidence}  ·  agents={' → '.join(trace)}]"

    history.append({"role": "user",      "text": question})
    history.append({"role": "assistant", "text": answer, "badge": badge_text, "badge_colour": conf_colour})
    if len(history) > 20:
        history = history[-20:]

    welcome = _chat_bubble(
        f"Fendt Relational Brain — Multi-Agent Strategic Advisor\n\n"
        f"{_db_stats_cached()['total']} signal(s) in Astra DB. "
        f"Router automatically directs queries to the Calculator Agent "
        f"(quantitative) or Analyst Agent (synthesis).",
        role="assistant",
    )
    bubbles = [welcome]
    for msg in history:
        bubble = _chat_bubble(msg["text"], msg["role"])
        if msg["role"] == "assistant" and msg.get("badge"):
            badge = html.Div(
                msg["badge"],
                style={
                    "fontSize": "9px",
                    "fontFamily": "JetBrains Mono, monospace",
                    "color": msg.get("badge_colour", "#7d8fa8"),
                    "marginTop": "6px",
                    "opacity": "0.75",
                },
            )
            bubble = html.Div([bubble, badge])
        bubbles.append(bubble)
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
    Output("graph-action-status", "children"),
    Input("rebuild-graph-btn",   "n_clicks"),
    Input("run-inference-btn",   "n_clicks"),
    prevent_initial_call=True,
)
def graph_action(rebuild_n: int, infer_n: int) -> str:
    """Handle Rebuild Graph and Run Inference buttons."""
    triggered = callback_context.triggered_id
    if triggered == "rebuild-graph-btn":
        try:
            counts = rebuild_graph_from_db()
            _flask_cache.delete_memoized(_load_graph_elements_cached)
            return (
                f"Graph rebuilt: {counts['nodes']} nodes, "
                f"{counts['links']} edges, {counts['triples']} triples"
            )
        except Exception as exc:
            log.error("graph_action rebuild failed: %s", exc)
            return f"Rebuild failed: {exc}"
    elif triggered == "run-inference-btn":
        try:
            result = infer_hidden_relationships()
            _flask_cache.delete_memoized(_load_graph_elements_cached)
            added = result["inferred_added"]
            total = result["total_triples"]
            return f"Inference complete: +{added} hidden cascades ({total} total triples)"
        except Exception as exc:
            log.error("graph_action inference failed: %s", exc)
            return f"Inference failed: {exc}"
    return no_update


@app.callback(
    Output("export-download", "data"),
    Input("export-btn", "n_clicks"),
    prevent_initial_call=True,
)
def export_report(n_clicks: int):
    html_content = _build_export_html()
    filename = f"fendt-pestel-report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.html"
    return dcc.send_string(html_content, filename)


# ── Strategic Reports callback ────────────────────────────────

@app.callback(
    Output("reports-body", "children"),
    Input("reports-dropdown", "value"),
    prevent_initial_call=True,   # initial content embedded by _tab_reports()
)
def render_report(path: str | None) -> html.Div:
    return _render_report_body(path)


@app.callback(
    Output("reports-pdf-download", "data"),
    Input("reports-export-pdf-btn", "n_clicks"),
    State("reports-dropdown", "value"),
    prevent_initial_call=True,
)
def export_report_pdf(_n: int, path: str | None):
    if not path or not _PDF_OK:
        return no_update
    try:
        content  = Path(path).read_text(encoding="utf-8")
        pdf_bytes = _md_to_pdf_bytes(content)
        filename  = f"{Path(path).stem}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
        return dcc.send_bytes(pdf_bytes, filename)
    except Exception as exc:
        log.error("export_report_pdf failed: %s", exc)
        return no_update


# ── Generate Intelligence Brief callback (background) ─────────

@app.long_callback(
    output=[
        Output("reports-dropdown",   "options"),
        Output("reports-dropdown",   "value"),
        Output("reports-gen-status", "children"),
    ],
    inputs=[Input("reports-gen-btn", "n_clicks")],
    running=[
        (Output("reports-gen-btn", "disabled"), True, False),
        (
            Output("reports-gen-status", "children"),
            html.Span("⚙ Generating brief — LLM working…",
                      style={"color": "#ffd93d", "fontSize": "11px"}),
            "",
        ),
    ],
    prevent_initial_call=True,
)
def generate_intelligence_brief(n_clicks: int):
    """Fetch top 10 signals, call generate_brief_markdown, write .md, refresh dropdown.

    Setting reports-dropdown.value triggers render_report automatically —
    no need to also output reports-body.children (that would be a duplicate output).
    """
    try:
        db = SignalDB()
        total = db.count()
        if total == 0:
            return no_update, no_update, "No signals in database — run Scout first."

        results = db.search("agricultural market disruption EU Fendt", n_results=min(10, total))
        signals = sorted([sig for sig, _ in results],
                         key=lambda s: s.disruption_score, reverse=True)

        md_text = generate_brief_markdown(signals)

        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts_str   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = _REPORTS_DIR / f"Strategic_Brief_{ts_str}.md"
        out_path.write_text(md_text, encoding="utf-8")
        log.info("Generated brief: %s", out_path.name)

        new_options = _glob_reports()
        new_value   = str(out_path)
        status_msg  = f"✓ Brief generated: {out_path.name}"
        return new_options, new_value, status_msg

    except Exception as exc:
        log.error("generate_intelligence_brief failed: %s", exc)
        return no_update, no_update, f"Error: {exc}"


# ── Intelligence Lens callback ────────────────────────────────

@app.callback(
    Output("lens-results", "children"),
    Input("lens-topic-dropdown", "value"),
    Input("lens-custom-input",   "value"),
    Input("lens-custom-input",   "n_submit"),
    prevent_initial_call=True,   # initial content embedded by _tab_lens()
)
def lens_search(topic: str | None, custom: str | None, _ns: int) -> html.Div:
    return _run_lens_search(topic, custom)


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _preflight()

    _scheduler_engine.start()
    stats = _db_stats_cached()
    log.info("App starting — Astra DB: %d signals, HuggingFace: %s",
             stats["total"], "OK" if _HF_OK else "NO KEY")

    print(f"\n  Fendt Sentinel  ·  http://localhost:8050")
    print(f"  Astra DB : {stats['total']} signal(s)")
    print(f"  HuggingFace: {'OK' if _HF_OK else 'no API key — set HUGGINGFACEHUB_API_TOKEN'}")
    print(f"  Scheduler: active (6-hour scout cycle)")
    print(f"  Auto-refresh: 30 seconds\n")

    app.run(debug=False, host="0.0.0.0", port=8050)
    _scheduler_engine.stop()
