# TestSprite Integration Guide

**Project:** codeframe
**Date:** 2025-11-21
**Integration Type:** E2E Testing + Unit Test Monitoring

---

## Overview

This guide explains how TestSprite has been integrated into the codeframe project to provide comprehensive test coverage through both E2E browser tests and unit test monitoring.

---

## 🎯 Integration Strategy

### Two-Tier Testing Approach

**Tier 1: Unit Tests (Jest + React Testing Library)**
- **Purpose:** Fast, isolated component and utility testing
- **Scope:** 701 unit tests covering components, hooks, reducers, utilities
- **Execution Time:** ~10 seconds
- **Run Frequency:** Every commit (pre-commit hook)
- **Coverage:** 81.61% overall, 89.29% on components

**Tier 2: E2E Tests (TestSprite + Playwright)**
- **Purpose:** Production scenario validation with real browser
- **Scope:** 20 E2E tests covering critical user workflows
- **Execution Time:** ~15 minutes
- **Run Frequency:** Nightly builds, pre-release validation
- **Coverage:** 100% pass rate on all workflows

---

## 📁 Project Structure

```
codeframe/
├── web-ui/
│   ├── src/                          # Source code
│   ├── __tests__/                    # Unit tests (Jest)
│   │   ├── components/               # Component tests (340+ tests)
│   │   ├── hooks/                    # Hook tests
│   │   ├── lib/                      # Utility tests
│   │   ├── reducers/                 # Reducer tests
│   │   └── integration/              # Integration tests
│   ├── jest.config.js                # Jest configuration
│   └── package.json                  # Test scripts
└── testsprite_tests/                 # TestSprite artifacts
    ├── TC001-TC020.py                # 20 Playwright E2E test scripts
    ├── testsprite_frontend_test_plan.json
    ├── testsprite-mcp-test-report.md # E2E test results
    ├── TESTSPRITE_SUMMARY.md         # E2E execution summary
    ├── UNIT_TEST_SUMMARY.md          # Unit test results
    ├── NEXT_STEPS.md                 # Improvement roadmap
    ├── TESTSPRITE_INTEGRATION_GUIDE.md # This file
    └── tmp/
        ├── code_summary.json         # Codebase analysis
        └── raw_report.md             # Raw E2E results
```

---

## 🚀 Running Tests

### Unit Tests (Local Development)

```bash
cd web-ui

# Run all tests
npm test

# Run tests in watch mode (for development)
npm run test:watch

# Run tests with coverage report
npm run test:coverage

# Run specific test file
npm test ChatInterface.test.tsx

# Run tests matching pattern
npm test -- --testNamePattern="ChatInterface"
```

### E2E Tests (TestSprite)

TestSprite E2E tests run through the TestSprite cloud service and require:
1. Next.js dev server running on port 3000
2. TestSprite CLI installed via npx
3. Internet connection for TestSprite tunnel

**Manual E2E Test Execution:**

```bash
# 1. Start frontend dev server
cd web-ui
npm run dev  # Runs on port 3000

# 2. In another terminal, run TestSprite tests
cd /home/frankbria/projects/codeframe
node /home/frankbria/.npm/_npx/8ddf6bea01b2519d/node_modules/@testsprite/testsprite-mcp/dist/index.js generateCodeAndExecute
```

**Automated E2E Test Execution (Recommended):**

Create a bash script for automated execution:

```bash
#!/bin/bash
# testsprite_tests/run-e2e-tests.sh

echo "🚀 Starting E2E test execution..."

# Start dev server in background
cd web-ui
npm run dev &
DEV_SERVER_PID=$!

# Wait for server to be ready
echo "⏳ Waiting for dev server..."
sleep 10

# Verify server is up
if curl -s http://localhost:3000 > /dev/null; then
    echo "✅ Dev server ready"
else
    echo "❌ Dev server failed to start"
    kill $DEV_SERVER_PID
    exit 1
fi

# Run TestSprite tests
cd ..
node /home/frankbria/.npm/_npx/8ddf6bea01b2519d/node_modules/@testsprite/testsprite-mcp/dist/index.js generateCodeAndExecute

# Stop dev server
kill $DEV_SERVER_PID

echo "✅ E2E tests complete"
```

---

## 📊 Test Coverage Reporting

### Unit Test Coverage

After running `npm run test:coverage`, view detailed coverage report:

```bash
# Terminal summary
cat coverage/lcov-report/index.html

# Open in browser
open coverage/lcov-report/index.html  # Mac
xdg-open coverage/lcov-report/index.html  # Linux
```

**Coverage Thresholds (jest.config.js):**

