"""
Fendt PESTEL-EL Sentinel Dashboard
====================================

Modern Streamlit dashboard powered by SQLite backend (q2_solution).

**Phase 4 Enterprise Features:**
- BLUF AI Executive Narrative (or rule-based fallback)
- Conversational AI Strategy Sparring (or prototype fallback)

Features 6 tabs:
1. Executive Summary: AI/rule-based BLUF + metrics + critical disruptions
2. Innovation Radar: Interactive Plotly visualization with dimension filters
3. Live Signal Feed: Searchable dataframe of all signals
4. The Inquisition: Conversational AI strategy dialogue (or prototype mode)
5. Knowledge Graph: Causal interdependencies (Table View + Network Graph)
6. Strategic Reports: C-suite markdown briefs viewer

**Prototype Mode:** Works without GEMINI_API_KEY using intelligent fallbacks.
**Production Mode:** Configure API key for full Claude AI capabilities.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
import os
from typing import List, Dict
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Add q2_solution to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT / "q2_solution"))

from database import SignalDatabase
from innovation_radar import InnovationRadar

# ===========================
# PAGE CONFIGURATION
# ===========================
st.set_page_config(
    page_title="Fendt PESTEL-EL Sentinel",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium dark theme
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stApp {
        color: #e0e0e0;
    }
    .metric-card {
        padding: 20px;
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 15px;
    }
    .critical-alert {
        padding: 15px;
        border-left: 4px solid #ff4b4b;
        background: rgba(255, 75, 75, 0.1);
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ===========================
# DATABASE CONNECTION
# ===========================

@st.cache_resource
def get_db():
    """Get cached database connection."""
    return SignalDatabase()

@st.cache_data(ttl=60)  # Cache for 1 minute
def load_all_signals():
    """Load all signals from database."""
    db = get_db()
    return db.get_all_signals()

@st.cache_data(ttl=60)
def get_db_stats():
    """Get database statistics."""
    db = get_db()
    return db.get_database_stats()

# ===========================
# BLUF AI EXECUTIVE NARRATIVE
# ===========================

def generate_bluf_narrative(db_stats: Dict, signals: List[Dict]) -> str:
    """
    Generate Bottom Line Up Front (BLUF) executive narrative.

    Uses Gemini API if available, otherwise generates intelligent rule-based summary.

    Analyzes database statistics and critical signals to produce a 3-sentence
    hard-hitting strategic summary for C-suite consumption.

    Args:
        db_stats: Database statistics from get_database_stats()
        signals: List of all signals from database

    Returns:
        str: 3-sentence BLUF narrative
    """
    api_key = os.getenv("GEMINI_API_KEY")

    # Analyze signal distribution
    df = pd.DataFrame(signals)

    # Count by dimension
    dimension_counts = df['primary_dimension'].value_counts().to_dict()
    top_dimension = max(dimension_counts, key=dimension_counts.get)
    top_dimension_pct = (dimension_counts[top_dimension] / len(df)) * 100

    # Count by severity
    severity_counts = df['disruption_classification'].value_counts().to_dict()
    critical_count = severity_counts.get('CRITICAL', 0)
    high_count = severity_counts.get('HIGH', 0)

    # Calculate average scores
    avg_velocity = df['velocity_score'].mean() if 'velocity_score' in df.columns else 0

    # Get top critical signal
    critical_df = df[df['disruption_classification'] == 'CRITICAL'].sort_values('impact_score', ascending=False)
    top_threat = critical_df.iloc[0]['title'] if len(critical_df) > 0 else None

    # If no API key, use intelligent rule-based fallback
    if not api_key:
        # Sentence 1: Overall status and volume
        sentence1 = f"Currently tracking {db_stats['total_signals']} disruption signals with {critical_count} CRITICAL and {high_count} HIGH priority threats demanding immediate attention."

        # Sentence 2: Dimension analysis
        if top_dimension_pct > 40:
            sentence2 = f"Signals are heavily skewed toward {top_dimension} dimension ({top_dimension_pct:.0f}% of total), indicating concentrated regulatory/market pressure in this area."
        else:
            sentence2 = f"Disruptions are distributed across PESTEL dimensions with {top_dimension} showing highest concentration ({top_dimension_pct:.0f}%)."

        # Sentence 3: Velocity and top threat
        if avg_velocity > 0.6:
            velocity_desc = "rapidly accelerating"
        elif avg_velocity > 0.4:
            velocity_desc = "building momentum"
        else:
            velocity_desc = "emerging gradually"

        if top_threat:
            sentence3 = f"Velocity indicators show {velocity_desc} disruption patterns, with most critical threat identified as: {top_threat[:80]}..."
        else:
            sentence3 = f"Velocity indicators show {velocity_desc} disruption patterns across the intelligence landscape."

        return f"{sentence1} {sentence2} {sentence3}"

    # If API key available, use Claude for more sophisticated analysis
    avg_impact = df['impact_score'].mean() if 'impact_score' in df.columns else 0
    avg_novelty = df['novelty_score'].mean() if 'novelty_score' in df.columns else 0

    # Build context for Claude
    context = f"""
