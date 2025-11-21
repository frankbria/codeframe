# TestSprite Unified Test Suite - Quick Reference

**Last Updated:** 2025-11-21

---

## 🚀 Run Tests

```bash
# Start frontend (required)
cd web-ui && npm run dev

# Run all TestSprite tests (in project root)
cd /home/frankbria/projects/codeframe
node /home/frankbria/.npm/_npx/8ddf6bea01b2519d/node_modules/@testsprite/testsprite-mcp/dist/index.js generateCodeAndExecute
```

---

## 📊 Current Status

- **Total Tests:** 22 (TC001-TC022)
- **Pass Rate:** 95.45% (21/22)
- **Frontend-Only:** 100% (21/21)
- **Failed Test:** TC001 (requires backend API on port 8080)
- **Dashboard:** https://www.testsprite.com/dashboard/mcp/tests/1b6320e2-5e9b-44f0-bc19-6041d5808960

---

## 📋 Test Categories

### E2E Workflows (TC001-TC013)
- ⚠️ TC001: Project Creation (requires backend)
- ✅ TC002-TC013: All frontend workflows (21 tests passing)

### Component Tests (TC014-TC022)
Converted from Jest unit tests to E2E browser tests:
- ✅ TC014: ChatInterface
- ✅ TC015: ErrorBoundary
- ✅ TC016: ContextItemList
- ✅ TC017: ContextTierChart
- ✅ TC018: LintResultsTable
- ✅ TC019: ReviewResultsPanel
- ✅ TC020: ReviewScoreChart
- ✅ TC021: ReviewFindingsList
- ✅ TC022: Timestamp Utilities

---

## 📁 Key Files

- **Test Plan:** `testsprite_frontend_test_plan.json` (single source of truth)
- **Summary:** `UNIFIED_TEST_SUITE_SUMMARY.md` (complete overview)
- **Test Report:** `testsprite-mcp-test-report.md` (latest results)
- **README:** `README.md` (documentation index)

---

## ⚠️ Important Notes

### TC001 Requirement
TC001 requires the backend API server running on port 8080:
```bash
# If backend is available
cd /home/frankbria/projects/codeframe
uv run uvicorn codeframe.main:app --port 8080
```

### Frontend-Only Testing
For frontend-only testing (without backend), **all 21 tests pass** (TC002-TC022).

---

## 📖 Full Documentation

See `UNIFIED_TEST_SUITE_SUMMARY.md` for:
- Detailed test breakdown
- Before/after comparison
- CI/CD integration guide
- Troubleshooting tips
- Success criteria
