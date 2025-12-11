# Active Session: Fix E2E Frontend Test Failures

**Started**: 2025-12-10
**Branch**: `e2e-frontend-tests`
**Status**: Phase 1 - In Progress

---

## Objective
Diagnose and fix E2E Playwright test failures by resolving backend connectivity issues, validating test data seeding, and ensuring all frontend components render correctly.

---

## Execution Plan

### Phase 1: Investigation & Diagnosis (Sequential) ⏳ IN PROGRESS
**Goal**: Identify root cause of E2E test failures

**Resources**:
- Agent: `playwright-expert` - Analyze Playwright test configuration and connection failures
- Agent: `root-cause-analyst` - Systematic investigation of ECONNREFUSED error

**Expected Outcome**: Clear understanding of:
- Why backend connection fails (port 8080 not running)
- Whether tests require running backend or should use mocks
- Database seeding issues (global-setup.ts dependencies)

**Estimated Duration**: 10-15 minutes | **Tokens**: ~5k

---

### Phase 2: Backend Environment Setup (Sequential)
**Goal**: Ensure backend services are running for E2E tests

**Resources**:
- Agent: `fastapi-expert` - Start FastAPI backend on port 8080
- Agent: `mongodb-expert` - Verify MongoDB connection and database state

**Expected Outcome**:
- Backend running on http://localhost:8080
- Database accessible at correct path
- Health check endpoint responding

**Estimated Duration**: 5-10 minutes | **Tokens**: ~3k

---

### Phase 3: Test Infrastructure Fixes (Parallel)
**Goal**: Fix test setup and data seeding issues

**Resources** (run in parallel):
- Agent: `python-expert` - Fix seed-test-data.py script database path resolution
- Agent: `typescript-expert` - Update global-setup.ts with proper error handling and retries
- Agent: `playwright-expert` - Validate playwright.config.ts webServer configuration

**Expected Outcome**:
- Global setup successfully creates test project
- Database seeding completes without errors
- WebServer starts before tests run

**Estimated Duration**: 15-20 minutes | **Tokens**: ~18k

---

### Phase 4: Frontend Test Validation (Sequential)
**Goal**: Run and fix individual test suites

**Resources**:
- Command: `/fhb:implement` - Fix failing test assertions in test files
  - test_dashboard.spec.ts
  - test_checkpoint_ui.spec.ts
  - test_metrics_ui.spec.ts
  - test_review_ui.spec.ts

**Expected Outcome**:
- All 4 test suites pass
- No flaky tests (consistent pass rate)
- Screenshots/traces available for debugging

**Estimated Duration**: 20-30 minutes | **Tokens**: ~25k

---

### Phase 5: Integration Testing (Sequential)
**Goal**: Verify full E2E workflow end-to-end

**Resources**:
- Agent: `quality-engineer` - Run complete test suite with all browsers
- Skill: `playwright-skill` - Execute cross-browser validation (Chromium, Firefox, WebKit)

**Expected Outcome**:
- All tests pass on all browsers
- No console errors or warnings
- Performance metrics acceptable (<5s per test)

**Estimated Duration**: 10-15 minutes | **Tokens**: ~8k

---

### Phase 6: Documentation & Cleanup (Sequential)
**Goal**: Update documentation and ensure reproducibility

**Resources**:
- Agent: `technical-writer` - Update E2E testing documentation in CLAUDE.md
- Command: `/fhb:docs` - Update relevant documentation files

**Expected Outcome**:
- README updated with E2E test running instructions
- CLAUDE.md includes E2E troubleshooting guide
- CI/CD integration notes (if applicable)

**Estimated Duration**: 10 minutes | **Tokens**: ~4k

---

## Total Estimates
- **Time**: 70-100 minutes (~1.5 hours)
- **Tokens**: ~63k tokens
- **Complexity**: Medium

---

## Success Criteria
- ✅ All 4 test suites pass (test_dashboard, test_checkpoint_ui, test_metrics_ui, test_review_ui)
- ✅ 100% pass rate across Chromium, Firefox, WebKit
- ✅ No console errors in test output
- ✅ Global setup completes in <10 seconds
- ✅ Individual tests complete in <5 seconds each
- ✅ Documentation updated with troubleshooting guide

---

## Risk Mitigation

### High Risk
- **Backend dependency**: E2E tests require running backend (not mocked)
  - **Mitigation**: Ensure FastAPI backend starts in Phase 2; add health check retries
- **Database state**: Tests may pollute shared database
  - **Mitigation**: Use test-specific database or cleanup after tests

### Medium Risk
- **Flaky tests**: Timing issues with WebSocket connections or async state updates
  - **Mitigation**: Add explicit waits in Playwright tests; increase timeout in playwright.config.ts
- **Browser binary missing**: Playwright browsers may not be installed
  - **Mitigation**: Run `npm run install:browsers` in Phase 2

### Low Risk
- **Port conflicts**: Port 8080 may already be in use
  - **Mitigation**: Check with `lsof -i :8080` before starting backend

---

## Progress Log

### Phase 1: Investigation & Diagnosis ⏳ IN PROGRESS
- [ ] Started
- [ ] playwright-expert analysis complete
- [ ] root-cause-analyst investigation complete
- [ ] Phase complete

### Phase 2: Backend Environment Setup
- [ ] Started
- [ ] Backend running on port 8080
- [ ] MongoDB connection verified
- [ ] Phase complete

### Phase 3: Test Infrastructure Fixes
- [ ] Started
- [ ] seed-test-data.py fixed (python-expert)
- [ ] global-setup.ts fixed (typescript-expert)
- [ ] playwright.config.ts validated (playwright-expert)
- [ ] Phase complete

### Phase 4: Frontend Test Validation
- [ ] Started
- [ ] test_dashboard.spec.ts passing
- [ ] test_checkpoint_ui.spec.ts passing
- [ ] test_metrics_ui.spec.ts passing
- [ ] test_review_ui.spec.ts passing
- [ ] Phase complete

### Phase 5: Integration Testing
- [ ] Started
- [ ] Cross-browser validation complete
- [ ] Phase complete

### Phase 6: Documentation & Cleanup
- [ ] Started
- [ ] Documentation updated
- [ ] Phase complete

---

## Notes
- Execution started: 2025-12-10
- Feature branch: `e2e-frontend-tests`
- Base branch: `main`