DATABASE STATISTICS:
- Total Signals: {db_stats['total_signals']}
- Date Range: {db_stats['date_range']['earliest']} to {db_stats['date_range']['latest']}

PESTEL DISTRIBUTION:
{chr(10).join(f'- {dim}: {count} signals ({count/db_stats["total_signals"]*100:.1f}%)' for dim, count in dimension_counts.items())}

SEVERITY BREAKDOWN:
{chr(10).join(f'- {severity}: {count}' for severity, count in severity_counts.items())}

AVERAGE SCORES:
- Impact: {avg_impact:.2f} / 1.0
- Velocity: {avg_velocity:.2f} / 1.0 (momentum tracking)
- Novelty: {avg_novelty:.2f} / 1.0

TOP CRITICAL THREAT:
{top_threat}
"""

    # Configure Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = f"""You are a strategic advisor delivering a Bottom Line Up Front (BLUF) briefing to AGCO/Fendt's C-suite.

Analyze the following intelligence data and generate EXACTLY 3 sentences that are:
1. Hard-hitting and direct (no corporate fluff)
2. Action-oriented (highlight what executives need to know NOW)
3. Data-driven (reference specific numbers and trends)

INTELLIGENCE DATA:
{context}

Generate the 3-sentence BLUF now. Do NOT include any preamble, title, or conclusion. ONLY the 3 sentences."""

    try:
        # Call Gemini
        response = model.generate_content(prompt)
        narrative = response.text.strip()
        return narrative

    except Exception as e:
        return f"⚠️ Error generating BLUF narrative: {str(e)}"

# ===========================
# THE INQUISITION - GEMINI API
# ===========================

def generate_strategic_questions(critical_signals: List[Dict]) -> List[str]:
    """
    Generate 3-5 hard-hitting strategic questions for Fendt C-suite
    using Gemini API based on critical signals.

    Args:
        critical_signals: List of critical disruption signals

    Returns:
        List of strategic questions
    """
    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")

    # Prepare signal context
    signal_summaries = []
    for sig in critical_signals[:10]:  # Limit to top 10 to avoid token overflow
        signal_summaries.append(
            f"- {sig['title']} [{sig['primary_dimension']}] "
            f"(Disruption: {sig.get('disruption_classification', 'N/A')}, "
            f"Impact: {sig.get('impact_score', 0):.2f})"
        )

    context = "\n".join(signal_summaries)

    # Configure Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Craft the prompt
    prompt = f"""You are a strategic advisor to AGCO/Fendt's C-suite leadership team.

Based on these CRITICAL disruption signals detected in the European agricultural market:

{context}

Generate 3-5 hard-hitting, aggressive strategic questions that force executive reflection and action. These questions should:
1. Challenge existing R&D roadmaps
2. Expose potential strategic blind spots
3. Highlight competitive threats or regulatory risks
4. Force decisions on resource allocation
5. Question timeline assumptions

Format: Return ONLY the questions, numbered 1-5, no preamble or conclusion.

Example style:
"If EU mandates electric tractors by 2027, how does Fendt's current diesel-focused R&D avoid obsolescence?"
"Which competitor will exploit this regulatory gap first, and what is Fendt's countermove?"

Generate the questions now:"""

    try:
        # Generate response
        questions = []
        response = model.generate_content(prompt)
        response_text = response.text

        # Parse numbered questions
        lines = response_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-')):
                # Remove numbering
                question = line.lstrip('0123456789.-) *').strip()
                if question:
                    questions.append(question)

        return questions if questions else ["No questions generated. Try again."]

    except Exception as e:
        return [f"⚠️ Error generating questions: {str(e)}"]

# ===========================
# MAIN DASHBOARD
# ===========================

st.markdown("""
<div style='text-align: center; padding: 20px; background: linear-gradient(135deg, rgba(0,100,0,0.1) 0%, rgba(0,50,0,0.2) 100%); border-radius: 10px; margin-bottom: 20px;'>
    <h1 style='color: #00ff88; margin: 0;'>🛰️ Fendt PESTEL-EL Sentinel</h1>
    <h3 style='color: #00ccff; margin: 10px 0;'>Strategic Intelligence War Room</h3>
    <p style='color: #999; margin: 0;'>Autonomous Agricultural Disruption Detection for AGCO/Fendt C-Suite</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("System Status")
stats = get_db_stats()

if stats['total_signals'] > 0:
    st.sidebar.metric("Total Signals", stats['total_signals'])

    if stats['date_range']:
        st.sidebar.caption(f"Earliest: {stats['date_range']['earliest']}")
        st.sidebar.caption(f"Latest: {stats['date_range']['latest']}")
else:
    st.sidebar.warning("No signals in database yet.")
    st.sidebar.info("Run the daily intelligence sweep to populate data.")

