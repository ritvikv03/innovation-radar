# Migration: Brave Search → Tavily

**Date**: March 8, 2026  
**Reason**: Tavily offers a free tier, Brave Search does not

---

## Changes Made

### 1. ✅ Updated `.mcp.json`
**Before**:
```json
"brave-search": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-brave-search"],
  "env": {
    "BRAVE_API_KEY": "${BRAVE_API_KEY}"
  }
}
```

**After**:
```json
"tavily": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-tavily"],
  "env": {
    "TAVILY_API_KEY": "${TAVILY_API_KEY}"
  }
}
```

### 2. ✅ Updated `.env`
Added:
```bash
TAVILY_API_KEY=your_tavily_api_key_here
```

**Action Required**: Replace `your_tavily_api_key_here` with your actual Tavily API key.

### 3. ✅ Updated Scout Agent
**File**: `.claude/agents/scout.md`

**Changes**:
- **Frontmatter tools**: Changed from `mcp__brave-search__brave_web_search` to `mcp__tavily__search`
- **Description**: Updated from "Brave Search" to "Tavily Search"
- **Search examples**: Changed from `brave_web_search()` to `search()` (Tavily's simpler API)

---

## Tavily vs Brave Search

| Feature | Tavily | Brave Search |
|---------|--------|--------------|
| **Free Tier** | ✅ Yes (1,000 requests/month) | ❌ No |
| **Pricing** | $0 → $50/month | Paid only |
| **MCP Server** | ✅ `@modelcontextprotocol/server-tavily` | ✅ `@modelcontextprotocol/server-brave-search` |
| **API Simplicity** | ⭐⭐⭐ Simple | ⭐⭐ More complex |
| **Search Quality** | High (AI-optimized) | High (privacy-focused) |

---

## Setup Instructions

### Step 1: Get Tavily API Key
1. Go to https://tavily.com
2. Sign up for free account
3. Get your API key from dashboard
4. **Free tier**: 1,000 searches/month (plenty for development)

### Step 2: Update `.env`
```bash
# Edit .env file
nano .env

# Replace this line:
TAVILY_API_KEY=your_tavily_api_key_here

# With your actual key:
TAVILY_API_KEY=tvly-your-actual-key-here
```

### Step 3: Load Environment
```bash
# Load .env variables
source <(grep -v '^#' .env | sed 's/^/export /')

# Or use the helper script
./load_env.sh

# Verify
echo $TAVILY_API_KEY
```

### Step 4: Restart Claude Code
Restart Claude Code to load the new Tavily MCP server.

### Step 5: Test Scout Agent
```
Scout, search for recent EU AgTech funding news
```

Scout should use Tavily to find real-time news.

---

## Tool Name Changes

**Scout Agent Tools (Updated)**:
| Old (Brave) | New (Tavily) |
|-------------|--------------|
| `mcp__brave-search__brave_web_search` | `mcp__tavily__search` |
| `mcp__brave-search__brave_local_search` | `mcp__tavily__search` |

**Note**: Tavily has a simpler API with just one `search` tool (vs. Brave's separate web/local tools).

---

## Verification

### Test 1: Environment Variable
```bash
echo $TAVILY_API_KEY
# Should output: tvly-...
```

### Test 2: MCP Configuration
```bash
cat .mcp.json | grep tavily
# Should show Tavily server config
```

### Test 3: Scout Agent Tools
```
Scout, what tools do you have?
```
Expected response should include: `mcp__tavily__search`

### Test 4: Live Search
```
Scout, search for "EU CAP reforms 2026"
```
Should return real-time search results.

---

## Migration Impact

### No Breaking Changes ✅
- All existing functionality preserved
- Database, pipeline, and other agents unaffected
- Only Scout agent search tool changed

### Improved Features ✅
- **Free tier**: No API costs for development
- **Simpler API**: Single `search` tool vs. multiple Brave tools
- **AI-optimized**: Tavily's search is optimized for AI agents

---

## Troubleshooting

### Issue: "TAVILY_API_KEY not set"
**Solution**:
```bash
export TAVILY_API_KEY="tvly-your-key-here"
```

### Issue: Scout can't use Tavily tools
**Solution**:
1. Verify API key is set: `echo $TAVILY_API_KEY`
2. Restart Claude Code
3. Check MCP server logs in Claude Code settings

### Issue: Search returns no results
**Solution**:
- Check API key is valid
- Verify you haven't exceeded free tier limit (1,000/month)
- Try a simpler search query

---

## Documentation Updated

- ✅ `.mcp.json` - Tavily server configured
- ✅ `.env` - TAVILY_API_KEY placeholder added
- ✅ `.claude/agents/scout.md` - Tools and examples updated
- ✅ `TAVILY_MIGRATION.md` - This file

**PHASE2_COMPLETION_SUMMARY.md will be updated to reflect Tavily instead of Brave Search.**

---

**Migration Status**: ✅ Complete  
**Action Required**: Set your Tavily API key in `.env`  
**Impact**: Zero breaking changes, improved free tier availability
