"""
Innovation Radar Visualization for Q2
======================================

Creates Thoughtworks-style Innovation Radar chart showing:
- Quadrants: PESTEL dimensions
- Rings: Time horizons (12/24/36 months)
- Dots: Individual disruption signals
- Size: Disruption score magnitude
"""

import plotly.graph_objects as go
import math
from typing import List, Dict
import json

# Single source of truth for all PESTEL-EL dimension colors.
# Import this in dashboard.py to keep Knowledge Graph, radar, and sidebar in sync.
PESTEL_COLORS = {
    'POLITICAL':     '#e41a1c',
    'ECONOMIC':      '#377eb8',
    'SOCIAL':        '#4daf4a',
    'TECHNOLOGICAL': '#984ea3',
    'ENVIRONMENTAL': '#ff7f00',
    'LEGAL':         '#ffff33',
    'INNOVATION':    '#00ccff',
    'SOCIAL_MEDIA':  '#ff69b4',
}


class InnovationRadar:
    """
    Generates interactive Innovation Radar visualizations.
    """

    def __init__(self):
        self.rings = {
            '12_MONTH': {'radius': 1.0, 'label': '12 Month', 'color': '#d73027'},
            '24_MONTH': {'radius': 0.66, 'label': '24 Month', 'color': '#fee08b'},
            '36_MONTH': {'radius': 0.33, 'label': '36 Month', 'color': '#1a9850'}
        }

        # 8 PESTEL-EL pillars at 45° each (360° / 8). Colors from PESTEL_COLORS.
        _angles = [0, 45, 90, 135, 180, 225, 270, 315]
        self.quadrants = {
            dim: {'angle_start': _angles[i], 'angle_end': _angles[i] + 45, 'color': PESTEL_COLORS[dim]}
            for i, dim in enumerate(PESTEL_COLORS)
        }

    def create_radar(self, signals: List[Dict], title: str = "European Agriculture Industry Disruption Radar") -> go.Figure:
        """
        Create Innovation Radar chart from scored signals with premium dark cyberpunk aesthetic.

        Args:
            signals: List of scored disruption signals
            title: Chart title

        Returns:
            plotly Figure object
        """
        fig = go.Figure()

        # Add quadrant background fills (transparent cyberpunk aesthetic)
        for quadrant, config in self.quadrants.items():
            angle_start = config['angle_start']
            angle_end = config['angle_end']
            angles = list(range(angle_start, angle_end + 1))

            # Create polygon for quadrant fill
            fig.add_trace(go.Scatterpolar(
                r=[1.0] * len(angles) + [0],
                theta=angles + [angle_start],
                fill='toself',
                fillcolor=config['color'],
                opacity=0.08,
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip'
            ))

        # Add ring circles (time horizons) with glowing effect
        for horizon, config in self.rings.items():
            fig.add_trace(go.Scatterpolar(
                r=[config['radius']] * 360,
                theta=list(range(360)),
                mode='lines',
                line=dict(color='rgba(0, 255, 136, 0.4)', width=2),
                name=config['label'],
                showlegend=True
            ))

        # Add quadrant dividers with glowing lines
        for quadrant, config in self.quadrants.items():
            angle = config['angle_start']
            fig.add_trace(go.Scatterpolar(
                r=[0, 1.0],
                theta=[angle, angle],
                mode='lines',
                line=dict(color='rgba(0, 204, 255, 0.6)', width=3),
                showlegend=False,
                hoverinfo='skip'
            ))

        # Plot signals with glowing markers
        for signal in signals:
            dimension = signal.get('primary_dimension', 'TECHNOLOGICAL')
            horizon = signal.get('time_horizon', '36_MONTH')
            score = signal.get('disruption_score', 0.5)
            title_text = signal.get('title', 'Unknown Signal')

            # Calculate position
            if dimension in self.quadrants:
                quad_config = self.quadrants[dimension]
                # Random angle within quadrant (with some jitter for readability)
                import random
                angle = random.uniform(quad_config['angle_start'] + 5, quad_config['angle_end'] - 5)

                # Ring radius with jitter
                base_radius = self.rings[horizon]['radius']
                radius = base_radius + random.uniform(-0.05, 0.05)

                # Marker size based on disruption score (larger for higher impact)
                marker_size = 12 + (score * 35)  # 12-47 px

                # Color by classification with cyberpunk palette
                classification = signal.get('classification', 'LOW')
                colors = {
                    'CRITICAL': '#ff0066',  # Hot pink
                    'HIGH': '#ff9933',      # Orange
                    'MODERATE': '#ffff00',  # Yellow
                    'LOW': '#00ff88'        # Cyan-green
                }
                marker_color = colors.get(classification, '#999999')

                # Add signal marker with glowing outline
                fig.add_trace(go.Scatterpolar(
                    r=[radius],
                    theta=[angle],
                    mode='markers',
                    marker=dict(
                        size=marker_size,
                        color=marker_color,
                        line=dict(color='rgba(255, 255, 255, 0.8)', width=2),
                        opacity=0.9
                    ),
                    hovertext=f"<b>{title_text}</b><br>"
                             f"<b>Dimension:</b> {dimension}<br>"
                             f"<b>Time Horizon:</b> {horizon.replace('_', ' ')}<br>"
                             f"<b>Math Score:</b> {score:.3f}<br>"
                             f"<b>Classification:</b> {classification}",
                    hoverinfo='text',
                    showlegend=False,
                    name=title_text
                ))

        # Update layout with dark cyberpunk theme
        fig.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(0, 0, 0, 0)',
            plot_bgcolor='rgba(0, 0, 0, 0)',
            title=dict(
                text=title,
                font=dict(size=22, family='Arial Black', color='#00ff88')
            ),
            polar=dict(
                bgcolor='rgba(14, 17, 23, 0.8)',
                radialaxis=dict(
                    visible=True,
                    range=[0, 1.1],
                    showticklabels=False,
                    gridcolor='rgba(255, 255, 255, 0.1)'
                ),
                angularaxis=dict(
                    tickvals=[22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5],
                    ticktext=['<b>POLITICAL</b>', '<b>ECONOMIC</b>', '<b>SOCIAL</b>',
                             '<b>TECHNOLOGICAL</b>', '<b>ENVIRONMENTAL</b>', '<b>LEGAL</b>',
                             '<b>INNOVATION</b>', '<b>SOCIAL MEDIA</b>'],
                    tickfont=dict(size=14, family='Arial Black', color='#00ccff'),
                    direction='clockwise',
                    gridcolor='rgba(0, 204, 255, 0.2)'
                )
            ),
            showlegend=True,
            legend=dict(
                font=dict(size=12, color='#e0e0e0'),
                bgcolor='rgba(0, 0, 0, 0.5)'
            ),
            height=800,
            width=900
        )

        return fig

    def create_pestel_heatmap(self, signals: List[Dict]) -> go.Figure:
        """
        Create PESTEL disruption heatmap showing signal distribution.

        Args:
            signals: List of scored signals

        Returns:
            plotly Figure object
        """
        # Count signals by dimension and horizon
        matrix = {}
        for dimension in self.quadrants.keys():
            matrix[dimension] = {'12_MONTH': 0, '24_MONTH': 0, '36_MONTH': 0}

        for signal in signals:
            dim = signal.get('primary_dimension', 'TECHNOLOGICAL')
            horizon = signal.get('time_horizon', '36_MONTH')
            if dim in matrix:
                matrix[dim][horizon] += 1

        # Prepare data for heatmap
        dimensions = list(self.quadrants.keys())
        horizons = ['12_MONTH', '24_MONTH', '36_MONTH']
        z_values = [[matrix[dim][h] for h in horizons] for dim in dimensions]

        fig = go.Figure(data=go.Heatmap(
            z=z_values,
            x=['12 Month', '24 Month', '36 Month'],
            y=dimensions,
            colorscale='YlOrRd',
            text=z_values,
            texttemplate='%{text}',
            textfont={"size": 16},
            hovertemplate='<b>%{y}</b><br>%{x}: %{z} signals<extra></extra>'
        ))

        fig.update_layout(
            title='PESTEL Disruption Signal Distribution by Time Horizon',
            xaxis_title='Time Horizon',
            yaxis_title='PESTEL Dimension',
            height=500,
            width=700
        )

        return fig


