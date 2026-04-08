"""
Innovation Radar Visualization for Q2
======================================

Creates Thoughtworks-style Innovation Radar chart showing:
- Quadrants: Strict 6 standard PESTEL dimensions (INNOVATION / SOCIAL_MEDIA removed)
- Rings: Time horizons — 12 months = Red, 24 months = Yellow, 36 months = Green
- Dots: Individual disruption signals
- Size: Disruption score magnitude
"""

import plotly.graph_objects as go
import math
from typing import List, Dict
import json

# ---------------------------------------------------------------------------
# Single source of truth for all PESTEL dimension colors.
# Import this in dashboard.py to keep Knowledge Graph, radar, and sidebar in sync.
#
# STRICT 6 PESTEL DIMENSIONS — "INNOVATION" and "SOCIAL_MEDIA" are removed.
# Legacy database entries carrying those deprecated tags are automatically
# remapped to the closest standard PESTEL dimension via _normalize_dimension().
# ---------------------------------------------------------------------------
PESTEL_COLORS = {
    'POLITICAL':     '#e41a1c',  # Red
    'ECONOMIC':      '#377eb8',  # Blue
    'SOCIAL':        '#4daf4a',  # Green
    'TECHNOLOGICAL': '#984ea3',  # Purple
    'ENVIRONMENTAL': '#ff7f00',  # Orange
    'LEGAL':         '#a6761d',  # Amber/brown (changed from #ffff33 to avoid conflict
                                 # with the 24-month ring yellow)
}

# Fallback mapping: legacy tags → nearest strict PESTEL category
_DEPRECATED_DIM_MAP: Dict[str, str] = {
    'INNOVATION':   'TECHNOLOGICAL',  # Innovation signals → Technology quadrant
    'SOCIAL_MEDIA': 'SOCIAL',         # Social media signals → Social quadrant
}


def _normalize_dimension(dim: str) -> str:
    """
    Map a raw dimension string to a valid strict-PESTEL key.

    - Applies the deprecated-tag fallback (INNOVATION → TECHNOLOGICAL, etc.)
    - Falls back to 'TECHNOLOGICAL' for any unknown string to ensure the
      radar never crashes on unexpected data.
    """
    if dim in PESTEL_COLORS:
        return dim
    return _DEPRECATED_DIM_MAP.get(dim, 'TECHNOLOGICAL')


