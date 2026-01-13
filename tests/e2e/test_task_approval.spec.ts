/**
 * E2E Tests: Task Approval API Contract
 *
 * Tests the task approval flow to catch request body mismatches.
 * This test was added after a bug where the frontend sent { task_ids: [...] }
 * but the backend expected { approved: bool, excluded_task_ids: [...] },
 * causing HTTP 422 validation errors.
 *
 * Key validations:
 * 1. Request body format matches backend Pydantic model
 * 2. No 422 validation errors occur
 * 3. API response matches expected format
 */

import { test, expect, type Route, type Request } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrorsWithBrowserFilters,
  ExtendedPage,
  waitForAPIResponse
} from './test-utils';
import { FRONTEND_URL, BACKEND_URL, TEST_PROJECT_IDS } from './e2e-config';

// Skip tests if no API key (can't generate tasks without Claude)
const HAS_API_KEY = !!process.env.ANTHROPIC_API_KEY;

// Use the planning phase project for task approval tests
// WARNING: Multiple test suites share this project ID.
// Approval tests mutate state (planning → active phase).
// Tests must run serially to avoid race conditions.
const PROJECT_ID = TEST_PROJECT_IDS.PLANNING;

// Wrap all tests in serial describe to prevent parallel execution issues
// (approval tests mutate shared project state)
test.describe.serial('Task Approval Tests', () => {

test.describe('Task Approval API Contract', () => {
  test.beforeEach(async ({ context, page }) => {
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await context.clearCookies();
    await loginUser(page);
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Task approval test', [
      'net::ERR_ABORTED', // Normal when navigation cancels pending requests
      'Failed to fetch RSC payload', // Next.js RSC during navigation - transient
      'NS_BINDING_ABORTED', // Firefox: Normal when navigation cancels requests
      'Load request cancelled' // WebKit/Safari: Normal when navigation cancels requests
    ]);
  });

  /**
   * Test that the task approval request body matches the backend contract.
   *
   * Backend expects (Pydantic model in tasks.py):
   * {
   *   "approved": bool,
   *   "excluded_task_ids": List[int]
   * }
   *
   * Frontend must NOT send:
   * - { task_ids: [...] }  // Wrong field name
   * - { approved_task_ids: [...] }  // Wrong approach
   * - Missing "approved" field
   */
  test('should send correct request body format for task approval @smoke', async ({ page }) => {
    let capturedRequestBody: any = null;
    let approvalRequestIntercepted = false;

    // Intercept the task approval API call to capture and validate request body
    await page.route('**/api/projects/*/tasks/approve', async (route: Route, request: Request) => {
      approvalRequestIntercepted = true;
      const postData = request.postData();

      if (postData) {
        try {
          capturedRequestBody = JSON.parse(postData);
        } catch {
          capturedRequestBody = { _parseError: postData };
        }
      }

      // Continue with the actual request
      await route.continue();
    });

    // Navigate to project with tasks in planning phase
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Navigate to Tasks tab - MUST be visible for planning phase project
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await expect(tasksTab).toBeVisible({ timeout: 10000 });
    await tasksTab.click();

    // Look for TaskReview component and approve button
    // These MUST be visible for a planning phase project with tasks
    const taskReview = page.locator('[role="tree"]');
    const approveButton = page.getByRole('button', { name: /approve/i });

    await expect(taskReview).toBeVisible({ timeout: 10000 });
    await expect(approveButton).toBeVisible({ timeout: 5000 });

    // Click approve button
    await approveButton.click();

    // Wait for API call to complete
    await page.waitForResponse(
      response => response.url().includes('/tasks/approve'),
      { timeout: 10000 }
    );

    // Validate the request body format was captured
    expect(approvalRequestIntercepted).toBe(true);
    expect(capturedRequestBody).toBeTruthy();

    // CRITICAL ASSERTIONS: These would have caught the original bug

    // 1. Must have "approved" field (boolean)
    expect(capturedRequestBody).toHaveProperty('approved');
    expect(typeof capturedRequestBody.approved).toBe('boolean');

    // 2. Must have "excluded_task_ids" field (array)
    expect(capturedRequestBody).toHaveProperty('excluded_task_ids');
    expect(Array.isArray(capturedRequestBody.excluded_task_ids)).toBe(true);

    // 3. Must NOT have "task_ids" field (the buggy format)
    expect(capturedRequestBody).not.toHaveProperty('task_ids');

    // 4. excluded_task_ids should contain integers, not strings
    if (capturedRequestBody.excluded_task_ids.length > 0) {
      capturedRequestBody.excluded_task_ids.forEach((id: any) => {
        expect(typeof id).toBe('number');
      });
    }

    console.log('[Task Approval] Request body validated successfully:', capturedRequestBody);
  });

  /**
   * Test that 422 validation errors from task approval are properly handled.
   *
   * This test mocks a 422 response to verify the frontend handles it gracefully.
   */
  test('should handle 422 validation error gracefully', async ({ page }) => {
    // Mock a 422 validation error response
    await page.route('**/api/projects/*/tasks/approve', async (route: Route) => {
      await route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: [
            {
              loc: ['body', 'approved'],
              msg: 'field required',
              type: 'value_error.missing'
            }
          ]
        })
      });
    });

    // Navigate to project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Navigate to Tasks tab - MUST be visible for planning phase project
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await expect(tasksTab).toBeVisible({ timeout: 10000 });
    await tasksTab.click();

    // Look for approve button - MUST be visible
    const approveButton = page.getByRole('button', { name: /approve/i });
    await expect(approveButton).toBeVisible({ timeout: 5000 });

    // Click approve button
    await approveButton.click();

    // Wait for response
    const response = await page.waitForResponse(
      r => r.url().includes('/tasks/approve'),
      { timeout: 10000 }
    );

    // Verify 422 was received (mocked response)
    expect(response.status()).toBe(422);

    // Verify UI shows error message (not a blank screen)
    // Use explicit assertion - FAIL if no error UI appears
    const errorIndicators = page.locator('[class*="destructive"], [class*="error"], [role="alert"]');
    const errorText = page.getByText(/failed|error|try again/i);

    // At least one error indicator must be visible
    await expect(
      errorIndicators.first().or(errorText.first())
    ).toBeVisible({ timeout: 5000 });
  });

});

