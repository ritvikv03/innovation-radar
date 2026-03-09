#!/bin/bash
# Load environment variables from .env file

set -a
source .env
set +a

echo "✅ Environment variables loaded:"
echo "  FIRECRAWL_API_KEY=${FIRECRAWL_API_KEY:0:10}..."
echo "  CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=$CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