```javascript
coverageThreshold: {
  './src/components/PRDModal.tsx': { branches: 80, functions: 80, lines: 80, statements: 80 },
  './src/components/TaskTreeView.tsx': { branches: 80, functions: 80, lines: 80, statements: 80 },
  './src/components/ProgressBar.tsx': { branches: 80, functions: 80, lines: 80, statements: 80 },
  './src/components/PhaseIndicator.tsx': { branches: 80, functions: 80, lines: 80, statements: 80 },
  './src/components/DiscoveryProgress.tsx': { branches: 80, functions: 80, lines: 80, statements: 80 },
  './src/components/ChatInterface.tsx': { branches: 85, functions: 85, lines: 85, statements: 85 },
  './src/components/ErrorBoundary.tsx': { branches: 85, functions: 85, lines: 85, statements: 85 },
  './src/components/context/ContextItemList.tsx': { branches: 85, functions: 100, lines: 100, statements: 85 },
  './src/components/context/ContextTierChart.tsx': { branches: 85, functions: 100, lines: 100, statements: 85 },
  './src/components/lint/LintResultsTable.tsx': { branches: 100, functions: 100, lines: 100, statements: 100 },
  './src/components/review/ReviewResultsPanel.tsx': { branches: 100, functions: 100, lines: 100, statements: 100 },
  './src/lib/timestampUtils.ts': { branches: 100, functions: 100, lines: 100, statements: 100 },
}
```

### E2E Test Results

TestSprite provides:
1. **Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/1f560e19-85fe-4de1-b584-02d1b836ca81
2. **Local Reports:** `testsprite_tests/testsprite-mcp-test-report.md`
3. **Test Recordings:** Available in TestSprite dashboard

**E2E Test Categories:**
- Project Creation (2 tests)
- Discovery & PRD (2 tests)
- Task Management (1 test)
- Multi-Agent (2 tests)
- Blocker Resolution (2 tests)
- Session Lifecycle (2 tests)
- Quality Gates (3 tests)
- Real-Time Communication (3 tests)
- Context Management (1 test)
- API & Type Safety (2 tests)

---

## 🔄 CI/CD Integration

### Recommended GitHub Actions Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: 'web-ui/package-lock.json'

      - name: Install dependencies
        working-directory: web-ui
        run: npm ci

      - name: Run unit tests with coverage
        working-directory: web-ui
        run: npm run test:coverage

      - name: Check coverage thresholds
        working-directory: web-ui
        run: |
          if [ $(cat coverage/coverage-summary.json | jq '.total.statements.pct') -lt 85 ]; then
            echo "❌ Coverage below 85% threshold"
            exit 1
          fi

      - name: Upload coverage reports
        uses: codecov/codecov-action@v3
        with:
          directory: web-ui/coverage
          flags: frontend

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || github.event_name == 'schedule'
    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'

      - name: Install dependencies
        working-directory: web-ui
        run: npm ci

      - name: Start dev server
        working-directory: web-ui
        run: npm run dev &

      - name: Wait for server
        run: npx wait-on http://localhost:3000 --timeout 60000

      - name: Run TestSprite E2E tests
        run: |
          cd /home/frankbria/projects/codeframe
          node /home/frankbria/.npm/_npx/8ddf6bea01b2519d/node_modules/@testsprite/testsprite-mcp/dist/index.js generateCodeAndExecute

      - name: Upload TestSprite results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: testsprite-results
          path: testsprite_tests/

# Schedule nightly E2E tests
# on:
#   schedule:
#     - cron: '0 2 * * *'  # 2 AM daily
```

### Pre-Commit Hook (Husky)

Install Husky for pre-commit hooks:

```bash
cd web-ui
npm install --save-dev husky
npx husky install
npx husky add .husky/pre-commit "cd web-ui && npm test"
```

---

## 📈 Monitoring & Metrics

### Unit Test Metrics

Track these metrics over time:
- **Coverage Percentage:** Target >85% overall
- **Test Count:** Currently 701 tests
- **Pass Rate:** Target 100%
- **Execution Time:** Currently ~10 seconds
- **Failed Tests:** Target 0

**Quality Ratchet Script:**

```bash
# Check current quality
python scripts/quality-ratchet.py check

# Record baseline
python scripts/quality-ratchet.py record --coverage 81.61 --pass-rate 100.0

# View trends
python scripts/quality-ratchet.py show
```

### E2E Test Metrics

Track these metrics:
- **Pass Rate:** Currently 100% (20/20)
- **Execution Time:** ~15 minutes
- **Test Coverage:** All critical workflows
- **Flakiness:** Target 0% flaky tests

**TestSprite Dashboard:** Monitor at https://www.testsprite.com/dashboard

---

## 🐛 Troubleshooting

### Common Issues

**1. Jest tests failing with "act()" warnings**
```javascript
// Wrap state updates in act()
import { act } from '@testing-library/react';

