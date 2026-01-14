# E2E Test Failures Report - 2026-01-13

## Summary

| Category | Count |
|----------|-------|
| Failed | 39 |
| Flaky | 13 |
| Skipped | 25 |
| Did not run | 19 |
| Passed | 559 |
| **Total** | **655** |
| **Duration** | 46.6m |

---

## Critical Issues (Grouped by Root Cause)

### Issue #1: Mobile Viewport Detection Bug

**Severity:** High
**Affected Browsers:** Mobile Chrome, Mobile Safari
**Affected Tests:** 3

The test incorrectly detects mobile browsers as desktop, then asserts desktop viewport width >800 when the actual mobile width is ~390px.

**Failing Tests:**
- `[Mobile Chrome] › test_mobile_smoke.spec.ts:50:7 › should have correct mobile viewport @smoke`
- `[Mobile Safari] › test_mobile_smoke.spec.ts:50:7 › should have correct mobile viewport @smoke`

**Error:**
```
Error: expect(received).toBeGreaterThan(expected)
Expected: > 800
Received:   393  (or 390 for Safari)
```

**Root Cause Analysis:**
The test runs `mobile: false` detection when it should detect `mobile: true` for Mobile Chrome/Safari projects:
```
Running mobile test on: chromium (mobile: false)
ℹ️ Desktop viewport: 1280x720 (not a mobile test)
```

**Location:** `tests/e2e/test_mobile_smoke.spec.ts:50-64`

**Fix:** Update mobile detection logic in playwright config or test setup to correctly identify Mobile Chrome/Safari projects.

---

### Issue #2: Project Phase State Mismatch (Seed Data)

**Severity:** High
**Affected Browsers:** Firefox, WebKit, Mobile Chrome, Mobile Safari
**Affected Tests:** 10+

Tests expect project to be in `planning` phase but receive `active` phase instead.

**Failing Tests:**
- `test_late_joining_user.spec.ts:129` - should show "Tasks Ready" section @smoke
- `test_state_reconciliation.spec.ts:132` - should show "Review Tasks" @smoke
- `test_state_reconciliation.spec.ts:657` - should maintain correct state after page refresh @smoke

**Error:**
```
Error: expect(received).toBe(expected) // Object.is equality
Expected: "planning"
Received: "active"
```

**Root Cause:** Test seed data creates projects in `active` phase instead of `planning` phase.

**Location:**
- `tests/e2e/test_late_joining_user.spec.ts:168`
- `tests/e2e/test_state_reconciliation.spec.ts:138`
- Seed script: `scripts/seed-test-data.py`

**Fix:** Update seed data script to ensure `TEST_PROJECT_IDS.PLANNING` projects remain in `planning` phase with tasks ready for review.

---

### Issue #3: Missing `tasks-ready-section` UI Element

**Severity:** High
**Affected Browsers:** Firefox, WebKit, Mobile Chrome, Mobile Safari
**Affected Tests:** 8+

The `[data-testid="tasks-ready-section"]` element is not visible when tests expect it.

**Failing Tests:**
- `test_late_joining_user.spec.ts:201` - should not show "Generate Tasks" button
- `test_state_reconciliation.spec.ts:657` - should maintain correct state after page refresh

**Error:**
```
Error: expect(locator).toBeVisible() failed
Locator: locator('[data-testid="tasks-ready-section"]')
Expected: visible
Timeout: 5000ms
Error: element(s) not found
```

