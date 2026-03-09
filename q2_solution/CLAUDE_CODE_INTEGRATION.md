# Claude Code Integration - Fendt PESTEL-EL Sentinel

This document describes the Claude Code native integrations for the Innovation Radar project.

## ✅ Integration Status

All Claude Code integrations are **fully operational** and ready for use.

| Component | Status | Location |
|-----------|--------|----------|
| Sub-Agents (4) | ✅ Active | `.claude/agents/` |
| Custom Skill | ✅ Active | `.claude/skills/score-disruption/` |
| MCP Server | ✅ Configured | `.mcp.json` |
| CLI Wrapper | ✅ Functional | `q2_solution/cli_scorer.py` |

---

## 🤖 Sub-Agent Architecture

Four specialized agents with proper frontmatter configuration:

### 1. Scout Agent
**File**: [.claude/agents/scout.md](.claude/agents/scout.md)
- **Role**: Web scraping specialist for EUR-Lex, Eurostat, FAOSTAT, AgriPulse
- **Tools**: `mcp__firecrawl__firecrawl_scrape`, `mcp__firecrawl__firecrawl_search`, `mcp__firecrawl__firecrawl_map`
- **Rate Limiting**: 10-second delays between scrapes
- **Output**: RawSignal Pydantic models with mandatory provenance

**Key Features**:
- Targets 4 primary European agricultural data sources
- Implements exponential backoff for HTTP 429 errors
- Preserves original language quotes with English translations
- 100% provenance compliance (source_url + exact_quote ≥10 chars)

### 2. Analyst Agent
**File**: [.claude/agents/analyst.md](.claude/agents/analyst.md)
- **Role**: PESTEL-EL classification and knowledge graph construction
- **Tools**: `read`, `write`, `bash`
- **Entity Resolution**: 85% similarity threshold for node merging
- **Temporal Decay**: 90-day half-life on all edges

**Key Features**:
- Classifies signals across 8 PESTEL-EL dimensions
- Extracts structured entities (regulations, technologies, locations)
- Builds provenance-first knowledge graph using `graph_utils.py`
- Multi-lingual normalization (all nodes in English, quotes preserved)

### 3. Critic Agent
**File**: [.claude/agents/critic.md](.claude/agents/critic.md)
- **Role**: EU Data Act 2026 compliance officer and graph validator
- **Tools**: `read`, `bash`
- **Enforcement**: 6 provenance validation rules
- **Audit**: Daily graph integrity checks

**Key Features**:
- Rejects edges missing source_url or exact_quote
- PII detection (emails, phone numbers, financial identifiers)
- Weight bounds validation (0.0-1.0)
- Temporal consistency checks (no future dates, <365 days old)

**Validation Rules**:
1. ❌ Missing source_url → REJECT
2. ❌ Missing exact_quote → REJECT
3. ❌ Quote <10 chars → REJECT (likely hallucinated)
4. ❌ Invalid URL format → REJECT
5. ❌ Temporal violation → REJECT
6. ❌ Weight out of bounds → REJECT

### 4. Writer Agent
**File**: [.claude/agents/writer.md](.claude/agents/writer.md)
- **Role**: Strategic brief generator for Fendt/AGCO executives
- **Tools**: `read`, `write`, `bash`
- **Output**: Board-ready markdown reports (8-12 pages)
- **Graph Queries**: Central nodes (degree ≥5), high-impact edges (weight >0.6)

**Key Features**:
- Cross-PESTEL disruption maps
- Probability-weighted scenario modeling
- Innovation gap analysis (unmet needs detection)
- M&A opportunity identification
- R&D roadmap alignment recommendations

---

## ⚡ Custom Skill: /score-disruption

**File**: [.claude/skills/score-disruption/SKILL.md](.claude/skills/score-disruption/SKILL.md)

### Usage
```bash
/score-disruption "The EU has just mandated a 40% reduction in synthetic fertilizer use by 2028."
```