if __name__ == "__main__":
    # Example usage with sample data
    sample_signals = [
        {
            'title': 'EU Battery Swapping Mandate 2027',
            'primary_dimension': 'LEGAL',
            'time_horizon': '24_MONTH',
            'disruption_score': 0.85,
            'classification': 'CRITICAL'
        },
        {
            'title': 'Autonomous Tractor Patent Surge in Germany',
            'primary_dimension': 'TECHNOLOGICAL',
            'time_horizon': '36_MONTH',
            'disruption_score': 0.72,
            'classification': 'HIGH'
        },
        {
            'title': 'CAP Subsidy Cuts for Diesel Equipment',
            'primary_dimension': 'POLITICAL',
            'time_horizon': '12_MONTH',
            'disruption_score': 0.78,
            'classification': 'CRITICAL'
        },
        {
            'title': 'Rising Labor Costs in Eastern Europe',
            'primary_dimension': 'SOCIAL',
            'time_horizon': '12_MONTH',
            'disruption_score': 0.65,
            'classification': 'HIGH'
        },
        {
            'title': 'Carbon Tax on Agricultural Machinery',
            'primary_dimension': 'ENVIRONMENTAL',
            'time_horizon': '24_MONTH',
            'disruption_score': 0.70,
            'classification': 'HIGH'
        },
        {
            'title': 'Fertilizer Price Volatility Due to Gas Prices',
            'primary_dimension': 'ECONOMIC',
            'time_horizon': '12_MONTH',
            'disruption_score': 0.55,
            'classification': 'MODERATE'
        }
    ]

    radar = InnovationRadar()

    # Create Innovation Radar
    print("Generating Innovation Radar...")
    radar_fig = radar.create_radar(sample_signals)
    radar_fig.write_html('/Users/ritvikvasikarla/Desktop/innovation-radar/q2_solution/outputs/charts/innovation_radar.html')
    print("✓ Saved to: outputs/charts/innovation_radar.html")

    # Create PESTEL Heatmap
    print("Generating PESTEL Heatmap...")
    heatmap_fig = radar.create_pestel_heatmap(sample_signals)
    heatmap_fig.write_html('/Users/ritvikvasikarla/Desktop/innovation-radar/q2_solution/outputs/charts/pestel_heatmap.html')
    print("✓ Saved to: outputs/charts/pestel_heatmap.html")

    print("\n" + "=" * 70)
    print("Visualization generation complete!")
    print("Open the HTML files in a browser to view interactive charts.")
    print("=" * 70)
