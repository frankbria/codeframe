#!/bin/bash
# AI Quality Enforcement - Comprehensive Verification Script
# Run this after AI claims task is complete to verify all quality checks pass

# Exit codes
EXIT_SUCCESS=0
EXIT_TEST_FAILURE=1
EXIT_COVERAGE_FAILURE=2
EXIT_SKIP_VIOLATION=3
EXIT_QUALITY_FAILURE=4

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
COVERAGE_THRESHOLD=85
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARTIFACTS_DIR="artifacts/verify/${TIMESTAMP}"

# Command-line options
FAIL_FAST=true
RUN_TESTS=true
RUN_COVERAGE=true
RUN_SKIP_CHECK=true
RUN_QUALITY=true
VERBOSE=false

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-fail-fast)
            FAIL_FAST=false
            shift
            ;;
        --skip-tests)
            RUN_TESTS=false
            shift
            ;;
        --skip-coverage)
            RUN_COVERAGE=false
            shift
            ;;
        --skip-quality)
            RUN_QUALITY=false
            shift
            ;;
        --skip-skip-check)
            RUN_SKIP_CHECK=false
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "AI Quality Enforcement - Verification Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-fail-fast      Continue running all checks even if one fails"
            echo "  --skip-tests        Skip test execution"
            echo "  --skip-coverage     Skip coverage check"
            echo "  --skip-quality      Skip code quality checks (black, ruff, mypy)"
            echo "  --skip-skip-check   Skip skip decorator detection"
            echo "  -v, --verbose       Verbose output"
            echo "  -h, --help          Show this help message"
            echo ""
            echo "Artifacts saved to: artifacts/verify/YYYYMMDD_HHMMSS/"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create artifacts directory
mkdir -p "$ARTIFACTS_DIR"

# Initialize results
OVERALL_SUCCESS=true
STEP_RESULTS=()

echo "═══════════════════════════════════════════════════════"
echo "  🔍 AI Quality Enforcement - Comprehensive Verification"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "📁 Artifacts: $ARTIFACTS_DIR"
echo ""

