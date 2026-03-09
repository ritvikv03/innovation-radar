# Fendt Strategic Intelligence War Room - User Guide

## 🎯 Overview

The **Fendt PESTEL-EL Sentinel War Room** is an executive-level strategic intelligence dashboard designed for C-suite decision-making. It provides real-time insights into European agricultural disruptions across all PESTEL dimensions.

---

## 🚀 Quick Start

### Launch the War Room

```bash
streamlit run dashboard.py
```

Access at: **http://localhost:8501**

---

## 📊 Dashboard Features

### **Tab 1: Executive Summary** 📊

**Purpose:** High-level strategic overview for quick executive briefings

**Key Metrics:**
- **Total Signals:** Complete count of all monitored disruptions
- **🔴 Critical Count:** Signals requiring immediate C-suite attention
- **🟠 High Count:** Signals in pilot/trial phase
- **Average Impact:** Mean disruption impact score across all signals

**Top 3 Critical Disruptions:**
- Displays the **3 highest-priority** signals based on our mathematical Disruption Score
- Each signal shows:
  - **Impact Score** (0.0-1.0): Market/regulatory impact magnitude
  - **Novelty Score** (0.0-1.0): How unprecedented this signal is
  - **Velocity Score** (0.0-1.0): Temporal momentum (mathematical, not sentiment-based)
- Expandable cards with full source URLs and verbatim quotes (EU Data Act 2026 compliant)

**Use Case:**
*"Present the Executive Summary tab during Monday morning C-suite briefings to highlight the week's most critical threats."*

---

### **Tab 2: Innovation Radar** 🎯

**Purpose:** Interactive visualization of disruption landscape across PESTEL dimensions and time horizons

**Features:**
- **6 PESTEL Quadrants:**
  - Political (0°-60°)
  - Economic (60°-120°)
  - Social (120°-180°)
  - Technological (180°-240°)
  - Environmental (240°-300°)
  - Legal (300°-360°)

- **3 Time Horizon Rings:**
  - 🔴 **12 Month (Inner):** Immediate action required (CRITICAL signals)
  - 🟡 **24 Month (Middle):** Pilot and trial phase (HIGH signals)
  - 🟢 **36 Month (Outer):** Assess and monitor (MODERATE/LOW signals)

- **Interactive Hover:**
  - Hover over any data point to see full signal details
  - Dot size represents composite disruption score

**Use Case:**
*"Use the Innovation Radar during quarterly strategy sessions to visualize where disruption threats are clustering and identify blind spots in Fendt's R&D portfolio."*

---

### **Tab 3: Live Signal Feed** 📡

**Purpose:** Raw data access for deep-dive analysis and custom filtering

**Features:**
- **Full-Text Search:** Search across title, content, and source fields
- **Dimension Filtering:** Multi-select filter by PESTEL dimensions
- **Sortable Columns:** Click any column header to sort
- **CSV Export:** Download filtered data for offline analysis
- **Real-Time Counter:** "Showing X of Y signals"

**Displayed Columns:**
- Title
- PESTEL Dimension
- Disruption Classification (CRITICAL/HIGH/MODERATE/LOW)
- Impact Score
- Novelty Score
- Velocity Score
- Date Ingested
- Source

**Use Case:**
*"Analysts can use the Live Signal Feed to export specific PESTEL dimensions (e.g., only Legal signals) for detailed compliance analysis before board meetings."*

---

### **Tab 4: The Inquisition** ⚔️

**Purpose:** AI-powered strategic questioning to challenge C-suite assumptions and force critical decisions

**How It Works:**
1. **Data Input:** Analyzes all CRITICAL signals currently in the SQLite database
2. **AI Processing:** Uses Anthropic Claude API (claude-3-5-sonnet-20241022) to generate strategic questions
3. **Output:** 3-5 hard-hitting questions designed to:
   - Challenge existing R&D roadmaps
   - Expose strategic blind spots
   - Highlight competitive threats
   - Force resource allocation decisions
   - Question timeline assumptions

**Example Questions:**
- *"If EU mandates electric tractors by 2027, how does Fendt's current diesel-focused R&D avoid obsolescence?"*
- *"Which competitor will exploit this regulatory gap first, and what is Fendt's countermove?"*
- *"With autonomous tractor regulations uncertain, what is Fendt's fallback strategy if Level 4 autonomy is banned in the EU?"*

**Signal Context Viewer:**
- Expandable section showing all critical signals analyzed
- Full transparency into AI reasoning

