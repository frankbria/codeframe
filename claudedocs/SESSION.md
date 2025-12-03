# Session: Fix E2E Playwright Tests in CI

**Date**: 2025-12-03
**Branch**: `fix/playwright-e2e-tests-ci`
**Base Commit**: `7f7e895` (main merged into branch)
**Status**: 🚧 **IN PROGRESS**

## Problem Statement

E2E Playwright tests are failing in GitHub Actions CI with only 18% pass rate (2/11 tests passing).

**Root Cause**: Tests are failing because the test project created in `global-setup.ts` has no data:
- No agents (empty agent list)
- No tasks (no task statistics)
- No metrics (no token usage or cost data)
- No checkpoints (no checkpoint history)
- No reviews (no review findings)
- No quality gates (no gate results)
- No activity feed (no events)

**Current Status**:
- ✅ Test project creation working correctly
- ✅ Frontend navigation working (2 tests passing)
- ❌ All feature tests failing due to empty data (9 tests failing)

## Execution Plan (5 Phases)

### Phase 1: Investigation & API Verification ✅
**Goal**: Validate current test infrastructure and confirm all required API endpoints exist
**Estimated Time**: 30-45 minutes
**Status**: Complete

**Resources**:
- Agent: `playwright-expert` - Review test failures, analyze Playwright configuration
- Agent: `fastapi-expert` - Verify all required API endpoints exist

**Tasks**:
1. Review recent GitHub Actions failure logs (last 5 runs)
2. Confirm `global-setup.ts` creates test project successfully (already verified ✅)
3. Verify API endpoints exist for seeding:
   - `POST /api/agents` (create agents)
   - `POST /api/tasks` (create tasks)
   - `POST /api/token-usage` (record token usage)
   - `POST /api/projects/{id}/checkpoints` (create checkpoints)
   - `POST /api/reviews` (save review reports)
   - `POST /api/quality-gates` (save quality gate results)
   - `POST /api/activity` (add activity events)
4. Document any missing endpoints

**Expected Outcome**:
- List of existing vs. missing API endpoints
- Clear path forward for Phase 2

---

### Phase 2: Quick Win Data Seeding (Agents & Tasks) ✅
**Goal**: Extend `global-setup.ts` to seed agents, tasks, and project progress
**Estimated Time**: 2-3 hours
**Target Pass Rate**: 40-50% (4-5 tests passing)
**Status**: Complete
**Actual Pass Rate**: 32% (12/37 tests passing)

**Resources**:
- Agent: `typescript-expert` - Implement TypeScript seeding logic
- Agent: `playwright-expert` - Validate test improvements

**Tasks**:
1. Create Python seeding script (`tests/e2e/seed-test-data.py`):
   - Seed 5 agents (lead, backend, frontend, test, review) with mixed statuses
   - Seed 10 tasks (3 completed, 2 in-progress, 2 blocked, 3 pending)
   - Update project progress statistics
2. Modify `global-setup.ts` to call Python seeding script after project creation
3. Run tests locally (Chromium only) to validate improvements
4. Commit changes and push to trigger GitHub Actions run

**Expected Tests Passing**:
- ✅ Dashboard sections test (already passing)
- ✅ Navigation test (already passing)
- ✅ Task statistics test (NEW)
- ✅ Agent status test (NEW)
- ✅ Possibly responsive mobile test

**Files Modified**:
```
tests/e2e/
├── global-setup.ts        (MODIFIED) - Add seeding orchestration
└── seed-test-data.py      (NEW) - Python seeding script
```

---

### Phase 3: Metrics & Cost Data Seeding
**Goal**: Seed token usage and cost data to pass metrics-related tests
**Estimated Time**: 2-3 hours
**Target Pass Rate**: 65-75% (7-8 tests passing)
**Status**: Pending

**Resources**:
- Agent: `python-expert` - Extend seeding script with token usage records
- Agent: `playwright-expert` - Validate metrics tests

**Tasks**:
1. Extend `seed-test-data.py` to seed:
   - 15 token usage records across 3 models (Sonnet, Opus, Haiku)
   - Records distributed across 3 days for time-series data
   - Total cost ~$4.46 USD (realistic for charts)
2. Run tests locally to validate metrics panel tests pass
3. Commit and push to GitHub Actions

**Expected Tests Passing**:
- ✅ Metrics panel test (NEW)
- ✅ Cost display test (NEW)
- ✅ Token stats test (NEW)

---

### Phase 4: Advanced Feature Data Seeding
**Goal**: Seed checkpoints, reviews, quality gates, and activity feed
**Estimated Time**: 2-3 hours
**Target Pass Rate**: 90-100% (9-11 tests passing)
**Status**: Pending

**Resources**:
- Agent: `python-expert` - Complete full data seeding
- Agent: `quality-engineer` - Validate all tests pass and fix weak assertions

**Tasks**:
1. Extend `seed-test-data.py` to seed:
   - 3 checkpoints with Git commit SHAs and metadata
   - 2 review reports (1 approved, 1 changes_requested) with findings
   - 2 quality gate results (1 passed, 1 failed)
   - 10 activity feed events
2. Fix weak test assertions:
   - Change `count() >= 0` to `count() > 0` where data should exist
   - Remove unnecessary conditionals in tests
   - Assert specific WebSocket message types
3. Run full test suite locally (all browsers: Chromium, Firefox, WebKit)
4. Commit and push to GitHub Actions

