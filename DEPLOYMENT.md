# Fendt PESTEL-EL Sentinel - Deployment Guide

This guide explains how to deploy the automated daily intelligence gathering system.

## Overview

The Fendt Sentinel uses a fully automated pipeline that:
1. **Gathers** European agricultural news daily via the Scout agent
2. **Routes** signals to specialized PESTEL analysts
3. **Scores** disruption potential using temporal momentum analysis
4. **Stores** everything in SQLite for dashboard visualization
5. **Surfaces** critical insights via the Streamlit dashboard

---

## Quick Start

### 1. Install Dependencies

```bash
pip install streamlit pandas plotly anthropic
```

### 2. Configure Environment

Ensure your `.env` file contains:

```bash
ANTHROPIC_API_KEY=sk-ant-...  # Required for "The Inquisition" feature
CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true
```

### 3. Launch the Dashboard

```bash
streamlit run dashboard.py
```

The dashboard will be available at `http://localhost:8501`

---

## Automated Daily Intelligence Sweep

### Manual Execution

Run the daily intelligence sweep manually:

```bash
./run_daily_intelligence.sh
```

This executes the router agent, which:
- Searches for European agricultural news
- Classifies signals by PESTEL dimension
- Calculates disruption scores (novelty, impact, velocity)
- Updates the SQLite database at `q2_solution/data/signals.db`

### Automated Daily Execution with Cron

To automate daily intelligence gathering, add the script to your crontab.

#### Step 1: Edit Crontab

```bash
crontab -e
```

#### Step 2: Add Cron Job

Add one of the following lines based on your preferred schedule:

**Run daily at 6:00 AM:**
```cron
0 6 * * * cd /Users/ritvikvasikarla/Desktop/innovation-radar && ./run_daily_intelligence.sh
```

**Run daily at 8:00 PM:**
```cron
0 20 * * * cd /Users/ritvikvasikarla/Desktop/innovation-radar && ./run_daily_intelligence.sh
```

**Run twice daily (6 AM and 6 PM):**
```cron
0 6,18 * * * cd /Users/ritvikvasikarla/Desktop/innovation-radar && ./run_daily_intelligence.sh
```

**Run every Monday at 9:00 AM:**
```cron
0 9 * * 1 cd /Users/ritvikvasikarla/Desktop/innovation-radar && ./run_daily_intelligence.sh
```

#### Step 3: Verify Crontab

Check that the cron job was added successfully:

```bash
crontab -l
```

You should see your scheduled job listed.

---

## Cron Schedule Syntax

```
* * * * * command
│ │ │ │ │
│ │ │ │ └─── Day of week (0-7, where 0 and 7 = Sunday)
│ │ │ └───── Month (1-12)
│ │ └─────── Day of month (1-31)
│ └───────── Hour (0-23)
└─────────── Minute (0-59)
```

### Common Examples:

| Schedule | Cron Expression | Description |
|----------|----------------|-------------|
| Every day at midnight | `0 0 * * *` | Midnight daily sweep |
| Every weekday at 9 AM | `0 9 * * 1-5` | Business days only |
| Every 6 hours | `0 */6 * * *` | Four times per day |
| First day of month at 8 AM | `0 8 1 * *` | Monthly intelligence report |

---

## Monitoring & Logs

### View Execution Logs

Logs are stored in the `logs/` directory:

```bash
# View today's log
cat logs/daily_intelligence_$(date +%Y%m%d).log

# View all recent logs
ls -lh logs/

# Tail the latest log in real-time
tail -f logs/daily_intelligence_$(date +%Y%m%d).log
```

### Log Retention

The script automatically deletes logs older than 30 days to prevent disk bloat.

---

## Dashboard Features

### Tab 1: Executive Summary
- Total signal count
- Critical/High severity breakdown
- Top 10 critical disruptions with full context

### Tab 2: Innovation Radar
- Interactive Plotly polar chart
- Signals positioned by PESTEL dimension and time horizon
- Size represents disruption score magnitude

### Tab 3: Live Signal Feed
- Full searchable/filterable table of all signals
- Export to CSV capability
- Sort by any column

### Tab 4: The Inquisition
- AI-generated strategic questions for C-suite
- Powered by Anthropic Claude API
- Analyzes critical signals to generate hard-hitting questions

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│  run_daily_intelligence.sh (Cron Trigger)                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────────────────────┐
│  Router Agent (.claude/agents/router.md)                    │
│  - Searches European agricultural news (Firecrawl/Brave)    │
│  - Routes signals to specialized PESTEL analysts            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────────────────────┐
│  Specialist Agents (political, economic, social, etc.)      │
│  - Extract entities, themes, quotes                         │
│  - Calculate disruption scores (q2_solution/cli_scorer.py)  │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────────────────────┐
│  SQLite Database (q2_solution/data/signals.db)              │
│  - Temporal momentum tracking                               │
│  - Provenance (source URL, exact quotes)                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard (dashboard.py)                         │
│  - Real-time visualization                                  │
│  - The Inquisition (Anthropic API)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Cron Job Not Running

1. **Check cron service is running:**
   ```bash
   # macOS
   sudo launchctl list | grep cron

   # Linux
   sudo systemctl status cron
   ```

2. **Check cron logs:**
   ```bash
   # macOS
   log show --predicate 'process == "cron"' --last 1h

   # Linux
   grep CRON /var/log/syslog
   ```

3. **Verify absolute paths:**
   Cron runs with minimal environment. Always use absolute paths in crontab.

### Dashboard Not Loading

1. **Check Python dependencies:**
   ```bash
   pip list | grep -E "streamlit|pandas|plotly|anthropic"
   ```

2. **Verify database exists:**
   ```bash
   ls -lh q2_solution/data/signals.db
   ```

3. **Check for errors:**
   ```bash
   streamlit run dashboard.py --logger.level=debug
   ```

### The Inquisition Not Working

1. **Verify API key is set:**
   ```bash
   echo $ANTHROPIC_API_KEY
   ```

2. **Check .env file:**
   ```bash
   cat .env | grep ANTHROPIC_API_KEY
   ```

3. **Ensure anthropic package is installed:**
   ```bash
   pip install anthropic
   ```

---

## Security Considerations

1. **API Key Protection:**
   - Never commit `.env` to version control
   - Add `.env` to `.gitignore`

2. **Database Backups:**
   ```bash
   # Create daily backup
   cp q2_solution/data/signals.db q2_solution/data/signals_backup_$(date +%Y%m%d).db
   ```

3. **Cron Email Notifications:**
   Add `MAILTO=your-email@example.com` at the top of crontab to receive error notifications.

---

## Next Steps

1. **Test the daily sweep manually** before scheduling cron
2. **Monitor the first few automated runs** to ensure stability
3. **Review dashboard daily** for critical disruptions
4. **Run The Inquisition weekly** to generate strategic questions
5. **Export signal data monthly** for long-term analysis

---

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review agent configurations in `.claude/agents/`
- Consult `CLAUDE.md` for architecture details

© 2026 Fendt Strategic Intelligence Team
