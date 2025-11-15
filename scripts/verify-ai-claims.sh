#!/bin/bash
# AI Quality Enforcement - Comprehensive Verification Script
# Run this after AI claims task is complete to verify all quality checks pass

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COVERAGE_THRESHOLD=85

echo "═══════════════════════════════════════════════════════"
echo "  AI Quality Enforcement - Verification"
echo "═══════════════════════════════════════════════════════"
echo ""

# Step 1: Run test suite
echo "Step 1: Running test suite..."
echo "───────────────────────────────────────────────────────"
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
    TEST_OUTPUT=$(pytest -v 2>&1)
    TEST_EXIT=$?
elif [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    TEST_OUTPUT=$(pytest -v 2>&1)
    TEST_EXIT=$?
else
    TEST_OUTPUT=$(pytest -v 2>&1)
    TEST_EXIT=$?
fi

echo "$TEST_OUTPUT"
PASSED_TESTS=$(echo "$TEST_OUTPUT" | grep -oP '\d+(?= passed)' || echo "0")
FAILED_TESTS=$(echo "$TEST_OUTPUT" | grep -oP '\d+(?= failed)' || echo "0")

if [ "$TEST_EXIT" -eq 0 ]; then
    echo -e "${GREEN}✅ Step 1: PASSED${NC} ($PASSED_TESTS tests, 0 failures)"
else
    echo -e "${RED}❌ Step 1: FAILED${NC} ($FAILED_TESTS failures)"
    exit 1
fi
echo ""

# Step 2: Check coverage
echo "Step 2: Checking coverage (threshold: ${COVERAGE_THRESHOLD}%)..."
echo "───────────────────────────────────────────────────────"
COVERAGE_OUTPUT=$(pytest --cov --cov-report=term-missing --cov-fail-under=$COVERAGE_THRESHOLD 2>&1)
COVERAGE_EXIT=$?

echo "$COVERAGE_OUTPUT"
COVERAGE=$(echo "$COVERAGE_OUTPUT" | grep "TOTAL" | awk '{print $4}' | sed 's/%//' || echo "0")

if [ "$COVERAGE_EXIT" -eq 0 ]; then
    echo -e "${GREEN}✅ Step 2: PASSED${NC} ($COVERAGE% coverage, threshold ${COVERAGE_THRESHOLD}%)"
else
    echo -e "${RED}❌ Step 2: FAILED${NC} ($COVERAGE% coverage, threshold ${COVERAGE_THRESHOLD}%)"
    exit 1
fi
echo ""

# Step 3: Check for skip decorator abuse
echo "Step 3: Detecting skip decorator abuse..."
echo "───────────────────────────────────────────────────────"
SKIP_OUTPUT=$(grep -r "@pytest.mark.skip\|@pytest.mark.skipif\|@skip\|@skipif" tests/ 2>/dev/null || echo "")

if [ -z "$SKIP_OUTPUT" ]; then
    echo -e "${GREEN}✅ Step 3: PASSED${NC} (0 skip decorators found)"
else
    echo -e "${YELLOW}⚠️  Skip decorators found:${NC}"
    echo "$SKIP_OUTPUT"
    echo -e "${RED}❌ Step 3: FAILED${NC} (skip decorators detected - use scripts/detect-skip-abuse.py for details)"
    exit 1
fi
echo ""

# Summary
echo "═══════════════════════════════════════════════════════"
echo -e "${GREEN}VERIFICATION RESULT: ✅ ALL CHECKS PASSED${NC}"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Summary:"
echo "  • Tests: $PASSED_TESTS passed, 0 failed"
echo "  • Coverage: $COVERAGE% (threshold $COVERAGE_THRESHOLD%)"
echo "  • Skip decorators: 0 violations"
echo ""
echo "Safe to proceed with commit."
echo ""