**Use Case:**
*"At the end of quarterly strategy meetings, use The Inquisition to generate provocative questions that can serve as homework assignments for executive teams before the next board meeting."*

**⚠️ Requirements:**
- Must have at least **1 CRITICAL signal** in database
- Requires `ANTHROPIC_API_KEY` in `.env` file
- Internet connection for API access

---

## 🎨 War Room Design Philosophy

### Premium Dark Theme
- **Background:** `#0e1117` (executive-grade dark)
- **Accent Colors:**
  - Critical alerts: `#ff4b4b` (red)
  - Success states: `#00ff88` (green)
  - Information: `#00ccff` (cyan)

### Executive-Friendly Layout
- **Minimal Scrolling:** Key metrics above the fold
- **Expandable Details:** Click to dive deeper
- **Progressive Disclosure:** Most critical info first, details on demand

---

## 🔄 Data Flow Architecture

```
Daily Cron Job (run_daily_intelligence.sh)
              ↓
      Router Agent
              ↓
  [Scout → PESTEL Analysts → Critic]
              ↓
      SQLite Database
      (q2_solution/data/signals.db)
              ↓
      War Room Dashboard
      (Streamlit with 4 tabs)
              ↓
      The Inquisition
      (Anthropic Claude API)
```

---

## 📈 Typical Executive Workflow

### **Daily Workflow (5 minutes):**
1. Open War Room dashboard
2. Check **Executive Summary** for new critical signals
3. If critical count increased, review Top 3 disruptions
4. Flag any signals requiring immediate team notification

### **Weekly Workflow (15 minutes):**
1. Review **Innovation Radar** for clustering patterns
2. Export relevant signals from **Live Signal Feed** for team distribution
3. Note any shifts in PESTEL dimension distribution

### **Monthly Workflow (30 minutes):**
1. Full review of **Executive Summary** trends
2. Explore **Innovation Radar** for strategic gaps
3. Run **The Inquisition** to generate questions
4. Prepare strategic questions for upcoming board meeting
5. Export all signals for month-over-month analysis

---

## 🛡️ Compliance & Data Provenance

Every signal in the War Room is:
- **Traceable:** Source URL provided (EU Data Act 2026 compliant)
- **Verified:** Exact quotes from original sources (min 10 chars)
- **Timestamped:** ISO 8601 date format
- **Scored:** Mathematical algorithms (not sentiment analysis)

**Temporal Decay:**
- Signals older than 90 days automatically decay in weight
- Ensures fresh, relevant intelligence

---

## 🔧 Troubleshooting

### Dashboard Won't Load
```bash
# Check dependencies
pip list | grep -E "streamlit|pandas|plotly|anthropic"

# Reinstall if needed
pip install streamlit pandas plotly anthropic
```

### No Signals Showing
```bash
# Database is empty (expected for fresh install)
# Run intelligence sweep:
./run_daily_intelligence.sh

# Check database:
ls -lh q2_solution/data/signals.db
```

### The Inquisition Not Working
```bash
# Check API key
echo $ANTHROPIC_API_KEY

# Or check .env file
cat .env | grep ANTHROPIC_API_KEY

# Install anthropic package if missing
pip install anthropic
```

### Database Errors
```bash
# Verify database integrity
python -c "
import sys
sys.path.insert(0, 'q2_solution')
from database import SignalDatabase
db = SignalDatabase()
print(db.get_database_stats())
"
```

---

## 🎯 Key Performance Indicators

Monitor these KPIs in the War Room:

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Total Signals | >50 | 20-50 | <20 |
| Critical Signals | 1-5 | 6-10 | >10 |
| Signal Freshness | <7 days | 7-30 days | >30 days |
| PESTEL Balance | Even distribution | 70% in 2 dimensions | 90% in 1 dimension |

---

## 📞 Support & Documentation

- **Technical Architecture:** See `CLAUDE.md`
- **Deployment Guide:** See `DEPLOYMENT.md`
- **Phase 3 Details:** See `PHASE3_COMPLETION_SUMMARY.md`
- **Quick Start:** See `QUICKSTART.md`

---

## 🏆 Best Practices

1. **Daily Check-Ins:** Review Executive Summary every morning
2. **Weekly Deep Dives:** Explore Innovation Radar for pattern analysis
3. **Monthly Strategy Sessions:** Use The Inquisition to challenge assumptions
4. **Quarterly Exports:** Download all signals for long-term trend analysis
5. **Immediate Alerts:** Share critical signals with relevant teams within 24 hours

---

**© 2026 Fendt Strategic Intelligence**
*Built with Claude Code • Powered by Anthropic AI*