/**
 * Tests requiring ANTHROPIC_API_KEY.
 * Skip entire suite if key is not available.
 */
test.describe('Task Approval - API Key Required Tests', () => {
  // Skip entire suite if no API key
  test.skip(!HAS_API_KEY, 'Requires ANTHROPIC_API_KEY');

  test.beforeEach(async ({ context, page }) => {
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await context.clearCookies();
    await loginUser(page);
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'API key required test', [
      'net::ERR_ABORTED',
      'Failed to fetch RSC payload',
      'NS_BINDING_ABORTED',
      'Load request cancelled'
    ]);
  });

  /**
   * Test the full task approval flow with API response validation.
   */
  test('should complete task approval with correct API response', async ({ page }) => {
    // Navigate to project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Navigate to Tasks tab - MUST be visible
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await expect(tasksTab).toBeVisible({ timeout: 10000 });
    await tasksTab.click();

    // Approve button - MUST be visible
    const approveButton = page.getByRole('button', { name: /approve/i });
    await expect(approveButton).toBeVisible({ timeout: 5000 });

    // Click and wait for response in parallel to avoid race condition
    const [response] = await Promise.all([
      page.waitForResponse(
        r => r.url().includes('/tasks/approve') && r.request().method() === 'POST',
        { timeout: 15000 }
      ),
      approveButton.click()
    ]);

    // Fail fast on 422 - this was the original bug
    const status = response.status();
    if (status === 422) {
      const body = await response.json();
      throw new Error(
        `Task approval returned 422 Validation Error!\n` +
        `This indicates a frontend/backend contract mismatch.\n` +
        `Response: ${JSON.stringify(body, null, 2)}`
      );
    }

    expect(status).toBe(200);

    // Parse and validate response format synchronously
    const approvalResponse = await response.json();
    expect(approvalResponse).toHaveProperty('success');
    expect(approvalResponse).toHaveProperty('phase');
    expect(approvalResponse).toHaveProperty('approved_count');
    expect(approvalResponse).toHaveProperty('excluded_count');
    expect(approvalResponse).toHaveProperty('message');

    console.log('[Task Approval] API response validated:', approvalResponse);
  });
});

/**
 * Integration test for API contract between frontend and backend.
 *
 * These tests verify the contract without requiring the full UI flow.
 */
