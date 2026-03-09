#!/bin/bash
# Phase 4 Quick Validation Test

echo "=== Phase 4 Dashboard Validation ==="
echo ""

echo "1. Checking Python syntax..."
python3 -m py_compile dashboard.py
if [ $? -eq 0 ]; then
    echo "   ✅ dashboard.py syntax valid"
else
    echo "   ❌ Syntax errors found"
    exit 1
fi

echo ""
echo "2. Checking for required imports..."
python3 -c "import streamlit; import pandas; import anthropic; print('   ✅ All imports available')" 2>&1 | grep -E "✅|Error"

echo ""
echo "3. Checking file structure..."
if [ -f "dashboard.py" ]; then echo "   ✅ dashboard.py exists"; fi
if [ -f "graph_utils.py" ]; then echo "   ✅ graph_utils.py exists"; fi
if [ -f "requirements.txt" ]; then echo "   ✅ requirements.txt exists"; fi
if [ -d "q2_solution" ]; then echo "   ✅ q2_solution/ directory exists"; fi
if [ -d "data" ]; then echo "   ✅ data/ directory exists"; fi
if [ -d "outputs/reports" ]; then echo "   ✅ outputs/reports/ directory exists"; fi

echo ""
echo "4. Checking documentation..."
if [ -f "TESTING_GUIDE.md" ]; then echo "   ✅ TESTING_GUIDE.md created"; fi
if [ -f "PHASE4_FINAL_SUMMARY.md" ]; then echo "   ✅ PHASE4_FINAL_SUMMARY.md created"; fi
if [ -f "PHASE4_IMPLEMENTATION_PLAN.md" ]; then echo "   ✅ PHASE4_IMPLEMENTATION_PLAN.md created"; fi

echo ""
echo "5. Checking Phase 4 features in dashboard.py..."
grep -q "generate_bluf_narrative" dashboard.py && echo "   ✅ BLUF function found"
grep -q "st.chat_message" dashboard.py && echo "   ✅ Chat interface found"
grep -q "Rule-Based Synthesis" dashboard.py && echo "   ✅ Prototype mode labels found"

echo ""
echo "=== Validation Complete ==="
echo ""
echo "🚀 Ready to launch! Run: streamlit run dashboard.py"
echo ""
echo "📖 See TESTING_GUIDE.md for detailed test instructions"
echo ""