st.sidebar.markdown("---")
st.sidebar.markdown("**PESTEL Breakdown**")
if stats['signals_per_dimension']:
    for dim, count in stats['signals_per_dimension'].items():
        st.sidebar.caption(f"{dim}: {count}")

# Load signals
signals = load_all_signals()

# ===========================
# TAB LAYOUT
# ===========================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Executive Summary",
    "🎯 Innovation Radar",
    "📡 Live Signal Feed",
    "⚔️ The Inquisition",
    "🕸️ Knowledge Graph",
    "📄 Strategic Reports"
])

# ===========================
# TAB 1: EXECUTIVE SUMMARY
# ===========================

with tab1:
    st.subheader("Executive Summary")

    if not signals:
        st.info("No signals available. Database is empty. Run the daily intelligence sweep.")
    else:
        # ===========================
        # BLUF AI EXECUTIVE NARRATIVE
        # ===========================

        st.markdown("""
        <div style='padding: 20px; background: linear-gradient(135deg, rgba(0,100,200,0.15) 0%, rgba(0,50,100,0.2) 100%); border-left: 4px solid #00ccff; border-radius: 10px; margin-bottom: 25px;'>
            <h3 style='color: #00ccff; margin: 0 0 10px 0;'>🎯 Bottom Line Up Front (BLUF)</h3>
        </div>
        """, unsafe_allow_html=True)

        # Generate or retrieve BLUF from session state
        if 'bluf_narrative' not in st.session_state or st.button("🔄 Regenerate AI Narrative", help="Click to generate a fresh AI analysis of current intelligence data"):
            with st.spinner("Generating AI executive narrative..."):
                st.session_state.bluf_narrative = generate_bluf_narrative(stats, signals)

        # Display BLUF with help tooltip
        st.markdown(
            f"""
            <div style='font-size: 18px; line-height: 1.8; color: #e0e0e0; padding: 15px; background: rgba(0,0,0,0.3); border-radius: 8px; margin-bottom: 25px;'>
                {st.session_state.bluf_narrative}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.caption("ℹ️ **AI-Generated Synthesis:** This narrative is dynamically generated by Gemini analyzing database statistics, PESTEL distribution, severity breakdown, and mathematical disruption scores. It provides a non-technical executive summary of the current threat landscape.")

        st.markdown("---")

        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(signals)

        # Top-level metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Signals", len(signals))

        with col2:
            critical_count = len(df[df['disruption_classification'] == 'CRITICAL'])
            st.metric("🔴 Critical", critical_count)

        with col3:
            high_count = len(df[df['disruption_classification'] == 'HIGH'])
            st.metric("🟠 High", high_count)

        with col4:
            # Average disruption score
            if 'impact_score' in df.columns and df['impact_score'].notna().any():
                avg_impact = df['impact_score'].mean()
                st.metric("Avg Impact", f"{avg_impact:.2f}", help="Average Impact across all ingested signals. This tracks the overall magnitude of industry disruption currently affecting the European agricultural landscape.")
            else:
                st.metric("Avg Impact", "N/A", help="Average Impact across all ingested signals. This tracks the overall magnitude of industry disruption currently affecting the European agricultural landscape.")

        st.markdown("---")

        # Time-Series Velocity Chart
        st.markdown("### 📈 Temporal Velocity Tracking")
        st.caption("**Signal volume over time demonstrates mathematical momentum tracking (not static data)**")

        # Group signals by date and count
        if 'date_ingested' in df.columns:
            df['date_parsed'] = pd.to_datetime(df['date_ingested']).dt.date
            daily_counts = df.groupby('date_parsed').size().reset_index(name='count')
            daily_counts = daily_counts.sort_values('date_parsed')
            
            # Format explicitly as strings to prevent Plotly from rendering continuous sub-second ticks
            daily_counts['date_str'] = daily_counts['date_parsed'].apply(lambda x: x.strftime('%b %d, %Y'))

            if len(daily_counts) > 0:
                # Create Plotly line chart for better aesthetics
                import plotly.graph_objects as go

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=daily_counts['date_str'],
                    y=daily_counts['count'],
                    mode='lines+markers',
                    name='Daily Signals',
                    line=dict(color='#00ff88', width=3),
                    marker=dict(size=8, color='#00ff88', line=dict(color='white', width=1)),
                    hovertemplate='<b>%{x}</b><br>Signals: %{y}<extra></extra>'
                ))

                fig.update_layout(
                    template='plotly_dark',
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    xaxis_title='Date',
                    yaxis_title='Signal Count',
                    height=250,
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis=dict(
                        gridcolor='rgba(255,255,255,0.1)',
                        type='category',
                        tickangle=-45
                    ),
                    yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
                    showlegend=False
                )

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Insufficient data for temporal chart. Need signals from multiple days.")
        else:
            st.warning("date_ingested field not found in signals.")

        st.markdown("---")

        # Critical Disruptions Section
        st.markdown("### 🚨 Top 3 Critical Disruptions")
        st.caption("**Highest-priority signals requiring immediate C-suite attention**")

        critical_signals = df[df['disruption_classification'] == 'CRITICAL'].to_dict('records')

        if critical_signals:
            # Sort by impact score (descending)
            critical_signals.sort(
                key=lambda x: x.get('impact_score', 0) if x.get('impact_score') is not None else 0,
                reverse=True
            )

            # Show top 3 with detailed view
            for i, signal in enumerate(critical_signals[:3]):  # Show top 3
                with st.expander(
                    f"🔴 {signal['title']} [{signal['primary_dimension']}]",
                    expanded=(i < 3)  # Expand first 3
                ):
                    col_a, col_b = st.columns([2, 1])

                    with col_a:
                        st.markdown(f"**Source:** [{signal['source']}]({signal['url']})")
                        st.markdown(f"**Date:** {signal['date_ingested']}")
                        st.caption(signal['content'][:500] + "..." if len(signal['content']) > 500 else signal['content'])

                    with col_b:
                        st.metric(
                            "Impact",
                            f"{signal.get('impact_score', 0):.2f}",
                            help="Impact (0.0-1.0) measures magnitude. Calculated algorithmically based on cross-PESTEL reach (how many dimensions the signal affects) and high-leverage triggers like legal mandates or tech breakthroughs. Crucial for flagging existential industry threats."
                        )
                        st.metric(
                            "Novelty",
                            f"{signal.get('novelty_score', 0):.2f}",
                            help="Novelty (0.0-1.0) measures uniqueness. Calculated via inverse-similarity text matching against historical signals in the SQLite database. Crucial for separating true emerging anomalies from repetitive background noise."
                        )
                        st.metric(
                            "Velocity",
                            f"{signal.get('velocity_score', 0):.2f}",
                            help="Velocity (0.0-1.0) measures acceleration. Derived mathematically by comparing recent 30-day signal volume against the trailing 6-month historical average. Crucial to prove a trend is actively gaining momentum, rather than just being a one-off event."
                        )

            # Show remaining critical signals count
            if len(critical_signals) > 3:
                st.info(f"ℹ️ **{len(critical_signals) - 3} additional critical signals** detected. View all in the Live Signal Feed tab.")
        else:
            st.success("✅ No critical disruptions detected. System is monitoring for emerging threats.")

# ===========================
# TAB 2: INNOVATION RADAR
# ===========================

with tab2:
    st.subheader("Innovation Radar - Industry Disruption Map")

    if not signals:
        st.info("No signals available. Run the daily intelligence sweep to populate the radar.")
    else:
        st.markdown("""
        **Time Horizons:**
        - 🔴 **12 Month**: Immediate action required
        - 🟡 **24 Month**: Pilot and trial phase
        - 🟢 **36 Month**: Assess and monitor

        **Quadrants**: PESTEL dimensions (Political, Economic, Social, Technological, Environmental, Legal)
        """)

        # Dimension filter widget
        df_radar = pd.DataFrame(signals)
        available_dimensions = sorted(df_radar['primary_dimension'].unique().tolist())

        selected_dimensions = st.multiselect(
            "🎛️ Filter by PESTEL Dimension",
            options=available_dimensions,
            default=available_dimensions,
            help="Select which PESTEL dimensions to display on the radar. Deselect to focus on specific areas."
        )

        if not selected_dimensions:
            st.warning("Please select at least one dimension to display the radar.")
        else:
            # Prepare signals for radar
            radar_signals = []
            # Filter signals by selected dimensions
            filtered_signals = [sig for sig in signals if sig['primary_dimension'] in selected_dimensions]

            for sig in filtered_signals:
                # Map disruption classification to time horizon
                classification = sig.get('disruption_classification', 'LOW')
                if classification == 'CRITICAL':
                    horizon = '12_MONTH'
                elif classification == 'HIGH':
                    horizon = '24_MONTH'
                else:
                    horizon = '36_MONTH'

                # Calculate composite disruption score
                impact = sig.get('impact_score', 0) if sig.get('impact_score') is not None else 0
                novelty = sig.get('novelty_score', 0) if sig.get('novelty_score') is not None else 0
                velocity = sig.get('velocity_score', 0) if sig.get('velocity_score') is not None else 0

                disruption_score = (impact * 0.5 + novelty * 0.3 + velocity * 0.2)

                radar_signals.append({
                    'title': sig['title'],
                    'primary_dimension': sig['primary_dimension'],
                    'time_horizon': horizon,
                    'disruption_score': disruption_score,
                    'classification': classification
                })

            # Generate radar
            try:
                radar = InnovationRadar()
                fig = radar.create_radar(radar_signals)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Error generating radar: {str(e)}")
                st.info("Ensure plotly is installed: pip install plotly")

# ===========================
# TAB 3: LIVE SIGNAL FEED
# ===========================

with tab3:
    st.subheader("Live Signal Feed - All Data")

    if not signals:
        st.info("No signals in database. Run the daily intelligence sweep.")
    else:
        df = pd.DataFrame(signals)

        # Search and filter controls
        col_search, col_filter = st.columns([2, 1])

        with col_search:
            search_term = st.text_input("🔍 Search signals (title, content, source)", "")

        with col_filter:
            dimension_filter = st.multiselect(
                "Filter by dimension",
                options=df['primary_dimension'].unique().tolist(),
                default=[]
            )

        # Apply filters
        filtered_df = df.copy()

        if search_term:
            filtered_df = filtered_df[
                filtered_df['title'].str.contains(search_term, case=False, na=False) |
                filtered_df['content'].str.contains(search_term, case=False, na=False) |
                filtered_df['source'].str.contains(search_term, case=False, na=False)
            ]

        if dimension_filter:
            filtered_df = filtered_df[filtered_df['primary_dimension'].isin(dimension_filter)]

        st.caption(f"Showing {len(filtered_df)} of {len(df)} signals")

        # Display configuration
        display_columns = [
            'title', 'primary_dimension', 'disruption_classification',
            'impact_score', 'novelty_score', 'velocity_score',
            'date_ingested', 'source'
        ]

        # Only show columns that exist
        display_columns = [col for col in display_columns if col in filtered_df.columns]

        # Display dataframe
        st.dataframe(
            filtered_df[display_columns].sort_values('date_ingested', ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "title": st.column_config.TextColumn("Title", width="large"),
                "primary_dimension": st.column_config.TextColumn("Dimension", width="small"),
                "disruption_classification": st.column_config.TextColumn("Severity", width="small"),
                "impact_score": st.column_config.NumberColumn(
                    "Impact",
                    format="%.2f",
                    help="Impact (0.0-1.0) measures magnitude. Calculated algorithmically based on cross-PESTEL reach (how many dimensions the signal affects) and high-leverage triggers like legal mandates or tech breakthroughs. Crucial for flagging existential industry threats."
                ),
                "novelty_score": st.column_config.NumberColumn(
                    "Novelty",
                    format="%.2f",
                    help="Novelty (0.0-1.0) measures uniqueness. Calculated via inverse-similarity text matching against historical signals in the SQLite database. Crucial for separating true emerging anomalies from repetitive background noise."
                ),
                "velocity_score": st.column_config.NumberColumn(
                    "Velocity",
                    format="%.2f",
                    help="Velocity (0.0-1.0) measures acceleration. Derived mathematically by comparing recent 30-day signal volume against the trailing 6-month historical average. Crucial to prove a trend is actively gaining momentum, rather than just being a one-off event."
                ),
            }
        )

        # Export option
        st.download_button(
            label="📥 Download as CSV",
            data=filtered_df.to_csv(index=False),
            file_name=f"fendt_signals_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ===========================
# TAB 4: THE INQUISITION (CONVERSATIONAL AI)
# ===========================

with tab4:
    st.markdown("""
    <div style='text-align: center; padding: 15px; background: rgba(255, 75, 75, 0.1); border-left: 4px solid #ff4b4b; border-radius: 5px; margin-bottom: 20px;'>
        <h2 style='color: #ff4b4b; margin: 0;'>⚔️ The Inquisition</h2>
        <p style='color: #ccc; margin: 5px 0 0 0;'>Conversational AI Strategy Sparring for C-Suite</p>
    </div>
    """, unsafe_allow_html=True)
    st.caption("**Engage in strategic dialogue with Claude. Ask follow-up questions, challenge assumptions, and explore alternative scenarios based on current disruption intelligence.**")

    if not signals:
        st.info("No signals available. Run the daily intelligence sweep first.")
    else:
        df = pd.DataFrame(signals)
        # Accept both CRITICAL and HIGH signals for analysis
        high_priority_signals = df[df['disruption_classification'].isin(['CRITICAL', 'HIGH'])].to_dict('records')

        if not high_priority_signals:
            st.warning("No high-priority signals detected. The Inquisition requires at least one CRITICAL or HIGH signal.")
            st.info("Run the daily intelligence sweep to populate data.")
        else:
            critical_count = len(df[df['disruption_classification'] == 'CRITICAL'])
            high_count = len(df[df['disruption_classification'] == 'HIGH'])
            st.markdown(f"**Analyzing {critical_count} CRITICAL and {high_count} HIGH signals ({len(high_priority_signals)} total)...**")

            # Initialize conversation state
            if 'inquisition_messages' not in st.session_state:
                st.session_state.inquisition_messages = []

            if 'inquisition_initialized' not in st.session_state:
                st.session_state.inquisition_initialized = False

            # Initialize conversation with strategic questions
            if st.button("🔮 Start New Strategic Session", type="primary") or not st.session_state.inquisition_initialized:
                with st.spinner("Consulting Claude for strategic insights..."):
                    questions = generate_strategic_questions(high_priority_signals)

                # Reset conversation
                st.session_state.inquisition_messages = []

                # Add system context
                context_summary = f"I've analyzed {len(high_priority_signals)} high-priority disruption signals ({critical_count} CRITICAL, {high_count} HIGH) across the PESTEL framework for Fendt/AGCO."

                # Format initial message with questions
                initial_message = f"{context_summary}\n\nHere are the critical strategic questions I need you to confront:\n\n"
                for i, question in enumerate(questions, 1):
                    initial_message += f"**{i}. {question}**\n\n"

                initial_message += "How would you like to respond? You can:\n- Answer a specific question\n- Challenge my assumptions\n- Ask for clarification\n- Explore alternative scenarios"

                # Add to conversation history
                st.session_state.inquisition_messages.append({
                    "role": "assistant",
                    "content": initial_message
                })

                st.session_state.inquisition_initialized = True
                st.rerun()

            # Display conversation history
            st.markdown("### 💬 Strategic Dialogue")

            for message in st.session_state.inquisition_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            # Chat input
            if prompt := st.chat_input("Type your response or question (e.g., 'Assume we can't change diesel roadmap until 2028. How does that affect Question 2?')"):
                # Add user message to history
                st.session_state.inquisition_messages.append({
                    "role": "user",
                    "content": prompt
                })

                # Display user message
                with st.chat_message("user"):
                    st.markdown(prompt)

                # Generate Claude response
                with st.chat_message("assistant"):
                    with st.spinner("Claude is thinking..."):
                        try:
                            api_key = os.getenv("GEMINI_API_KEY")
                            genai.configure(api_key=api_key)
                            model = genai.GenerativeModel('gemini-2.5-flash')

                            # Build signal context
                            signal_context = "\n".join([
                                f"- {sig['title']} [{sig['primary_dimension']}] (Impact: {sig.get('impact_score', 0):.2f})"
                                for sig in high_priority_signals[:10]
                            ])

                            # System prompt
                            system_prompt = f"""You are a strategic advisor to AGCO/Fendt's C-suite engaged in a strategic dialogue about agricultural industry disruptions.

CURRENT INTELLIGENCE CONTEXT:
{signal_context}

Your role:
1. Provide hard-hitting, data-driven strategic insights
2. Challenge assumptions and identify blind spots
3. Explore alternative scenarios when asked
4. Reference specific signals and scores in your analysis
5. Be direct and action-oriented"""

                            # Compile context
                            chat_context = f"{system_prompt}\n\n"
                            # Skip the last message which is the current prompt, we will append it explicitly
                            for msg in st.session_state.inquisition_messages[:-1]:
                                chat_context += f"{msg['role'].upper()}: {msg['content']}\n\n"
                            
                            chat_context += f"USER: {prompt}\n\nPlease respond strategically:"

                            response = model.generate_content(chat_context)
                            full_response = response.text

                            st.markdown(full_response)

                            # Add assistant response to history
                            st.session_state.inquisition_messages.append({
                                "role": "assistant",
                                "content": full_response
                            })

                        except Exception as e:
                            st.error(f"⚠️ Error generating response: {str(e)}")

            # Show signal context
            with st.expander("📋 View High-Priority Signals Being Analyzed"):
                for sig in high_priority_signals[:10]:
                    st.markdown(f"**{sig['title']}** [{sig['primary_dimension']}]")
                    st.caption(f"Impact: {sig.get('impact_score', 0):.2f} | Source: {sig['source']}")
                    st.markdown("---")

# ===========================
# TAB 5: KNOWLEDGE GRAPH
# ===========================

with tab5:
    st.markdown("""
    <div style='text-align: center; padding: 15px; background: rgba(0, 255, 136, 0.1); border-left: 4px solid #00ff88; border-radius: 5px; margin-bottom: 20px;'>
        <h2 style='color: #00ff88; margin: 0;'>🕸️ Knowledge Graph</h2>
        <p style='color: #ccc; margin: 5px 0 0 0;'>Causal Interdependencies Across PESTEL Dimensions</p>
    </div>
    """, unsafe_allow_html=True)

    st.caption("**The Knowledge Graph maps ripple effects between PESTEL dimensions. Choose your preferred view below.**")

    graph_path = Path('./data/graph.json')

    if not graph_path.exists():
        st.warning("⚠️ Knowledge Graph not yet initialized. No causal relationships have been mapped.")
        st.info("The Graph is populated by the Analyst agents during the intelligence pipeline execution.")
    else:
        try:
            import json
            import networkx as nx

            # Load graph
            with open(graph_path, 'r') as f:
                graph_data = json.load(f)

            G = nx.node_link_graph(graph_data)

            # Display stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Nodes (Entities)", G.number_of_nodes(), help="Nodes represent distinct entities derived from the intelligence feed. A node can be a regulatory policy, an economic shift, a specific technology, or a physical environment change. The more nodes tracked, the broader our horizon scanning.")
            with col2:
                st.metric("Edges (Relationships)", G.number_of_edges(), help="Edges represent the mathematical links connecting two distinct nodes. This explicitly tracks how one event (e.g., a Political change) ripples out to trigger another event (e.g., an Economic cost).")
            with col3:
                if G.number_of_edges() > 0:
                    avg_weight = sum([attrs.get('weight', 0) for _, _, attrs in G.edges(data=True)]) / G.number_of_edges()
                    st.metric("Avg Edge Weight", f"{avg_weight:.2f}", help="Weight (-1.0 to 1.0) measures the strength of the causal ripple. Positive values accelerate or amplify a trend. Negative values decelerate, regulate, or restrict a trend.")
                else:
                    st.metric("Avg Edge Weight", "N/A", help="Weight (-1.0 to 1.0) measures the strength of the causal ripple. Positive values accelerate or amplify a trend. Negative values decelerate, regulate, or restrict a trend.")

            st.markdown("---")

            # View selection
            view_mode = st.radio(
                "📊 Visualization Mode",
                ["📋 Table View (Recommended)", "🕸️ Network Graph"],
                help="Table View is clearer for large graphs. Network Graph shows spatial relationships."
            )

            if view_mode == "📋 Table View (Recommended)":
                st.markdown("### Causal Relationships")
                st.caption("**Each row shows one causal link. Read as: Source → Relationship → Target**")

                causality_data = []
                for source, target, attrs in G.edges(data=True):
                    source_label = G.nodes[source].get('label', source)
                    source_cat = G.nodes[source].get('category', 'N/A')
                    target_label = G.nodes[target].get('label', target)
                    target_cat = G.nodes[target].get('category', 'N/A')

                    relationship = attrs.get('relationship', 'RELATES_TO')
                    weight = attrs.get('weight', 0.0)
                    quote = attrs.get('exact_quote', 'N/A')
                    source_url = attrs.get('source_url', 'N/A')

                    causality_data.append({
                        'Source': f"{source_label} [{source_cat}]",
                        'Relationship': relationship,
                        'Target': f"{target_label} [{target_cat}]",
                        'Weight': weight,
                        'Effect': '🟢 Positive' if weight > 0 else '🔴 Negative' if weight < 0 else '⚪ Neutral',
                        'Evidence Quote': quote[:100] + '...' if len(quote) > 100 else quote,
                        'Source URL': source_url
                    })

                causality_df = pd.DataFrame(causality_data)
                causality_df['abs_weight'] = causality_df['Weight'].abs()
                causality_df = causality_df.sort_values('abs_weight', ascending=False).drop('abs_weight', axis=1)

                st.dataframe(
                    causality_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Source": st.column_config.TextColumn("📍 Source Node", width="medium"),
                        "Relationship": st.column_config.TextColumn("⚡ Causal Verb", width="small"),
                        "Target": st.column_config.TextColumn("🎯 Target Node", width="medium"),
                        "Weight": st.column_config.NumberColumn("📊 Weight", format="%.2f", width="small"),
                        "Effect": st.column_config.TextColumn("↗️ Effect Type", width="small"),
                        "Evidence Quote": st.column_config.TextColumn("📜 Quote", width="large"),
                        "Source URL": st.column_config.LinkColumn("🔗 Source", width="medium")
                    }
                )

                st.download_button(
                    label="📥 Download Causality Table as CSV",
                    data=causality_df.to_csv(index=False),
                    file_name=f"knowledge_graph_causality_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

            else:
                from pyvis.network import Network
                import tempfile
                import streamlit.components.v1 as components

                st.markdown("### Interactive Network Visualization")
                st.caption("**Drag nodes to explore. Click for details. Arrows show causality direction.**")

                col_filter1, col_filter2 = st.columns(2)

                with col_filter1:
                    min_weight = st.slider(
                        "Minimum Edge Weight (Strength)",
                        min_value=0.0,
                        max_value=1.0,
                        value=0.1,
                        step=0.1,
                        help="Filter out weak relationships to reduce clutter"
                    )

                with col_filter2:
                    all_categories = set()
                    for _, attrs in G.nodes(data=True):
                        all_categories.add(attrs.get('category', 'UNKNOWN'))

                    selected_categories = st.multiselect(
                        "Filter by PESTEL Dimension",
                        options=sorted(all_categories),
                        default=sorted(all_categories),
                        help="Show only nodes from selected dimensions"
                    )

                net = Network(
                    height='650px',
                    width='100%',
                    bgcolor='#0e1117',
                    font_color='#ffffff',
                    directed=True
                )

                net.barnes_hut(
                    gravity=-10000,
                    central_gravity=0.1,
                    spring_length=250,
                    spring_strength=0.001,
                    damping=0.5
                )

                category_colors = {
                    'POLITICAL': '#e41a1c',
                    'ECONOMIC': '#377eb8',
                    'SOCIAL': '#4daf4a',
                    'TECHNOLOGICAL': '#984ea3',
                    'ENVIRONMENTAL': '#ff7f00',
                    'LEGAL': '#ffff33'
                }

                visible_nodes = set()
                for node_id, attrs in G.nodes(data=True):
                    category = attrs.get('category', 'UNKNOWN')

                    if category not in selected_categories:
                        continue

                    label = attrs.get('label', node_id)
                    color = category_colors.get(category, '#999999')

                    display_label = label[:30] + '...' if len(label) > 30 else label

                    net.add_node(
                        node_id,
                        label=display_label,
                        title=f"<b>{label}</b><br>{category}",
                        color=color,
                        size=35,
                        font={'size': 18, 'color': '#ffffff', 'face': 'arial', 'bold': True}
                    )
                    visible_nodes.add(node_id)

                for source, target, attrs in G.edges(data=True):
                    if source not in visible_nodes or target not in visible_nodes:
                        continue

                    weight = attrs.get('weight', 0.0)

                    if abs(weight) < min_weight:
                        continue

                    relationship = attrs.get('relationship', 'RELATES_TO')

                    if weight > 0.5:
                        edge_color = '#00ff88'
                    elif weight > 0:
                        edge_color = '#00ccff'
                    elif weight < -0.5:
                        edge_color = '#ff0066'
                    elif weight < 0:
                        edge_color = '#ff9933'
                    else:
                        edge_color = '#999999'

                    net.add_edge(
                        source,
                        target,
                        title=f"{relationship} (weight: {weight:.2f})",
                        color=edge_color,
                        width=abs(weight) * 5,
                        arrows={'to': {'enabled': True, 'scaleFactor': 1.5}}
                    )

                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.html') as f:
                    net.save_graph(f.name)
                    with open(f.name, 'r') as html_file:
                        html_content = html_file.read()

                    components.html(html_content, height=670, scrolling=False)

                st.markdown("---")
                st.markdown("### 🎨 Edge Color Legend")
                col_l1, col_l2, col_l3, col_l4 = st.columns(4)

                with col_l1:
                    st.markdown("🟢 **Strong Positive** (Weight > 0.5)")
                with col_l2:
                    st.markdown("🔵 **Moderate Positive** (Weight 0 to 0.5)")
                with col_l3:
                    st.markdown("🟠 **Moderate Negative** (Weight -0.5 to 0)")
                with col_l4:
                    st.markdown("🔴 **Strong Negative** (Weight < -0.5)")

        except ImportError as e:
            st.error(f"⚠️ Required libraries not installed: {str(e)}")
            st.info("Run: `pip install pyvis networkx`")
        except Exception as e:
            st.error(f"Error loading Knowledge Graph: {str(e)}")

# ===========================
# TAB 6: STRATEGIC REPORTS
# ===========================

with tab6:
    st.markdown("""
    <div style='text-align: center; padding: 15px; background: rgba(0, 204, 255, 0.1); border-left: 4px solid #00ccff; border-radius: 5px; margin-bottom: 20px;'>
        <h2 style='color: #00ccff; margin: 0;'>📄 Strategic Output Reports</h2>
        <p style='color: #ccc; margin: 5px 0 0 0;'>C-Suite Markdown Briefs & Board Presentations</p>
    </div>
    """, unsafe_allow_html=True)

    st.caption("**The Writer agent generates executive-ready strategic briefs in Markdown format. These reports synthesize disruption signals into actionable R&D recommendations.**")

    reports_dir = Path('./outputs/reports')

    if not reports_dir.exists() or not any(reports_dir.glob('*.md')):
        st.warning("⚠️ No strategic reports found.")
        st.info("Reports are automatically generated by the Writer agent during pipeline execution. Check `outputs/reports/` directory.")

        if reports_dir.exists():
            st.code(f"Report directory exists but is empty: {reports_dir}")
        else:
            st.code(f"Report directory not created yet: {reports_dir}")
    else:
        report_files = sorted(reports_dir.glob('*.md'), key=lambda x: x.stat().st_mtime, reverse=True)

        if report_files:
            report_names = [f.name for f in report_files]
            selected_report = st.selectbox(
                "📋 Select Report to View",
                options=report_names,
                help="Reports are sorted by modification time (newest first)"
            )

            selected_file = reports_dir / selected_report

            col1, col2 = st.columns(2)
            with col1:
                st.caption(f"**File:** {selected_report}")
            with col2:
                mod_time = datetime.fromtimestamp(selected_file.stat().st_mtime)
                st.caption(f"**Last Modified:** {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")

            st.markdown("---")

            try:
                with open(selected_file, 'r', encoding='utf-8') as f:
                    report_content = f.read()

                st.markdown(report_content, unsafe_allow_html=True)

                st.markdown("---")
                st.download_button(
                    label="📥 Download Report as Markdown",
                    data=report_content,
                    file_name=selected_report,
                    mime="text/markdown"
                )

            except Exception as e:
                st.error(f"Error reading report: {str(e)}")
        else:
            st.warning("No markdown reports found in outputs/reports/")

# ===========================
# FOOTER
# ===========================

st.sidebar.markdown("---")
st.sidebar.caption("© 2026 Fendt Strategic Intelligence")
st.sidebar.caption("Powered by Claude Code & SQLite")
