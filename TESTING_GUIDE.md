# Phase 4 Testing Guide - Prototype Mode
**Date:** March 8, 2026
**Prerequisites:** No API key required

---

## 🚀 How to Test

### 1. Launch Dashboard
```bash
cd /Users/ritvikvasikarla/Desktop/innovation-radar
streamlit run dashboard.py
```

### 2. Test BLUF AI Narrative (Tab 1)

**Expected Behavior:**
1. Navigate to Tab 1 "Executive Summary"
2. If database has signals, you'll see a blue BLUF box at the top
3. Read the 3-sentence strategic summary
4. Click "🔄 Regenerate AI Narrative" to refresh
5. Verify caption shows "Rule-Based Synthesis (Prototype Mode)"

**What to Check:**
- ✅ BLUF displays without errors
- ✅ Narrative mentions actual signal counts from database
- ✅ PESTEL dimension analysis is accurate
- ✅ Top threat (if CRITICAL signals exist) is named
- ✅ Regenerate button works

**Sample BLUF Output:**
```
Currently tracking 14 disruption signals with 3 CRITICAL and 5 HIGH priority
threats demanding immediate attention. Signals are heavily skewed toward POLITICAL
dimension (43% of total), indicating concentrated regulatory/market pressure in
this area. Velocity indicators show building momentum disruption patterns...
```

---

### 3. Test Conversational Inquisition (Tab 4)

**Expected Behavior:**
1. Navigate to Tab 4 "The Inquisition"
2. Click "🔮 Start New Strategic Session"
3. System generates 3-5 strategic questions
4. Type a response in the chat input
5. Receive a fallback response explaining prototype mode

**What to Check:**
- ✅ Initial strategic questions appear in chat
- ✅ Chat input box is visible
- ✅ Typing and sending a message works
- ✅ Fallback response acknowledges your question
- ✅ Conversation history is retained (scroll up to see previous messages)
- ✅ Caption shows "Conversational AI" explanation

**Sample Interaction:**
```
User: "Assume we can't change diesel roadmap until 2028. How does that affect Question 2?"
Assistant Response (Prototype Mode):
**[Prototype Mode - No API Key]**

I understand your question: "Assume we can't change diesel roadmap until 2028..."

Based on the signals we're tracking, this question relates to trade-offs between
short-term operational constraints and long-term strategic positioning. Key considerations:

1. **Timeline Rigidity Risk**: If infrastructure/technology decisions are locked
   until 2028, we may face accelerated obsolescence if regulatory timelines
   compress faster than anticipated.

2. **Competitor Response Window**: A 2-year delay creates an opening for
   competitors to capture early-adopter markets.

3. **Mitigation Strategies**: Consider parallel-path development, strategic
   partnerships, or modular upgrade paths.

*To enable full conversational AI capabilities, configure ANTHROPIC_API_KEY in .env*
```

---

## ⚠️ Known Prototype Limitations

### Prototype Mode (No API Key)
1. **BLUF Narrative:** Rule-based, not AI-generated
   - Uses mathematical analysis of DB stats
   - Less nuanced than Claude's natural language
   - Still accurate and data-driven

2. **Conversational AI:** Static fallback responses
   - Cannot truly "spar" or explore scenarios
   - Provides generic strategic framework
   - Does not reference specific signal content

3. **Missing Features from Phase 4:**
   - Tab 7: Competitor Radar (not implemented)
   - Proactive Alerting (not implemented)
   - PDF Export (not implemented)
   - Prophet forecasting (not implemented)
   - DoWhy causal validation (not implemented)
   - GDELT integration (not implemented)
   - Neo4j preparation (not implemented)

---

## ✅ What Works Fully (Regardless of API Key)

These features work identically in prototype and production:

1. **Tab 1:** Top-level metrics, Top 3 Critical Disruptions, Time-series velocity chart
2. **Tab 2:** Innovation Radar with dimension filters and dark cyberpunk theme
3. **Tab 3:** Live Signal Feed with search, filters, and CSV export
4. **Tab 5:** Knowledge Graph (Table View + Network Graph with filters)
5. **Tab 6:** Strategic Reports viewer

---

## 🔧 Troubleshooting

### Issue: BLUF shows error
**Solution:** Ensure database has signals. Run `python q2_solution/q2_pipeline.py` first

### Issue: Inquisition shows "No high-priority signals"
**Solution:** Database needs at least 1 CRITICAL or HIGH signal

### Issue: Chat history disappears
**Solution:** This is expected if you refresh the page (session state resets)

### Issue: Want to test with real Claude AI
**Solution:** Get Anthropic API key and add to `.env`:
```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

---

## 📊 Success Criteria

**Phase 4 Prototype is successful if:**
- ✅ Dashboard launches without errors
- ✅ BLUF narrative generates in Tab 1
- ✅ Chat interface works in Tab 4
- ✅ Fallback messages clearly indicate prototype mode
- ✅ All existing tabs (2, 3, 5, 6) still work
- ✅ No crashes or exceptions

---

## 🚀 Next Steps for Production

To upgrade from prototype to production:

1. **Get Anthropic API Key**
   - Sign up at https://console.anthropic.com
   - Generate API key
   - Add to `.env` file

2. **High-Priority Features** (if budget allows):
   - Implement Competitor Radar (Tab 7)
   - Add Proactive Alerting (email/webhook)
   - Implement PDF Export for board decks

3. **Advanced Features** (future phases):
   - Prophet forecasting
   - DoWhy causal validation
   - GDELT global event firehose
   - Neo4j graph database migration

---

**Testing Status:** ✅ READY
**Deployment:** Prototype mode suitable for demos and development
**Production Readiness:** Requires API key for full AI capabilities

---

**Tester Notes:**
- Test both BLUF and Chat in same session
- Try regenerating BLUF multiple times
- Send multiple chat messages to test conversation flow
- Verify all tooltips and help text display correctly