### What It Does
Fast disruption scoring (<1s response time) with:
- **Disruption Score**: 0.00-1.00 using (0.35 × Novelty) + (0.40 × Impact) + (0.25 × Velocity)
- **Classification**: CRITICAL/HIGH/MODERATE/LOW
- **Time Horizon**: 12_MONTH/24_MONTH/36_MONTH
- **PESTEL Dimension**: Primary classification across 8 pillars
- **Component Breakdown**: Novelty, Impact, Velocity scores

### Example Output
```
Disruption Score: 0.52 (HIGH)
Time Horizon: 36_MONTH
Primary PESTEL Dimension: LEGAL
Novelty: 0.80 | Impact: 0.42 | Velocity: 0.30
```

### Technical Implementation
- **CLI Wrapper**: [q2_solution/cli_scorer.py](q2_solution/cli_scorer.py)
- **No Model Invocation**: Direct Python execution for speed
- **Imports**: `SignalClassifier`, `DisruptionScorer` from Q2 solution

### Use Cases
1. **Quick Signal Triage**: Validate signals during Scout operations
2. **PESTEL Testing**: Verify classification accuracy
3. **Formula Benchmarking**: Test disruption scoring on edge cases
4. **Graph Validation**: Pre-check signals before Analyst ingestion

---

## 🔧 MCP Tooling: Firecrawl

**File**: [.mcp.json](.mcp.json)

### Configuration
```json
{
  "mcpServers": {
    "firecrawl": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/firecrawl-mcp-server"],
      "env": {
        "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}"
      },
      "description": "Firecrawl MCP Server for EUR-Lex, Eurostat, FAOSTAT, AgriPulse scraping"
    }
  }
}
```

### Setup Instructions

1. **Get Firecrawl API Key**:
   - Sign up at https://firecrawl.dev
   - Copy API key from dashboard

2. **Set Environment Variable**:
   ```bash
   export FIRECRAWL_API_KEY="fc-your-api-key-here"
   ```

   Or add to your shell profile (~/.zshrc, ~/.bashrc):
   ```bash
   echo 'export FIRECRAWL_API_KEY="fc-your-api-key-here"' >> ~/.zshrc
   source ~/.zshrc
   ```

3. **Verify Installation**:
   ```bash
   # Claude Code will automatically install the MCP server on first use
   # The Scout agent has access to these tools:
   # - mcp__firecrawl__firecrawl_scrape
   # - mcp__firecrawl__firecrawl_search
   # - mcp__firecrawl__firecrawl_map
   ```

### Target Sources
Scout agent is configured to scrape:
- **EUR-Lex**: EU legal database (regulations, directives)
- **Eurostat**: SDMX economic data feeds
- **FAOSTAT**: Agricultural statistics
- **AgriPulse**: Industry news and policy analysis

### Rate Limiting
Scout agent implements:
- 10-second delays between requests
- Exponential backoff for HTTP 429 errors (max 60s)
- Respects robots.txt

---

## 🔍 Verification Commands

### 1. List All Sub-Agents
```bash
/agents
```
**Expected Output**: Should show scout, analyst, critic, writer

### 2. Test Custom Skill
```bash
/score-disruption "The EU has just mandated a 40% reduction in synthetic fertilizer use by 2028."
```
**Expected Output**:
```
Disruption Score: 0.52 (HIGH)
Time Horizon: 36_MONTH
Primary PESTEL Dimension: LEGAL
Novelty: 0.80 | Impact: 0.42 | Velocity: 0.30
```

### 3. Test CLI Scorer Directly
```bash
cd q2_solution
python cli_scorer.py "Germany bans diesel agricultural machinery by 2027"
```

### 4. Verify MCP Server (requires API key)
```bash
# In Claude Code chat:
# Ask Scout agent to scrape a test URL
# Example: "Scout, scrape the latest EUR-Lex CAP regulation"
```

---

## 📁 File Structure