# Activate virtualenv
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
elif [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Step 1: Run test suite
if [ "$RUN_TESTS" = true ]; then
    echo -e "${BLUE}📋 Step 1: Running test suite...${NC}"
    echo "───────────────────────────────────────────────────────"

    START_TIME=$(date +%s)

    # Run pytest with JSON report
    if [ "$VERBOSE" = true ]; then
        pytest -v --json-report --json-report-file="$ARTIFACTS_DIR/test-report.json" 2>&1 | tee "$ARTIFACTS_DIR/test-output.txt"
        TEST_EXIT=${PIPESTATUS[0]}
    else
        pytest -v --json-report --json-report-file="$ARTIFACTS_DIR/test-report.json" > "$ARTIFACTS_DIR/test-output.txt" 2>&1
        TEST_EXIT=$?

        # Show summary
        tail -n 20 "$ARTIFACTS_DIR/test-output.txt"
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    # Parse results
    TEST_OUTPUT=$(cat "$ARTIFACTS_DIR/test-output.txt")
    PASSED_TESTS=$(echo "$TEST_OUTPUT" | grep -oP '\d+(?= passed)' | head -1 || echo "0")
    FAILED_TESTS=$(echo "$TEST_OUTPUT" | grep -oP '\d+(?= failed)' | head -1 || echo "0")

    if [ "$TEST_EXIT" -eq 0 ]; then
        echo -e "${GREEN}✅ Step 1: PASSED${NC} ($PASSED_TESTS tests, 0 failures, ${DURATION}s)"
        STEP_RESULTS+=("✅ Tests: PASSED ($PASSED_TESTS tests)")
    else
        echo -e "${RED}❌ Step 1: FAILED${NC} ($FAILED_TESTS failures)"
        STEP_RESULTS+=("❌ Tests: FAILED ($FAILED_TESTS failures)")
        OVERALL_SUCCESS=false

        if [ "$FAIL_FAST" = true ]; then
            echo ""
            echo -e "${RED}Stopping due to test failures (use --no-fail-fast to continue)${NC}"
            exit $EXIT_TEST_FAILURE
        fi
    fi
    echo ""
fi

# Step 2: Check coverage
if [ "$RUN_COVERAGE" = true ]; then
    echo -e "${BLUE}📊 Step 2: Checking coverage (threshold: ${COVERAGE_THRESHOLD}%)...${NC}"
    echo "───────────────────────────────────────────────────────"

    START_TIME=$(date +%s)

    # Run coverage with HTML report
    pytest --cov --cov-report=term-missing --cov-report=html:"$ARTIFACTS_DIR/coverage-html" --cov-fail-under=$COVERAGE_THRESHOLD > "$ARTIFACTS_DIR/coverage-output.txt" 2>&1
    COVERAGE_EXIT=$?

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    # Show output
    if [ "$VERBOSE" = true ]; then
        cat "$ARTIFACTS_DIR/coverage-output.txt"
    else
        # Show summary lines
        grep -A 20 "TOTAL" "$ARTIFACTS_DIR/coverage-output.txt" || cat "$ARTIFACTS_DIR/coverage-output.txt"
    fi

    # Parse coverage percentage
    COVERAGE=$(grep "TOTAL" "$ARTIFACTS_DIR/coverage-output.txt" | awk '{print $4}' | sed 's/%//' | head -1 || echo "0")

    if [ "$COVERAGE_EXIT" -eq 0 ]; then
        echo -e "${GREEN}✅ Step 2: PASSED${NC} ($COVERAGE% coverage, threshold ${COVERAGE_THRESHOLD}%, ${DURATION}s)"
        echo -e "${CYAN}   HTML report: $ARTIFACTS_DIR/coverage-html/index.html${NC}"
        STEP_RESULTS+=("✅ Coverage: PASSED ($COVERAGE%)")
    else
        echo -e "${RED}❌ Step 2: FAILED${NC} ($COVERAGE% coverage, threshold ${COVERAGE_THRESHOLD}%)"
        STEP_RESULTS+=("❌ Coverage: FAILED ($COVERAGE% < ${COVERAGE_THRESHOLD}%)")
        OVERALL_SUCCESS=false

        if [ "$FAIL_FAST" = true ]; then
            echo ""
            echo -e "${RED}Stopping due to coverage failure (use --no-fail-fast to continue)${NC}"
            exit $EXIT_COVERAGE_FAILURE
        fi
    fi
    echo ""
fi

# Step 3: Check for skip decorator abuse
if [ "$RUN_SKIP_CHECK" = true ]; then
    echo -e "${BLUE}🔍 Step 3: Detecting skip decorator abuse...${NC}"
    echo "───────────────────────────────────────────────────────"

    START_TIME=$(date +%s)

    # Use detect-skip-abuse.py if available
    if [ -f "scripts/detect-skip-abuse.py" ]; then
        python scripts/detect-skip-abuse.py > "$ARTIFACTS_DIR/skip-check.txt" 2>&1
        SKIP_EXIT=$?

        if [ "$VERBOSE" = true ]; then
            cat "$ARTIFACTS_DIR/skip-check.txt"
        fi
    else
        # Fallback to grep
        grep -r "@pytest.mark.skip\|@pytest.mark.skipif\|@skip\|@skipif" tests/ > "$ARTIFACTS_DIR/skip-check.txt" 2>&1
        if [ -s "$ARTIFACTS_DIR/skip-check.txt" ]; then
            SKIP_EXIT=1
        else
            SKIP_EXIT=0
        fi
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    SKIP_COUNT=$(wc -l < "$ARTIFACTS_DIR/skip-check.txt" || echo "0")

    if [ "$SKIP_EXIT" -eq 0 ]; then
        echo -e "${GREEN}✅ Step 3: PASSED${NC} (0 skip decorators found, ${DURATION}s)"
        STEP_RESULTS+=("✅ Skip Check: PASSED (0 violations)")
    else
        echo -e "${YELLOW}⚠️  Skip decorators found:${NC}"
        head -n 10 "$ARTIFACTS_DIR/skip-check.txt"
        echo -e "${RED}❌ Step 3: FAILED${NC} ($SKIP_COUNT skip decorators detected)"
        STEP_RESULTS+=("❌ Skip Check: FAILED ($SKIP_COUNT violations)")
        OVERALL_SUCCESS=false

        if [ "$FAIL_FAST" = true ]; then
            echo ""
            echo -e "${RED}Stopping due to skip violations (use --no-fail-fast to continue)${NC}"
            exit $EXIT_SKIP_VIOLATION
        fi
    fi
    echo ""
fi

# Step 4: Code quality checks
if [ "$RUN_QUALITY" = true ]; then
    echo -e "${BLUE}🎨 Step 4: Running code quality checks...${NC}"
    echo "───────────────────────────────────────────────────────"

    QUALITY_SUCCESS=true
    START_TIME=$(date +%s)

    # Black formatting check
    echo -n "  • Black formatting... "
    black --check . > "$ARTIFACTS_DIR/black-check.txt" 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        QUALITY_SUCCESS=false
    fi

    # Ruff linting
    echo -n "  • Ruff linting... "
    ruff check . > "$ARTIFACTS_DIR/ruff-check.txt" 2>&1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${RED}❌${NC}"
        QUALITY_SUCCESS=false
    fi

    # Mypy type checking (optional - may not be configured)
    if command -v mypy &> /dev/null; then
        echo -n "  • Mypy type checking... "
        mypy . > "$ARTIFACTS_DIR/mypy-check.txt" 2>&1
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅${NC}"
        else
            echo -e "${YELLOW}⚠️${NC}"
            # Don't fail on mypy warnings
        fi
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    if [ "$QUALITY_SUCCESS" = true ]; then
        echo -e "${GREEN}✅ Step 4: PASSED${NC} (all quality checks passed, ${DURATION}s)"
        STEP_RESULTS+=("✅ Quality: PASSED")
    else
        echo -e "${RED}❌ Step 4: FAILED${NC} (quality issues detected)"
        STEP_RESULTS+=("❌ Quality: FAILED")
        OVERALL_SUCCESS=false

        if [ "$FAIL_FAST" = true ]; then
            echo ""
            echo -e "${RED}Stopping due to quality failures (use --no-fail-fast to continue)${NC}"
            exit $EXIT_QUALITY_FAILURE
        fi
    fi
    echo ""
fi

# Step 5: Generate comprehensive report
echo -e "${BLUE}📝 Step 5: Generating verification report...${NC}"
echo "───────────────────────────────────────────────────────"

cat > "$ARTIFACTS_DIR/verification-report.md" << EOF
# 🔍 AI Quality Enforcement - Verification Report

**Date**: $(date '+%Y-%m-%d %H:%M:%S')
**Artifacts**: \`$ARTIFACTS_DIR\`

---

## Summary

EOF

if [ "$OVERALL_SUCCESS" = true ]; then
    cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF
### ✅ VERIFICATION PASSED

All quality checks have passed. The code is ready for commit.

EOF
else
    cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF
### ❌ VERIFICATION FAILED

One or more quality checks failed. Please review the issues below.

EOF
fi

cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF
---

## Detailed Results

EOF

# Add each step result
for result in "${STEP_RESULTS[@]}"; do
    echo "- $result" >> "$ARTIFACTS_DIR/verification-report.md"
done

cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF

---

## Artifacts

EOF

# List artifacts
for artifact in "$ARTIFACTS_DIR"/*; do
    if [ -f "$artifact" ]; then
        filename=$(basename "$artifact")
        echo "- \`$filename\`" >> "$ARTIFACTS_DIR/verification-report.md"
    elif [ -d "$artifact" ]; then
        dirname=$(basename "$artifact")
        echo "- \`$dirname/\` (directory)" >> "$ARTIFACTS_DIR/verification-report.md"
    fi
done

cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF

---

## Next Steps

EOF

if [ "$OVERALL_SUCCESS" = true ]; then
    cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF
1. Review the test results and coverage report
2. Commit your changes with a descriptive message
3. Push to the remote repository

**All checks passed - safe to proceed!** ✅
EOF
else
    cat >> "$ARTIFACTS_DIR/verification-report.md" << EOF
1. Review the failed checks above
2. Fix the issues identified
3. Re-run verification: \`scripts/verify-ai-claims.sh\`
4. Once all checks pass, commit and push

**Please fix the issues before committing.** ❌
EOF
fi

echo -e "${CYAN}   Report saved: $ARTIFACTS_DIR/verification-report.md${NC}"
echo ""

# Summary
echo "═══════════════════════════════════════════════════════"
if [ "$OVERALL_SUCCESS" = true ]; then
    echo -e "${GREEN}VERIFICATION RESULT: ✅ ALL CHECKS PASSED${NC}"
else
    echo -e "${RED}VERIFICATION RESULT: ❌ SOME CHECKS FAILED${NC}"
fi
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Summary:"
for result in "${STEP_RESULTS[@]}"; do
    echo "  $result"
done
echo ""
echo "📁 Artifacts directory: $ARTIFACTS_DIR"
echo "📝 Full report: $ARTIFACTS_DIR/verification-report.md"
echo ""

if [ "$OVERALL_SUCCESS" = true ]; then
    echo -e "${GREEN}✅ Safe to proceed with commit.${NC}"
    echo ""
    exit $EXIT_SUCCESS
else
    echo -e "${RED}❌ Please fix the issues above before committing.${NC}"
    echo ""
    exit $EXIT_TEST_FAILURE
fi