act(() => {
  // Your state-updating code here
});
```

**2. TestSprite server not reachable**
```bash
# Verify dev server is running
curl http://localhost:3000

# Check firewall settings
sudo ufw status

# Verify port is not in use
lsof -i :3000
```

**3. Coverage threshold failures**
```bash
# Update jest.config.js thresholds if needed
# Or add more tests to reach threshold
npm run test:coverage -- --verbose
```

**4. TestSprite tunnel connection errors**
```bash
# Check internet connectivity
ping tun.testsprite.com

# Verify TestSprite credentials
# Check TestSprite dashboard for account status
```

---

## 🔒 Security Considerations

### Secrets Management

**Never commit:**
- API keys
- Authentication tokens
- TestSprite credentials
- .env files with secrets

**Use environment variables:**
```bash
# .env.local (gitignored)
NEXT_PUBLIC_API_URL=http://localhost:8080
ANTHROPIC_API_KEY=sk-ant-***
TESTSPRITE_API_KEY=***
```

### Test Data

**Unit Tests:**
- Use mocked data (no real API calls)
- No sensitive information in test fixtures
- Mock external services

**E2E Tests:**
- Use test accounts only
- No production data
- Clean up test data after runs

---

## 📚 Additional Resources

### Documentation
- **Jest:** https://jestjs.io/docs/getting-started
- **React Testing Library:** https://testing-library.com/docs/react-testing-library/intro/
- **TestSprite:** https://docs.testsprite.com
- **Playwright:** https://playwright.dev/docs/intro

### Project Documentation
- **PRD:** `/home/frankbria/projects/codeframe/PRD.md`
- **Architecture:** `/home/frankbria/projects/codeframe/CODEFRAME_SPEC.md`
- **Guidelines:** `/home/frankbria/projects/codeframe/CLAUDE.md`
- **E2E Report:** `testsprite_tests/testsprite-mcp-test-report.md`
- **Unit Test Summary:** `testsprite_tests/UNIT_TEST_SUMMARY.md`

### Test Examples
- **Component Test:** `web-ui/__tests__/components/ChatInterface.test.tsx`
- **Utility Test:** `web-ui/__tests__/lib/timestampUtils.test.ts`
- **Integration Test:** `web-ui/__tests__/integration/blocker-websocket.test.ts`

---

## 🎯 Best Practices

### Unit Testing
1. **Test behavior, not implementation** - Focus on what the user sees
2. **Use descriptive test names** - `test_sends_message_on_form_submit`
3. **Follow AAA pattern** - Arrange, Act, Assert
4. **Mock external dependencies** - API calls, WebSocket, date functions
5. **Test edge cases** - Null, undefined, empty strings, large numbers
6. **Test error states** - API failures, network errors, validation failures
7. **Test accessibility** - ARIA labels, keyboard navigation, screen readers
8. **Keep tests fast** - Mock slow operations, avoid timeouts
9. **Avoid test interdependence** - Each test should run independently
10. **Clean up after tests** - Use afterEach/beforeEach for cleanup

### E2E Testing
1. **Test critical user workflows** - Focus on high-value paths
2. **Use realistic data** - Match production scenarios
3. **Handle async operations** - Use proper waits, not arbitrary sleeps
4. **Test error recovery** - Network failures, server errors
5. **Keep tests stable** - Avoid flaky tests with proper waiting
6. **Run E2E tests less frequently** - Nightly or pre-release (not every commit)
7. **Monitor test duration** - Keep E2E suite under 30 minutes
8. **Use page objects** - Encapsulate page interactions
9. **Take screenshots on failure** - Aid debugging
10. **Test on multiple browsers** - Chrome, Firefox, Safari

---

## 📞 Support

### Getting Help
- **TestSprite Support:** support@testsprite.com
- **Project Issues:** https://github.com/frankbria/codeframe/issues
- **Slack Channel:** #codeframe-testing (if applicable)

### Useful Commands
```bash
# View test file tree
tree web-ui/__tests__

# Count total tests
grep -r "it('test_" web-ui/__tests__ | wc -l

# Find flaky tests
grep -r "test.skip\|it.skip" web-ui/__tests__

# Generate coverage badge
npm run test:coverage && npx coverage-badge-creator
```

---

**Integration Guide Version:** 1.0
**Last Updated:** 2025-11-21
**Status:** ✅ Complete - Both unit and E2E testing integrated
**Next Review:** When adding major new features or significant codebase changes
