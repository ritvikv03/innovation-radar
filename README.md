# Fendt PESTEL-EL Sentinel

**Autonomous Strategic Intelligence for AGCO/Fendt**

The Fendt PESTEL-EL Sentinel is a production-ready, multi-agent AI framework designed to monitor, map, and predict macro-environmental trends affecting the agricultural sector. It focuses on the **PESTEL-EL** pillars.

---

## 🏗️ Architecture: The "Relational Brain"

This system builds a **Cross-Impact Knowledge Graph**. It traces causal chains—such as how a new EU ESG law (Legal) impacts input costs (Economic), triggering farmer sentiment shifts (Social).

### 🤖 The Agent Team
Orchestrated by the **Sentinel Python Framework** and executed by **Claude Code**:
*   **Scout**: Gathers raw data from free-tier APIs and web scraping.
*   **Analyst**: Processes data, extracts entities, and updates the Knowledge Graph.
*   **Critic**: Ensures logic and compliance with the **EU Data Act 2026**.
*   **Writer**: Synthesizes graph data into "Risk vs. Opportunity" Strategic Briefs.

---

## 🚀 Getting Started

### Quick Start (Local Development)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   npm install -g @anthropic-ai/claude-code
   ```

2. **Set Environment Variables**:
   ```bash
   export ANTHROPIC_API_KEY="your_api_key_here"
   export FIRECRAWL_API_KEY="your_firecrawl_key_here"  # Optional
   ```

3. **Run the Pipeline**:
   ```bash
   # Run full pipeline once
   python sentinel.py --run-once

   # Run specific agent
   python sentinel.py --agent scout

   # Start autonomous mode (runs every 24 hours)
   python sentinel.py --autonomous 24
   ```

4. **View Dashboard**:
   ```bash
   streamlit run dashboard.py
   ```
   Open http://localhost:8501 in your browser.

### Production Deployment (GitHub Actions)

The system runs autonomously via GitHub Actions. See [.github/workflows/sentinel.yml](.github/workflows/sentinel.yml).

**Setup**:
1. Fork this repository
2. Add secrets in Settings → Secrets → Actions:
   - `ANTHROPIC_API_KEY`
   - `FIRECRAWL_API_KEY` (optional)
3. Enable GitHub Actions
4. Pipeline runs daily at midnight UTC (configurable)

### Documentation

1.  **[CLAUDE.md](CLAUDE.md)**: Technical architecture, agent prompts, security rules, Knowledge Graph logic.
2.  **[authentication.md](authentication.md)**: Claude Code authentication guide (OAuth vs API key).
3.  **[knowledge_graph_schema.md](knowledge_graph_schema.md)**: Detailed node/edge schema reference.

---

## 📊 Core Technology
- **Orchestration**: Production-grade Python ([sentinel.py](sentinel.py)) + GitHub Actions for autonomous daily execution.
- **Dashboard**: Streamlit UI ([dashboard.py](dashboard.py)) with Innovation Radar, Knowledge Graph, and Disruption Alerts.
- **Intelligence**: Claude Code (Agentic CLI) via Claude Pro subscription or API.
- **Relational Data**: NetworkX Python Knowledge Graph ([data/graph.json](data/graph.json)) with temporal decay and entity resolution.
- **Data Sources**:
  - **Legal**: EUR-Lex (EU regulations)
  - **Economic**: Eurostat, FAOSTAT
  - **Innovation**: Espacenet (EPO patents), ArXiv research papers, Crunchbase startups
  - **News/Social**: RSS feeds (AgriPulse, EurActiv, AgFunder), YouTube transcripts
  - **Environmental**: Open-Meteo, Copernicus Climate Data

---

## 📂 Repository Structure
```text
/
├── sentinel.py                      # Production orchestrator (replaces n8n)
├── dashboard.py                     # Streamlit dashboard with Innovation Radar
├── innovation_radar.py              # Thoughtworks-style radar visualization
├── strategy_frameworks.py           # SWOT & Porter's 5 Forces generators
├── graph_utils.py                   # Core Knowledge Graph engine
├── requirements.txt                 # Python dependencies (updated for Q2)
├── .claude/
│   ├── agents/
│   │   ├── scout.md                 # Enhanced with industry sources (patents, startups)
│   │   ├── analyst.md               # Entity extraction & cross-impact analysis
│   │   ├── critic.md                # EU Data Act 2026 compliance validator
│   │   └── writer.md                # Board-level disruption report generator (NEW)
│   └── skills/
│       └── strategist/              # High-level strategic question generator
├── .github/workflows/
│   └── sentinel.yml                 # GitHub Actions autonomous pipeline
├── data/
│   ├── graph.json                   # Knowledge Graph (NetworkX format)
│   └── sentinel_state.json          # Orchestrator state tracking
├── logs/                            # Sentinel operational logs
├── output/
│   ├── briefs/                      # Writer agent strategic reports
│   └── frameworks/                  # SWOT & Porter's analyses
├── raw_ingest/                      # Scout agent collected data
├── CLAUDE.md                        # Technical architecture & rules
├── authentication.md                # Claude Code setup guide
├── knowledge_graph_schema.md        # Graph schema documentation
└── README.md                        # This file
```