**Root Cause:** Either:
1. Component not rendered due to phase state (see Issue #2)
2. Missing `data-testid` attribute on the component
3. Conditional rendering logic not showing the section

**Location:** Component needs investigation in `web-ui/src/components/`

**Fix:** Ensure `tasks-ready-section` component renders when project has tasks in planning phase.

---

### Issue #4: Mobile Click Interception Bug

**Severity:** High
**Affected Browsers:** Mobile Chrome
**Affected Tests:** 15+ (all metrics tests on Mobile Chrome)

On mobile viewport, clicks on dashboard tabs are intercepted by overlapping elements.

**Failing Tests:**
- All `test_metrics_ui.spec.ts` tests on Mobile Chrome
- `test_dashboard.spec.ts:157` - should display all main dashboard sections
- `test_dashboard.spec.ts:273` - should display metrics and cost tracking panel
- `test_dashboard.spec.ts:496` - should navigate between dashboard sections
- `test_task_execution_flow.spec.ts:143` - should navigate between dashboard tabs

**Error:**
```
TimeoutError: locator.click: Timeout 15000ms exceeded.
Call log:
  - <nav role="tablist" data-testid="nav-menu"> intercepts pointer events
  - <div data-testid="phase-progress"> intercepts pointer events
  - <button>Chat with Lead</button> intercepts pointer events
```

**Root Cause:** On mobile viewport:
1. Sticky header elements overlap clickable tabs
2. Z-index/stacking context issues
3. Elements not scrolled into view properly before click

**Location:**
- `web-ui/src/components/Dashboard.tsx` (header layout)
- `tests/e2e/test_metrics_ui.spec.ts:48`

**Fix:**
1. Review mobile CSS for z-index stacking
2. Add `{ force: true }` or scroll before click in tests as workaround
3. Fix header/nav positioning on mobile to avoid overlap

---

### Issue #5: Task Approval Button Not Visible

**Severity:** Medium
**Affected Browsers:** Chromium
**Affected Tests:** 1

**Failing Test:**
- `[chromium] › test_task_approval.spec.ts:149:7 › should handle 422 validation error gracefully`

**Error:**
```
Error: expect(locator).toBeVisible() failed
Locator: getByRole('button', { name: /approve/i })
Expected: visible
Timeout: 5000ms
```

**Location:** `tests/e2e/test_task_approval.spec.ts:178`

**Fix:** Investigate why approve button doesn't render in this specific test scenario.

---

### Issue #6: Task Approval API Contract Failures

**Severity:** Medium
**Affected Browsers:** Firefox, WebKit, Mobile Chrome, Mobile Safari
**Affected Tests:** 5

**Failing Test:**
- `test_task_approval.spec.ts:70` - should send correct request body format @smoke

**Location:** `tests/e2e/test_task_approval.spec.ts:70`

**Note:** Related to Issue #5 - approve button visibility affects API tests.

---

## Backend Errors (Found in Server Logs)

### Backend Issue #1: Task Object Type Mismatch

**Error:**
```python
AttributeError: 'dict' object has no attribute 'id'
# at: logger.info(f"Frontend agent {self.agent_id} executing task {task.id}: {task.title}")
```

**Location:** Frontend agent task execution code

**Fix:** Ensure task objects are properly deserialized from dict to Task model.

---

### Backend Issue #2: NoneType Search Pattern

**Error:**
```python
AttributeError: 'NoneType' object has no attribute 'search_pattern'
# Tasks 868, 869, 871 failed with this error
```

**Fix:** Add null checks before accessing `search_pattern` attribute.

---

### Backend Issue #3: Missing Issues in Database

**Error:**
```python
ValueError: No issues found in database. Generate issues first using generate_issues(sprint_number)
```

**Root Cause:** Task generation attempted without prerequisite issues in database.

**Fix:** Ensure seed data includes issues or improve error handling with graceful degradation.

---

## Flaky Tests (13 Total)

All flaky tests eventually passed on retry. Consider increasing timeouts or adding more robust waits.

| Browser | Test File | Test Name |
|---------|-----------|-----------|
| webkit | test_metrics_ui.spec.ts:62 | should display metrics panel |
| webkit | test_metrics_ui.spec.ts:82 | should display total cost |
| webkit | test_metrics_ui.spec.ts:165 | should display cost breakdown by model |
| webkit | test_metrics_ui.spec.ts:340 | should refresh metrics in real-time |
| webkit | test_metrics_ui.spec.ts:381 | should display cost trend chart |
| webkit | test_project_creation.spec.ts:275 | should show empty state when no projects exist |
| webkit | test_returning_user.spec.ts:412 | should show quality gate failures @returning-user |
| webkit | test_review_ui.spec.ts:118 | should expand/collapse review finding details |
| webkit | test_review_ui.spec.ts:149 | should filter findings by severity |
| webkit | test_start_agent_flow.spec.ts:113 | should show agent status panel after project creation |
| webkit | test_state_reconciliation.spec.ts:279 | should show "Discovery Complete" |
| Mobile Safari | test_mobile_smoke.spec.ts:141 | should handle responsive navigation @smoke |
| Mobile Safari | test_returning_user.spec.ts:492 | should load complete state from API @returning-user |

**Common Pattern:** WebKit/Safari timing issues with API responses and UI updates.

**Recommended Fix:** Increase timeouts for webkit or add explicit waitFor conditions.

---

## Warnings (Non-Critical)

### Warning #1: GitWorkflowManager Initialization

```
Could not initialize GitWorkflowManager: /home/frankbria/projects/codeframe/tests/e2e/.codeframe/workspaces/X. Git features will be disabled.
```

**Impact:** Low - Git features not used in E2E tests

### Warning #2: Incomplete API Data

```
⚠️ Project API returned incomplete data: {"blockers":[],"total":0,...}
```

**Impact:** Medium - May indicate seed data issues

### Warning #3: Default AUTH_SECRET

```
⚠️ AUTH_SECRET not set - using default value. DO NOT USE IN PRODUCTION!
```

**Impact:** None for tests - expected in test environment

### Warning #4: Font Override

```
⨯ Failed to find font override values for font `Nunito Sans`
```

**Impact:** Low - Cosmetic, does not affect functionality

---

## Recommended Priority Order

1. **Issue #2** - Fix seed data (blocks 10+ tests across browsers)
2. **Issue #4** - Fix mobile click interception (blocks 15+ tests)
3. **Issue #1** - Fix mobile viewport detection (affects 2 critical smoke tests)
4. **Issue #3** - Fix tasks-ready-section visibility (depends on #2)
5. **Issue #5/#6** - Fix task approval button visibility
6. **Flaky Tests** - Increase webkit timeouts

---

## GitHub Issue Template

### For each issue, create:

```markdown
## Description
[Brief description of the failure]

## Test(s) Affected
- [ ] `[browser] › file.spec.ts:line › test name`

## Error Message
```
[Error output]
```

## Root Cause
[Analysis]

## Proposed Fix
[Solution]

## Files to Modify
- [ ] `path/to/file.ts`
```

---

## Quick Reference: All Failed Tests

### Chromium (1)
- `test_task_approval.spec.ts:149` - should handle 422 validation error gracefully

### Firefox (5)
- `test_late_joining_user.spec.ts:129` - should show "Tasks Ready" section @smoke
- `test_late_joining_user.spec.ts:201` - should not show "Generate Tasks" button
- `test_state_reconciliation.spec.ts:132` - should show "Review Tasks" @smoke
- `test_state_reconciliation.spec.ts:657` - should maintain correct state @smoke
- `test_task_approval.spec.ts:70` - should send correct request body @smoke

### WebKit (5)
- `test_late_joining_user.spec.ts:129` - should show "Tasks Ready" section @smoke
- `test_late_joining_user.spec.ts:201` - should not show "Generate Tasks" button
- `test_state_reconciliation.spec.ts:132` - should show "Review Tasks" @smoke
- `test_state_reconciliation.spec.ts:657` - should maintain correct state @smoke
- `test_task_approval.spec.ts:70` - should send correct request body @smoke

### Mobile Chrome (17)
- `test_dashboard.spec.ts:157, 273, 496` - dashboard sections/metrics/navigation
- `test_late_joining_user.spec.ts:129, 201` - tasks ready section
- `test_metrics_ui.spec.ts:62, 82, 98, 117, 133, 165, 202, 247, 270, 313, 340, 381` - all metrics tests
- `test_mobile_smoke.spec.ts:50` - viewport detection
- `test_state_reconciliation.spec.ts:132, 657` - state reconciliation
- `test_task_approval.spec.ts:70` - task approval
- `test_task_execution_flow.spec.ts:143` - tab navigation

### Mobile Safari (6)
- `test_late_joining_user.spec.ts:129, 201` - tasks ready section
- `test_mobile_smoke.spec.ts:50` - viewport detection
- `test_state_reconciliation.spec.ts:132, 657` - state reconciliation
- `test_task_approval.spec.ts:70` - task approval