class InnovationRadar:
    """
    Generates interactive Innovation Radar visualizations.

    Ring color semantics (fixed):
        12 months → Red     (act now)
        24 months → Yellow  (pilot phase)
        36 months → Green   (monitor and assess)

    Quadrant layout: 6 strict PESTEL sectors at 60° each.
    """

    # Time-horizon rings with explicit color semantics
    RING_CONFIG = {
        '12_MONTH': {
            'radius': 1.0,
            'label': '12 Month (Immediate)',
            'color': '#d73027',   # Red
            'ui_emoji': '🔴',
        },
        '24_MONTH': {
            'radius': 0.66,
            'label': '24 Month (Pilot)',
            'color': '#fee08b',   # Yellow
            'ui_emoji': '🟡',
        },
        '36_MONTH': {
            'radius': 0.33,
            'label': '36 Month (Monitor)',
            'color': '#1a9850',   # Green
            'ui_emoji': '🟢',
        },
    }

    # Ordered list of the 6 standard PESTEL dimensions for consistent rendering
    ORDERED_DIMS = [
        'POLITICAL', 'ECONOMIC', 'SOCIAL',
        'TECHNOLOGICAL', 'ENVIRONMENTAL', 'LEGAL',
    ]

    def __init__(self) -> None:
        self.rings = self.RING_CONFIG

        # 6 PESTEL sectors at 60° each (360° / 6)
        _sector_size = 60
        self.quadrants = {
            dim: {
                'angle_start': i * _sector_size,
                'angle_end':   (i + 1) * _sector_size,
                'color':       PESTEL_COLORS[dim],
            }
            for i, dim in enumerate(self.ORDERED_DIMS)
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_radar(
        self,
        signals: List[Dict],
        title: str = "European Agriculture Industry Disruption Radar",
    ) -> go.Figure:
        """
        Create Innovation Radar chart from scored signals.

        Deprecated dimension tags (INNOVATION, SOCIAL_MEDIA) in signals are
        silently remapped to their PESTEL equivalent before plotting.

        Args:
            signals: List of scored disruption signals
            title: Chart title

        Returns:
            plotly Figure object
        """
        fig = go.Figure()

        # 1. Quadrant background fills
        for dim, config in self.quadrants.items():
            angles = list(range(config['angle_start'], config['angle_end'] + 1))
            fig.add_trace(go.Scatterpolar(
                r=[1.0] * len(angles) + [0],
                theta=angles + [config['angle_start']],
                fill='toself',
                fillcolor=config['color'],
                opacity=0.08,
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip',
            ))

        # 2. Ring circles (time horizons) — color = classification urgency
        for horizon, config in self.rings.items():
            fig.add_trace(go.Scatterpolar(
                r=[config['radius']] * 360,
                theta=list(range(360)),
                mode='lines',
                line=dict(color=config['color'], width=2),
                opacity=0.75,
                name=config['label'],
                showlegend=True,
            ))

        # 3. Quadrant dividers
        for dim, config in self.quadrants.items():
            angle = config['angle_start']
            fig.add_trace(go.Scatterpolar(
                r=[0, 1.0],
                theta=[angle, angle],
                mode='lines',
                line=dict(color='rgba(0, 204, 255, 0.6)', width=3),
                showlegend=False,
                hoverinfo='skip',
            ))

        # 4. Plot signals
        import random
        for signal in signals:
            raw_dim = signal.get('primary_dimension', 'TECHNOLOGICAL')
            dimension = _normalize_dimension(raw_dim)  # Apply fallback
            horizon = signal.get('time_horizon', '36_MONTH')
            if horizon not in self.rings:
                horizon = '36_MONTH'
            score = signal.get('disruption_score', 0.5)
            title_text = signal.get('title', 'Unknown Signal')
            url = signal.get('url', '')

            quad_config = self.quadrants[dimension]
            angle = random.uniform(
                quad_config['angle_start'] + 5,
                quad_config['angle_end'] - 5,
            )

            base_radius = self.rings[horizon]['radius']
            radius = base_radius + random.uniform(-0.04, 0.04)
            radius = max(0.05, min(1.05, radius))

            marker_size = 12 + (score * 35)   # 12–47 px

            classification = signal.get('classification', 'LOW')
            marker_colors = {
                'CRITICAL': '#ff0066',
                'HIGH':     '#ff9933',
                'MODERATE': '#ffff00',
                'LOW':      '#00ff88',
            }
            marker_color = marker_colors.get(classification, '#999999')

            # Build hover text — never include raw URL to avoid hallucinations
            source_note = f"<br><b>Source:</b> {url[:80]}…" if url else ""
            was_remapped = raw_dim != dimension
            remap_note = f"<br><i>(remapped from {raw_dim})</i>" if was_remapped else ""

            hover = (
                f"<b>{title_text}</b><br>"
                f"<b>Dimension:</b> {dimension}{remap_note}<br>"
                f"<b>Time Horizon:</b> {horizon.replace('_', ' ')}<br>"
                f"<b>Disruption Score:</b> {score:.3f}<br>"
                f"<b>Classification:</b> {classification}"
                f"{source_note}"
            )

            fig.add_trace(go.Scatterpolar(
                r=[radius],
                theta=[angle],
                mode='markers',
                marker=dict(
                    size=marker_size,
                    color=marker_color,
                    line=dict(color='rgba(255, 255, 255, 0.8)', width=2),
                    opacity=0.9,
                ),
                hovertext=hover,
                hoverinfo='text',
                showlegend=False,
                name=title_text,
            ))

        # 5. Angular axis tick labels at sector mid-points
        dims_with_signals = {
            _normalize_dimension(sig.get('primary_dimension', ''))
            for sig in signals
        }
        tick_vals = [i * 60 + 30 for i in range(6)]  # mid-point of each 60° sector
        tick_labels = [
            f'<b>{dim}</b>' if dim in dims_with_signals else dim
            for dim in self.ORDERED_DIMS
        ]

        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0, 0, 0, 0)',
            plot_bgcolor='rgba(0, 0, 0, 0)',
            title=dict(
                text=title,
                font=dict(size=22, family='Arial Black', color='#00ff88'),
            ),
            polar=dict(
                bgcolor='rgba(14, 17, 23, 0.8)',
                radialaxis=dict(
                    visible=True,
                    range=[0, 1.1],
                    showticklabels=False,
                    gridcolor='rgba(255, 255, 255, 0.1)',
                ),
                angularaxis=dict(
                    tickvals=tick_vals,
                    ticktext=tick_labels,
                    tickfont=dict(size=13, family='Arial Black', color='#00ccff'),
                    direction='clockwise',
                    gridcolor='rgba(0, 204, 255, 0.2)',
                ),
            ),
            showlegend=True,
            legend=dict(
                font=dict(size=12, color='#e0e0e0'),
                bgcolor='rgba(0, 0, 0, 0.5)',
                title=dict(text='Time Horizon', font=dict(color='#aaa', size=11)),
            ),
            height=800,
            width=900,
        )

        return fig

    def create_pestel_heatmap(self, signals: List[Dict]) -> go.Figure:
        """
        Create PESTEL disruption heatmap showing signal distribution by dimension and time horizon.

        Deprecated dimension tags are remapped before aggregation.
        """
        # Initialise matrix with strict 6 PESTEL dims only
        matrix = {dim: {'12_MONTH': 0, '24_MONTH': 0, '36_MONTH': 0}
                  for dim in self.ORDERED_DIMS}

        for signal in signals:
            dim = _normalize_dimension(signal.get('primary_dimension', 'TECHNOLOGICAL'))
            horizon = signal.get('time_horizon', '36_MONTH')
            if horizon not in ('12_MONTH', '24_MONTH', '36_MONTH'):
                horizon = '36_MONTH'
            if dim in matrix:
                matrix[dim][horizon] += 1

        horizons = ['12_MONTH', '24_MONTH', '36_MONTH']
        z_values = [[matrix[dim][h] for h in horizons] for dim in self.ORDERED_DIMS]

        fig = go.Figure(data=go.Heatmap(
            z=z_values,
            x=['12 Month (Red)', '24 Month (Yellow)', '36 Month (Green)'],
            y=self.ORDERED_DIMS,
            colorscale='YlOrRd',
            text=z_values,
            texttemplate='%{text}',
            textfont={'size': 16},
            hovertemplate='<b>%{y}</b><br>%{x}: %{z} signals<extra></extra>',
        ))

        fig.update_layout(
            title='PESTEL Disruption Signal Distribution by Time Horizon',
            xaxis_title='Time Horizon',
            yaxis_title='PESTEL Dimension',
            height=500,
            width=700,
        )

        return fig