```
innovation-radar/
├── .claude/
│   ├── agents/
│   │   ├── scout.md       # Web scraping specialist (Firecrawl)
│   │   ├── analyst.md     # PESTEL classifier + graph builder
│   │   ├── critic.md      # EU Data Act compliance validator
│   │   └── writer.md      # Strategic brief generator
│   └── skills/
│       └── score-disruption/
│           └── SKILL.md   # CLI scoring skill definition
├── .mcp.json              # Firecrawl MCP server config
├── q2_solution/
│   ├── cli_scorer.py      # CLI wrapper for disruption scoring
│   ├── signal_classifier.py
│   ├── disruption_scorer.py
│   └── ...
└── CLAUDE_CODE_INTEGRATION.md  # This file
```

---

## 🎯 Workflow Example

### End-to-End Pipeline

1. **Scout**: Scrape EUR-Lex for new CAP regulation
   ```
   User: "Scout, find the latest EU fertilizer restrictions"
   Scout: [Uses Firecrawl to scrape EUR-Lex]
   Output: RawSignal JSON with source_url and exact_quote
   ```

2. **Quick Validation**: Score the signal
   ```
   User: /score-disruption "EU mandates 40% nitrogen reduction by 2026"
   Output: Disruption Score: 0.68 (HIGH)
   ```

3. **Analyst**: Build knowledge graph
   ```
   User: "Analyst, ingest this signal and update the graph"
   Analyst: [Classifies PESTEL, extracts entities, creates nodes/edges]
   Output: Graph updated with provenance-backed relationships
   ```

4. **Critic**: Validate compliance
   ```
   User: "Critic, audit the last 10 graph updates"
   Critic: [Checks source_url, exact_quote, PII, weight bounds]
   Output: ✅ All edges compliant with EU Data Act 2026
   ```

5. **Writer**: Generate executive brief
   ```
   User: "Writer, create a monthly disruption foresight report"
   Writer: [Queries graph for central nodes, high-impact edges]
   Output: Strategic brief saved to /output/briefs/
   ```

---

## 🚨 Troubleshooting

### Issue: /score-disruption command not found
**Solution**: Restart Claude Code to reload skill definitions

### Issue: Firecrawl MCP errors
**Solution**: Verify `FIRECRAWL_API_KEY` is set:
```bash
echo $FIRECRAWL_API_KEY
```

### Issue: Scout agent can't scrape
**Possible causes**:
1. FIRECRAWL_API_KEY not set
2. MCP server not installed (Claude Code auto-installs on first use)
3. Rate limit exceeded (check Firecrawl dashboard)

### Issue: CLI scorer import errors
**Solution**: Ensure you're in the q2_solution directory:
```bash
cd /Users/ritvikvasikarla/Desktop/innovation-radar/q2_solution
python cli_scorer.py "test signal"
```

---

## 📊 Success Metrics

### Sub-Agents
- **Scout**: 50-100 signals/day, 100% provenance compliance
- **Analyst**: <5% duplicate nodes, 85%+ entity resolution rate
- **Critic**: 85-95% approval rate, zero PII violations
- **Writer**: ≥80% executive engagement, ≥50% action rate

### Custom Skill
- **Response Time**: <1 second
- **Accuracy**: 90%+ PESTEL classification agreement with manual review
- **Usage**: 10-20 scores/day during active research

### MCP Integration
- **Uptime**: 99%+ (dependent on Firecrawl service)
- **Rate Limit Compliance**: Zero HTTP 429 errors
- **Source Diversity**: ≥15 unique domains/week

---

## 🔗 Additional Resources

- **Q2 Solution Documentation**: [q2_solution/README.md](q2_solution/README.md)
- **PESTEL-EL Framework**: [CLAUDE.md](CLAUDE.md)
- **Firecrawl Docs**: https://docs.firecrawl.dev
- **Claude Code Agents**: https://docs.claude.com/claude-code/agents

---

**Last Updated**: March 8, 2026
**Integration Version**: 1.0
**Status**: ✅ Production Ready
