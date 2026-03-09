# CLAUDE.md: Sentinel Architecture & Project Rules

This document serves as the technical source of truth and operational guide for the Fendt PESTEL-EL Sentinel.

---

## 🎯 Strategic Context
The system is built for AGCO/Fendt to predict agricultural trends by mapping interdependencies in the **PESTEL-EL** framework.

### The 8 Pillars
1.  **Political**: Policies, trade, elections.
2.  **Economic**: Prices, subsidies, interest rates.
3.  **Social**: Sentiment, protests, labor.
4.  **Technological**: R&D, digitalization.
5.  **Environmental**: Climate, weather, emissions.
6.  **Legal**: EU Laws (EUR-Lex), compliance.
7.  **Innovation**: Product launches, patents.
8.  **Social Media**: Influencer trends, viral "buzzwords".

---

## 🤖 Agent Architectures (Native Claude Code)

The Fendt Sentinel has migrated from standalone Python scripts and `n8n` to a **Native Claude Code multi-agent architecture**. Sub-agents are stored in `.claude/agents/` and skills in `.claude/skills/`.

### 1. Scout Agent (`scout.md`)
- **Primary Tool**: Firecrawl MCP Server, Tavily MCP Server.
- **Defense**: Implements rate-limiting and validates live URLs.
- **Target**: Live EU agricultural news, EUR-Lex, Eurostat (SDMX), FAOSTAT, AgriPulse.

### 2. The Router Agent (`router.md` - Phase 2)
- **Role**: Ingests data from the Scout and routes it to specialized PESTEL analysts based on the primary dimension detected.

### 3. PESTEL Analyst Agents (Phase 2 Roadmap)
Instead of a single analyst, the platform utilizes specialized expert analysts stored in `.claude/agents/`:
- `political-analyst.md`, `economic-analyst.md`, `social-analyst.md`
- `tech-analyst.md`, `environmental-analyst.md`, `legal-analyst.md`
- **Primary Tool**: `q2_solution/database.py` (SQLite temporal momentum tracking), `graph_utils.py`.
- **Normalization**: Translates content to English but preserves original quotes.

### 4. Critic Agent (`critic.md`)
- **Primary Tool**: Audit functions via Bash.
- **Compliance**: Enforces **EU Data Act 2026**.
- **Audit**: Every edge must have `source_url` and `exact_quote` (min 10 chars).

### 5. Writer Agent (`writer.md`)
- **Output**: Strategic briefs in Markdown.
- **Logic**: Generates board-ready R&D portfolios based on high disruption scores.

---

## ⚡ Custom Skills & Capabilities

*   **/score-disruption `text`**: A custom Claude Code skill that pipes raw text through `q2_solution/cli_scorer.py` to calculate a mathematical Disruption Score based on Novelty, Impact, and Velocity.
*   **Temporal Velocity Analytics**: Disruption scores factor in mathematical momentum derived from SQLite historical queries, rather than static sentiment analysis.

## 📊 Knowledge Graph Logic (`graph_utils.py`)

*   **Temporal Decay**: 90-day half-life. Edges lose weight daily automatically. Edges < 0.05 are pruned.
*   **Provenance Defense**: No relationship is valid without a source URL and verbatim quote.
*   **Multi-Edge Support**: One pair of nodes can have multiple evidence edges.

---

## 🔐 Security & Operations

### Authentication Method
- **Guide**: See [authentication.md](authentication.md) for full setup instructions.
- **OAuth (Claude Pro)**: Preferred. Free and supports multi-agent `claude code` usage.
- **Mounting**: The host's `~/.claude` is mounted to `/home/node/.claude` (ensure write local permissions).

### Compliance Checklist (EU Data Act 2026)
- **Data Minimization**: No PII allowed.
- **Transparency**: Every claim is traceable to a source.
- **Quality**: Decay ensures stale data doesn't drive decisions.

---

## 🛠️ Development Rules
- **Python**: Use `networkx` for graph operations and `sqlite3` for temporal momentum tracking.
- **MCP Servers**: Live internet access MUST go through configured `.mcp.json` servers (e.g., Firecrawl, Tavily).
- **Documentation**: Don't create new `.md` files in the root. Update `README.md` or `QUICKSTART.md`. Keep the repo clean.