if __name__ == "__main__":
    sample_signals = [
        {'title': 'EU Battery Swapping Mandate 2027',
         'primary_dimension': 'LEGAL', 'time_horizon': '24_MONTH',
         'disruption_score': 0.85, 'classification': 'CRITICAL'},
        {'title': 'Autonomous Tractor Patent Surge',
         'primary_dimension': 'TECHNOLOGICAL', 'time_horizon': '36_MONTH',
         'disruption_score': 0.72, 'classification': 'HIGH'},
        {'title': 'CAP Subsidy Cuts for Diesel',
         'primary_dimension': 'POLITICAL', 'time_horizon': '12_MONTH',
         'disruption_score': 0.78, 'classification': 'CRITICAL'},
        # Deprecated tag — should remap cleanly
        {'title': 'AgTech Startup Funding Surge',
         'primary_dimension': 'INNOVATION', 'time_horizon': '36_MONTH',
         'disruption_score': 0.65, 'classification': 'HIGH'},
    ]

    radar = InnovationRadar()
    print("Generating Innovation Radar (6 PESTEL dims)...")
    fig = radar.create_radar(sample_signals)
    fig.write_html('q2_solution/outputs/charts/innovation_radar.html')
    print("✓ Saved to: outputs/charts/innovation_radar.html")
