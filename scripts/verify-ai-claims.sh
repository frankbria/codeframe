#!/bin/bash
# Run this after AI claims task is complete

set -e

echo "🔍 Verifying AI claims..."
echo ""

# Run tests
echo "Running pytest..."
pytest -v --cov --cov-report=term-missing

# Check for skip abuse
echo ""
echo "Checking for @skip abuse..."
if grep -r "@pytest.mark.skip\|@skip" tests/ 2>/dev/null; then
    echo "❌ Found @skip decorators in tests"
    exit 1
fi

# Check coverage
COVERAGE=$(pytest --cov --cov-report=term 2>&1 | grep "TOTAL" | awk '{print $4}' | sed 's/%//')
echo ""
echo "Coverage: ${COVERAGE}%"

if [ "$COVERAGE" -lt 80 ]; then
    echo "❌ Coverage below 80%"
    exit 1
fi

echo ""
echo "✅ All verifications passed"