**Expected Tests Passing**:
- ✅ Review findings panel test (NEW)
- ✅ Quality gates panel test (NEW)
- ✅ Checkpoint panel test (NEW)
- ✅ WebSocket real-time updates test (improved)

**Files Modified**:
```
tests/e2e/
├── seed-test-data.py           (MODIFIED) - Complete seeding
├── test_dashboard.spec.ts      (MODIFIED) - Fix weak assertions
├── test_checkpoint_ui.spec.ts  (MODIFIED) - Fix weak assertions
├── test_metrics_ui.spec.ts     (MODIFIED) - Fix weak assertions
└── test_review_ui.spec.ts      (MODIFIED) - Fix weak assertions
```

---

### Phase 5: CI/CD Validation & Documentation
**Goal**: Ensure tests pass consistently in GitHub Actions and document solution
**Estimated Time**: 1-2 hours
**Status**: Pending

**Resources**:
- Skill: `managing-gitops-ci` - Validate GitHub Actions workflow
- Agent: `technical-writer` - Document seeding approach

**Tasks**:
1. Monitor GitHub Actions E2E test runs (3 consecutive passing runs required)
2. Review Playwright HTML reports uploaded as artifacts
3. Troubleshoot any CI-specific failures (timing issues, WebSocket problems)
4. Update project documentation:
   - Add section to `CLAUDE.md` on E2E test data requirements
   - Document seeding script usage in `tests/e2e/README.md`
   - Update `E2E_PLAYWRIGHT_FIX_SUMMARY.md` with final results
5. Create summary report

**Expected Outcome**:
- 90-100% test pass rate in GitHub Actions (3+ consecutive runs)
- Comprehensive documentation of test data seeding

**Files Modified**:
```
CLAUDE.md                        (MODIFIED) - Add E2E testing guidance
E2E_PLAYWRIGHT_FIX_SUMMARY.md    (MODIFIED) - Update with final results
tests/e2e/README.md              (NEW) - Document seeding approach
```

---

## Estimated Resources

- **Total Time**: 8-13 hours
- **Token Usage**: ~58k tokens
- **Risk Level**: Medium (potential missing API endpoints)

## Success Criteria

- ✅ **Primary Goal**: 90-100% E2E test pass rate in GitHub Actions (currently 18%)
- ✅ **Secondary Goal**: Tests validate all Sprint 10 features
- ✅ **Tertiary Goal**: Seeding approach documented and maintainable

## Key Technical Decisions

1. **Seeding Strategy**: Python script called from TypeScript `global-setup.ts`
   - Rationale: Python has better FastAPI/SQLite integration
   - Alternative: TypeScript seeding (more complex, no benefits)

2. **Seeding Scope**: Comprehensive data across all features
   - Phase 2: Agents & tasks (quick win)
   - Phase 3: Metrics & costs (medium complexity)
   - Phase 4: Advanced features (full coverage)

3. **Assertion Improvements**: Strengthen weak assertions
   - Change `count() >= 0` to `count() > 0` (expect data to exist)
   - Remove unnecessary conditionals (data should always exist)

## Next Steps

Starting with Phase 1: Investigation & API Verification

---

## Phase 2 Results & Analysis

### ✅ Achievements

1. **Test Pass Rate Improvement**: 77% increase
   - Before: 2/11 (18%)
   - After: 12/37 (32%)
   - +10 tests now passing

2. **Infrastructure Complete**
   - `seed-test-data.py` - Comprehensive seeding script
   - `PHASE1_API_ENDPOINT_ANALYSIS.md` - API documentation
   - `PHASE2_TEST_ANALYSIS.md` - Failure pattern analysis

3. **Data Seeding Working**
   - ✅ 5 agents (lead, backend, frontend, test, review)
   - ✅ 10 tasks (3 completed, 2 in-progress, 2 blocked, 3 pending)
   - ✅ 15 token usage records (Sonnet, Opus, Haiku)
   - ✅ 7 code review findings
   - ✅ 3 checkpoints (via API)

4. **New Passing Tests**
   - ✅ Agent status information
   - ✅ Review findings (expand/collapse, filter, recommendations)
   - ✅ Metrics (cost charts, pricing, export, filters)

### ⚠️ Remaining Issues

**Critical Gap**: Project-agent assignments missing
- Agents seeded in `agents` table
- But not assigned to project in `project_agents` table
- Frontend filters agents without project assignment
- **Impact**: May prevent 10-15 tests from passing

**Component Rendering**: Some panels not displaying
- Checkpoint panel (8 tests failing)
- Quality gates panel (expected - no data)
- Some dashboard sections (6 tests failing)

**Test Regressions**: 2 previously passing tests now fail
- "should display all main dashboard sections"
- "should navigate between dashboard sections"

### 🎯 Strategic Recommendations

**Quick Win Path** (1 hour, 50-60% target):
1. Add project-agent assignments (30 min)
2. Run tests, measure improvement
3. Debug 2-3 components if needed (30 min)

**Full Fix Path** (4-6 hours, 90-100% target):
1. Add project-agent assignments
2. Debug all component issues
3. Add quality gate seeding
4. Fix weak assertions
5. Run full test suite (all browsers)

---

**Session Start**: 2025-12-03
**Current Phase**: Phase 2 Complete - Review & Analysis ✅
**Next Session**: Quick win or full fix (user choice)
