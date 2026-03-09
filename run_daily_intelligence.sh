#!/bin/bash
# Fendt PESTEL-EL Sentinel - Daily Intelligence Sweep
# ====================================================
#
# This script triggers the automated daily intelligence gathering
# using the Claude Code router agent to scan European agricultural news
# across all PESTEL dimensions and update the SQLite database.
#
# Usage:
#   ./run_daily_intelligence.sh
#
# For automated daily runs, add to crontab (see DEPLOYMENT.md)

# Set working directory to script location
cd "$(dirname "$0")"

# Log execution
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_intelligence_$(date +%Y%m%d).log"

echo "========================================" >> "$LOG_FILE"
echo "Daily Intelligence Sweep: $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# Execute the router agent
# This triggers a background execution of the daily intelligence sweep
claude code --agent router "Execute a daily sweep for European Agricultural news across all PESTEL dimensions. Score them and update the SQLite database." >> "$LOG_FILE" 2>&1

# Capture exit status
EXIT_STATUS=$?

if [ $EXIT_STATUS -eq 0 ]; then
    echo "✓ Daily intelligence sweep completed successfully at $(date)" >> "$LOG_FILE"
else
    echo "✗ Daily intelligence sweep failed with exit code $EXIT_STATUS at $(date)" >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"

# Keep only last 30 days of logs
find "$LOG_DIR" -name "daily_intelligence_*.log" -type f -mtime +30 -delete

exit $EXIT_STATUS
