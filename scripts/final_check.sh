#!/bin/bash
# Final Integration Check Script
# This script performs a comprehensive check of the Gemini LLM integration

set -e

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║         Gemini LLM Integration - Final Check                      ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Checking Core Files"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check core files exist
for file in "strategies/ai_pm.py" "news_replay.py" "demo_news_driven.py"; do
    if [ -f "$file" ]; then
        check_pass "File exists: $file"
    else
        check_fail "File missing: $file"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Checking Documentation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check documentation files
for file in "SUMMARY.md" "CHANGES.md" "TEST_GUIDE.md" "QUICK_REFERENCE.md" "README_INTEGRATION.md" "DELIVERY.md"; do
    if [ -f "$file" ]; then
        check_pass "Documentation: $file"
    else
        check_fail "Documentation missing: $file"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Checking Tools"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check tool files
for file in "verify_integration.py" "demo_runner.py" "quick_test.sh"; do
    if [ -f "$file" ]; then
        check_pass "Tool exists: $file"
    else
        check_fail "Tool missing: $file"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Checking SDK Migration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for old SDK
if grep -r "google.generativeai" strategies/ai_pm.py news_replay.py 2>/dev/null | grep -v "^#" | grep "import google.generativeai" >/dev/null; then
    check_fail "Old SDK (google.generativeai) still present"
else
    check_pass "Old SDK removed"
fi

# Check for new SDK
if grep -r "import google.genai" strategies/ai_pm.py news_replay.py >/dev/null; then
    check_pass "New SDK (google.genai) imported"
else
    check_fail "New SDK not found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Checking Model Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check GEMINI_MODEL configuration
if grep "GEMINI_MODEL" strategies/ai_pm.py >/dev/null && grep "GEMINI_MODEL" news_replay.py >/dev/null; then
    check_pass "GEMINI_MODEL configured in both files"
else
    check_fail "GEMINI_MODEL not configured"
fi

# Check default model
if grep "gemini-2.0-flash-exp" strategies/ai_pm.py >/dev/null; then
    check_pass "Default model: gemini-2.0-flash-exp"
else
    check_warn "Default model not gemini-2.0-flash-exp"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. Checking Response Parsing"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for robust response parsing
if grep "hasattr(response, 'text')" strategies/ai_pm.py >/dev/null && grep "hasattr(response, 'candidates')" strategies/ai_pm.py >/dev/null; then
    check_pass "Robust response parsing in ai_pm.py"
else
    check_fail "Response parsing not updated in ai_pm.py"
fi

if grep "hasattr(response, 'text')" news_replay.py >/dev/null && grep "hasattr(response, 'candidates')" news_replay.py >/dev/null; then
    check_pass "Robust response parsing in news_replay.py"
else
    check_fail "Response parsing not updated in news_replay.py"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "7. Checking Error Handling"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check for error truncation
if grep "\[:100\]" strategies/ai_pm.py >/dev/null || grep "\[:80\]" strategies/ai_pm.py >/dev/null; then
    check_pass "Error truncation in ai_pm.py"
else
    check_warn "Error truncation not found in ai_pm.py"
fi

if grep "\[:100\]" news_replay.py >/dev/null || grep "\[:80\]" news_replay.py >/dev/null; then
    check_pass "Error truncation in news_replay.py"
else
    check_warn "Error truncation not found in news_replay.py"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "8. Checking Python Syntax"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check Python syntax
for file in "strategies/ai_pm.py" "news_replay.py" "demo_news_driven.py" "verify_integration.py" "demo_runner.py"; do
    if python3 -m py_compile "$file" 2>/dev/null; then
        check_pass "Syntax OK: $file"
    else
        check_fail "Syntax error: $file"
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "9. Checking Environment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check environment variables
if [ -n "$AI_PM_USE_LLM" ]; then
    if [ "$AI_PM_USE_LLM" = "1" ]; then
        check_pass "AI_PM_USE_LLM=1 (LLM enabled)"
    else
        check_warn "AI_PM_USE_LLM=$AI_PM_USE_LLM (LLM disabled)"
    fi
else
    check_warn "AI_PM_USE_LLM not set (LLM disabled by default)"
fi

if [ -n "$GEMINI_API_KEY" ]; then
    check_pass "GEMINI_API_KEY is set"
else
    check_warn "GEMINI_API_KEY not set (will use rule-based fallback)"
fi

if [ -n "$GEMINI_MODEL" ]; then
    check_pass "GEMINI_MODEL=$GEMINI_MODEL"
else
    check_pass "GEMINI_MODEL not set (will use default: gemini-2.0-flash-exp)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "10. Checking SDK Installation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if SDK is installed
if python3 -c "import google.genai" 2>/dev/null; then
    check_pass "google.genai SDK installed"
else
    check_fail "google.genai SDK not installed"
    echo ""
    echo "  To install: python3 -m pip install --upgrade google-genai"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                         FINAL SUMMARY                              ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

TOTAL=$((PASS + FAIL))
if [ $TOTAL -gt 0 ]; then
    PERCENTAGE=$((PASS * 100 / TOTAL))
else
    PERCENTAGE=0
fi

echo -e "Checks passed: ${GREEN}$PASS${NC}"
echo -e "Checks failed: ${RED}$FAIL${NC}"
echo -e "Success rate:  ${BLUE}$PERCENTAGE%${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ ALL CHECKS PASSED - Integration is ready!                      ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run tests: pytest -xvs"
    echo "  2. Test rule-based: python3 demo_runner.py rule"
    echo "  3. Test LLM: python3 demo_runner.py llm"
    echo "  4. Read docs: cat QUICK_REFERENCE.md"
    echo ""
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ SOME CHECKS FAILED - Please review the output above            ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Please fix the issues and run this script again."
    echo ""
    exit 1
fi
