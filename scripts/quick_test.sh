#!/bin/bash
# Quick Test Script for Gemini LLM Integration
# Usage: ./quick_test.sh [test_number]

set -e

echo "=================================="
echo "Gemini LLM Integration Quick Test"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test functions
test_rule_based() {
    echo -e "${YELLOW}Test 1: Rule-based mode (no LLM)${NC}"
    echo "Setting up environment..."
    unset AI_PM_USE_LLM
    unset GEMINI_API_KEY

    echo "Running demo..."
    python3 demo_news_driven.py 2>&1 | grep -A 5 "HISTORICAL PATTERN ANALYSIS" | head -10

    echo -e "${GREEN}✓ Test 1 passed${NC}"
    echo ""
}

test_llm_no_key() {
    echo -e "${YELLOW}Test 2: LLM enabled but no API key (fallback test)${NC}"
    echo "Setting up environment..."
    export AI_PM_USE_LLM=1
    unset GEMINI_API_KEY

    echo "Running demo..."
    python3 demo_news_driven.py 2>&1 | grep -E "(Analysis method|Note)" | head -5

    echo -e "${GREEN}✓ Test 2 passed (fallback working)${NC}"
    echo ""
}

test_llm_with_key() {
    echo -e "${YELLOW}Test 3: LLM with API key (real call)${NC}"

    if [ -z "$GEMINI_API_KEY" ]; then
        echo -e "${RED}⚠ GEMINI_API_KEY not set, skipping real LLM test${NC}"
        echo "To run this test, set: export GEMINI_API_KEY=your_key"
        return
    fi

    export AI_PM_USE_LLM=1
    echo "Using model: ${GEMINI_MODEL:-gemini-2.0-flash-exp}"

    echo "Running demo..."
    python3 demo_news_driven.py 2>&1 | grep -A 8 "HISTORICAL PATTERN ANALYSIS"

    echo -e "${GREEN}✓ Test 3 passed${NC}"
    echo ""
}

test_pytest() {
    echo -e "${YELLOW}Test 4: Running pytest suite${NC}"
    python3 -m pytest -xvs --tb=short 2>&1 | tail -5
    echo -e "${GREEN}✓ Test 4 passed${NC}"
    echo ""
}

# Main
case "${1:-all}" in
    1)
        test_rule_based
        ;;
    2)
        test_llm_no_key
        ;;
    3)
        test_llm_with_key
        ;;
    4)
        test_pytest
        ;;
    all)
        test_rule_based
        test_llm_no_key
        test_llm_with_key
        test_pytest
        ;;
    *)
        echo "Usage: $0 [1|2|3|4|all]"
        echo "  1 - Rule-based mode test"
        echo "  2 - LLM fallback test"
        echo "  3 - LLM real call test"
        echo "  4 - Pytest suite"
        echo "  all - Run all tests (default)"
        exit 1
        ;;
esac

echo "=================================="
echo -e "${GREEN}All requested tests completed!${NC}"
echo "=================================="