test.describe('Task Approval API Contract - Direct API Tests', () => {
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  /**
   * Test the API directly to verify contract.
   *
   * This catches mismatches even if the UI is never exercised.
   */
  test('should accept correct request body format via direct API call', async ({ page, request }) => {
    // Get auth token - loginUser() was called in beforeEach
    const authToken = await page.evaluate(() => localStorage.getItem('auth_token'));
    expect(authToken).toBeTruthy();  // FAIL if login didn't work

    // Make direct API call with correct format
    const response = await request.post(
      `${BACKEND_URL}/api/projects/${PROJECT_ID}/tasks/approve`,
      {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        },
        data: {
          approved: true,
          excluded_task_ids: []
        }
      }
    );

    const status = response.status();

    // Should NOT be 422 (validation error) with correct format
    expect(status).not.toBe(422);

    // Acceptable statuses: 200 (success), 400 (not in planning phase), 404 (project not found)
    // All of these indicate the request format was valid
    expect([200, 400, 403, 404]).toContain(status);

    if (status === 200) {
      const body = await response.json();
      expect(body).toHaveProperty('success');
    }

    console.log(`[API Contract] Direct API call returned ${status} - format accepted`);
  });

  /**
   * Negative test: Verify incorrect format is rejected.
   *
   * This documents the expected backend behavior.
   * Note: If project already transitioned to active phase from earlier tests,
   * backend may return 400 (phase check) before Pydantic validation (422).
   * Both responses indicate the invalid request was properly rejected.
   */
  test('should reject incorrect request body format', async ({ page, request }) => {
    // Get auth token - loginUser() was called in beforeEach
    const authToken = await page.evaluate(() => localStorage.getItem('auth_token'));
    expect(authToken).toBeTruthy();  // FAIL if login didn't work

    // Make direct API call with INCORRECT format (the buggy format)
    const response = await request.post(
      `${BACKEND_URL}/api/projects/${PROJECT_ID}/tasks/approve`,
      {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        },
        data: {
          task_ids: ['task-1', 'task-2', 'task-3'] // WRONG FORMAT
        }
      }
    );

    const status = response.status();

    // Accept 422 (validation error) or 400 (phase check failed first)
    // Either response indicates the invalid request was rejected
    expect([400, 422]).toContain(status);

    const body = await response.json();
    expect(body).toHaveProperty('detail');

    console.log(`[API Contract] Incorrect format correctly rejected with ${status}`);
  });
});

/**
 * Multi-Agent Execution Tests - P0 Blocker Fix (Direct API Tests)
 *
 * After task approval transitions to Development phase, verify that:
 * 1. Approval returns immediately (background task doesn't block)
 * 2. WebSocket receives development_started event
 *
 * These are direct API tests that don't depend on UI state.
 * They use TEST_PROJECT_IDS.PLANNING which is seeded in planning phase.
 *
 * Note: These tests require ANTHROPIC_API_KEY to actually create agents.
 * Without the key, approval succeeds but agent creation is skipped.
 */
test.describe('Multi-Agent Execution After Task Approval - Direct API Tests', () => {
  // Use loginUser() helper in beforeEach per E2E test coding guidelines
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  /**
   * Test that approval returns immediately without waiting for agent execution.
   *
   * The background task should not block the approval response.
   * This is a critical test for the P0 fix - ensures non-blocking behavior.
   *
   * Note: If earlier tests in the serial suite already approved the project,
   * this will return 400 instead of 200. Either way, we verify response time.
   */
  test('should return approval response immediately without blocking', async ({ page, request }) => {
    // Get auth token from localStorage (set by loginUser() in beforeEach)
    const authToken = await page.evaluate(() => localStorage.getItem('auth_token'));
    expect(authToken).toBeTruthy();

    const startTime = Date.now();

    // Make direct API call for approval
    const response = await request.post(
      `${BACKEND_URL}/api/projects/${PROJECT_ID}/tasks/approve`,
      {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        },
        data: {
          approved: true,
          excluded_task_ids: []
        }
      }
    );

    const elapsed = Date.now() - startTime;
    const status = response.status();

    // PRIMARY ASSERTION: Response should return quickly (< 5 seconds)
    // This is the critical P0 fix - agent creation happens in background
    expect(elapsed).toBeLessThan(5000);

    // Accept 200 (first approval) or 400 (project already transitioned)
    // Both are valid depending on test execution order
    expect([200, 400]).toContain(status);

    if (status === 200) {
      const responseData = await response.json();
      expect(responseData.success).toBe(true);
      expect(responseData.phase).toBe('active');
      console.log(`[Multi-Agent] Approval returned in ${elapsed}ms - confirmed non-blocking`);
      console.log(`[Multi-Agent] Approved ${responseData.approved_count} tasks`);
    } else {
      console.log(`[Multi-Agent] Project already approved (${status}) - response time: ${elapsed}ms`);
    }
  });
});

}); // End of serial describe wrapper
