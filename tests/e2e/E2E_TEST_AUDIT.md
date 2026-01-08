# E2E Test Audit Report

**Date**: 2026-01-07
**Auditor**: Claude Code
**Status**: CRITICAL ISSUES FOUND AND FIXED

## Fixes Applied in This PR

### Commit 1: Initial fixes
1. **WebSocket test now REQUIRES messages** - `test_dashboard.spec.ts:444-456`
2. **Error filters tightened** - All test files now only filter `net::ERR_ABORTED`
3. **API response validation added** - `test_project_creation.spec.ts`, `test_task_breakdown.spec.ts`

### Commit 2: Comprehensive pattern replacement
4. **Replaced `.catch(() => false)` patterns** across all test files:
   - `test_task_breakdown.spec.ts`: All 6 conditional skips now verify alternate state before skipping
   - `test_metrics_ui.spec.ts`: API responses now validated, no silent failures
   - `test_start_agent_flow.spec.ts`: Replaced 3 instances with `.count()` + `.isVisible()` pattern
   - `test_complete_user_journey.spec.ts`: Replaced 5 instances with proper assertions
5. **Replaced `.catch(() => {})` patterns** - Metrics tests now fail on API errors
6. **Added state verification before skips** - Tests now assert they're in a known alternate state

## Remaining Work (Future PRs)

- Add API response validation to more user actions (lower priority)
- Consider test data fixtures for consistent project states

## Executive Summary

The E2E test suite has **critical design flaws** that allow tests to pass even when functionality is broken. The tests are designed to avoid failures rather than catch them.

## Critical Issues

### 1. Error Filtering Masks Real Failures (CRITICAL)

**Location**: Every test file's `afterEach` block

**Pattern**:
```typescript
checkTestErrors(page, 'Test name', [
  'WebSocket', 'ws://', 'wss://',  // ALL WebSocket errors ignored
  'net::ERR_FAILED',               // Network failures ignored
  'net::ERR_ABORTED',              // Cancelled requests ignored
  'discovery',                      // Discovery API errors ignored
  'Failed to fetch',                // Fetch errors ignored
]);
```

**Impact**: If WebSocket server is down, APIs are returning 500s, or network is broken - tests still pass.

**Files Affected**:
- `test_task_execution_flow.spec.ts:43-50`
- `test_project_creation.spec.ts:39-46, 181-188`
- `test_auth_flow.spec.ts:51-59`
- `test_start_agent_flow.spec.ts:49-56`
- `test_complete_user_journey.spec.ts:47-55`
- `test_task_breakdown.spec.ts:46-51`
- `test_dashboard.spec.ts:143-148`

### 2. Conditional Skip Pattern (CRITICAL)

**Pattern**:
```typescript
const isVisible = await element.isVisible().catch(() => false);
if (!isVisible) {
  test.skip(true, 'Element not visible - skipping');
  return;
}
```

**Impact**: If a feature is completely broken, tests skip instead of fail. This gives false confidence that "all tests pass."

**Files Affected**:
- `test_task_breakdown.spec.ts`: 6 instances (lines 93, 114, 206, 226, 290, 316)
- `test_metrics_ui.spec.ts`: 1 instance (line 201)
- `test_start_agent_flow.spec.ts`: 3 instances (lines 83, 135, 190)
- `test_complete_user_journey.spec.ts`: 1 instance (line 107)

### 3. WebSocket Test Accepts 0 Messages (CRITICAL)

**Location**: `test_dashboard.spec.ts:444-452`

**Code**:
```typescript
if (wsMonitor.messages.length === 0) {
  console.log('ℹ️ No WebSocket messages received (backend is passive)');
  // Accept 0 messages as long as connection succeeded
}
```

**Impact**: WebSocket test passes even if NO messages are received. This completely defeats the purpose of testing real-time updates.

### 4. `.catch(() => false)` Swallows Errors (HIGH)

**Pattern**:
```typescript
const hasError = await errorSection.isVisible().catch(() => false);
```

**Impact**: If checking visibility throws an error (e.g., element detached, timeout), it's silently treated as "not visible" instead of failing.

**Occurrences**: 40+ instances across all test files

### 5. `toBeAttached()` Instead of `toBeVisible()` (MEDIUM)

**Pattern**:
```typescript
await expect(element).toBeAttached();  // Only checks DOM presence
// Should be:
await expect(element).toBeVisible();   // Checks actually rendered
```

**Impact**: Elements can exist in DOM but be invisible (display:none, visibility:hidden). Tests pass but user can't see the element.

**Files with excessive `toBeAttached()` usage**:
- `test_task_execution_flow.spec.ts`: 10 instances
- `test_complete_user_journey.spec.ts`: 4 instances
- `test_dashboard.spec.ts`: 9 instances

### 6. Console.log Instead of Assertions (LOW)

**Pattern**:
```typescript
console.log('✅ Feature works');
// No actual assertion!
```

**Impact**: Logs success without verifying condition is actually true.

### 7. No API Response Validation (HIGH)

**Pattern**:
```typescript
await button.click();
// No verification that API call succeeded!
```

**Impact**: Tests verify UI changes but not that the backend actually processed the request.

**Exception**: Only `test_task_breakdown.spec.ts` now validates API response (after recent fix).

## Recommended Fixes

### Fix 1: Remove Overly Broad Error Filters

Replace:
```typescript
checkTestErrors(page, 'Test', ['WebSocket', 'ws://', ...]);
```

With:
```typescript
checkTestErrors(page, 'Test', [
  'net::ERR_ABORTED'  // Only filter navigation cancellations
]);
```

### Fix 2: Replace Conditional Skips with Proper Setup

Replace:
```typescript
if (!isVisible) {
  test.skip(true, 'Not in correct state');
}
```

With:
```typescript
// Set up test data to ensure correct state
await setupProjectInPlanningPhase(page, projectId);
await expect(element).toBeVisible();
```

### Fix 3: Assert on API Responses

Add:
```typescript
const responsePromise = page.waitForResponse(
  response => response.url().includes('/api/endpoint')
);
await button.click();
const response = await responsePromise;
expect(response.status()).toBeLessThan(400);
```

### Fix 4: Replace `.catch(() => false)` with Proper Assertions

Replace:
```typescript
const isVisible = await element.isVisible().catch(() => false);
if (isVisible) { /* do something */ }
```

With:
```typescript
await expect(element).toBeVisible({ timeout: 5000 });
```

### Fix 5: WebSocket Test Must Receive Messages

Replace:
```typescript
if (wsMonitor.messages.length === 0) {
  // Accept 0 messages
}
```

With:
```typescript
expect(wsMonitor.messages.length).toBeGreaterThan(0);
```

## Files Requiring Immediate Attention

1. **test_dashboard.spec.ts** - WebSocket test is useless
2. **test_task_breakdown.spec.ts** - Too many conditional skips
3. **test-utils.ts** - `checkTestErrors` is too permissive
4. **All test files** - Error filter lists too broad

## Metrics

| Issue Type | Count | Severity |
|------------|-------|----------|
| Error filter masking | 8 files | CRITICAL |
| Conditional skips | 11 instances | CRITICAL |
| WebSocket 0-message acceptance | 1 instance | CRITICAL |
| `.catch(() => false)` | 40+ instances | HIGH |
| `toBeAttached()` misuse | 23 instances | MEDIUM |
| Console.log not assertion | 20+ instances | LOW |
