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
  checkTestErrors,
  ExtendedPage,
  waitForAPIResponse
} from './test-utils';
import { FRONTEND_URL, BACKEND_URL, TEST_PROJECT_IDS } from './e2e-config';

// Skip tests if no API key (can't generate tasks without Claude)
const HAS_API_KEY = !!process.env.ANTHROPIC_API_KEY;

// Use the planning phase project for task approval tests
const PROJECT_ID = TEST_PROJECT_IDS.PLANNING;

test.describe('Task Approval API Contract', () => {
  test.beforeEach(async ({ context, page }) => {
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await context.clearCookies();
    await loginUser(page);
  });

  test.afterEach(async ({ page }) => {
    checkTestErrors(page, 'Task approval test', [
      'net::ERR_ABORTED', // Normal when navigation cancels pending requests
      'Failed to fetch RSC payload' // Next.js RSC during navigation - transient
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
  test('should send correct request body format for task approval', async ({ page }) => {
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

    // Navigate to Tasks tab
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});

    if (await tasksTab.isVisible()) {
      await tasksTab.click();

      // Look for TaskReview component (only present in planning phase)
      const taskReview = page.locator('[role="tree"]'); // TaskReview uses role="tree"
      const approveButton = page.getByRole('button', { name: /approve/i });

      // Only proceed if we're in planning phase with task review available
      if (await taskReview.isVisible().catch(() => false) && await approveButton.isVisible().catch(() => false)) {
        // Click approve button
        await approveButton.click();

        // Wait for API call to complete (success or error)
        await page.waitForResponse(
          response => response.url().includes('/tasks/approve'),
          { timeout: 10000 }
        ).catch(() => {});

        // Validate the request body format
        if (approvalRequestIntercepted && capturedRequestBody) {
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
        }
      } else {
        // Not in planning phase - skip test but don't fail
        console.log('[Task Approval] Project not in planning phase - skipping approval validation');
        test.skip(true, 'Project not in planning phase');
      }
    }
  });

  /**
   * Test that 422 validation errors from task approval are properly handled.
   *
   * This test mocks a 422 response to verify the frontend handles it gracefully.
   */
  test('should handle 422 validation error gracefully', async ({ page }) => {
    let responseStatus: number | null = null;

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

    // Navigate to Tasks tab
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});

    if (await tasksTab.isVisible()) {
      await tasksTab.click();

      // Look for approve button
      const approveButton = page.getByRole('button', { name: /approve/i });

      if (await approveButton.isVisible().catch(() => false)) {
        // Click approve button
        await approveButton.click();

        // Wait for response
        const response = await page.waitForResponse(
          r => r.url().includes('/tasks/approve'),
          { timeout: 10000 }
        ).catch(() => null);

        if (response) {
          responseStatus = response.status();

          // Verify 422 was received
          expect(responseStatus).toBe(422);

          // Verify UI shows error message (not a blank screen)
          const errorMessage = page.locator('[class*="destructive"], [class*="error"], [role="alert"]');
          await errorMessage.first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});

          // Should display some error feedback
          const hasErrorUI = await errorMessage.count() > 0 ||
            await page.getByText(/failed|error|try again/i).isVisible().catch(() => false);

          expect(hasErrorUI).toBe(true);
        }
      } else {
        console.log('[Task Approval] Approve button not visible - project may not be in planning phase');
        test.skip(true, 'Project not in planning phase');
      }
    }
  });

  /**
   * Test the full task approval flow with API response validation.
   *
   * Only runs when ANTHROPIC_API_KEY is available (needed for task generation).
   */
  test(HAS_API_KEY ? 'should complete task approval with correct API response' : 'skip: requires ANTHROPIC_API_KEY',
    async ({ page }) => {
      test.skip(!HAS_API_KEY, 'Requires ANTHROPIC_API_KEY for task generation');

      let approvalResponse: any = null;

      // Capture the approval response
      page.on('response', async response => {
        if (response.url().includes('/tasks/approve') && response.request().method() === 'POST') {
          const status = response.status();

          // Fail fast on 422 - this was the original bug
          if (status === 422) {
            const body = await response.json().catch(() => ({}));
            throw new Error(
              `Task approval returned 422 Validation Error!\n` +
              `This indicates a frontend/backend contract mismatch.\n` +
              `Response: ${JSON.stringify(body, null, 2)}`
            );
          }

          if (status === 200) {
            approvalResponse = await response.json().catch(() => null);
          }
        }
      });

      // Navigate to project
      await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
      await page.waitForLoadState('networkidle');

      // Navigate to Tasks tab
      const tasksTab = page.locator('[data-testid="tasks-tab"]');
      if (await tasksTab.isVisible().catch(() => false)) {
        await tasksTab.click();

        const approveButton = page.getByRole('button', { name: /approve/i });

        if (await approveButton.isVisible().catch(() => false)) {
          await approveButton.click();

          // Wait for approval to complete
          await page.waitForResponse(
            r => r.url().includes('/tasks/approve'),
            { timeout: 15000 }
          ).catch(() => {});

          // Validate response format
          if (approvalResponse) {
            expect(approvalResponse).toHaveProperty('success');
            expect(approvalResponse).toHaveProperty('phase');
            expect(approvalResponse).toHaveProperty('approved_count');
            expect(approvalResponse).toHaveProperty('excluded_count');
            expect(approvalResponse).toHaveProperty('message');

            console.log('[Task Approval] API response validated:', approvalResponse);
          }
        }
      }
    }
  );
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
    // Get auth token
    const authToken = await page.evaluate(() => localStorage.getItem('auth_token'));
    test.skip(!authToken, 'No auth token available');

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
   * Negative test: Verify 422 is returned for incorrect format.
   *
   * This documents the expected backend behavior.
   */
  test('should return 422 for incorrect request body format', async ({ page, request }) => {
    // Get auth token
    const authToken = await page.evaluate(() => localStorage.getItem('auth_token'));
    test.skip(!authToken, 'No auth token available');

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

    // Should be 422 (validation error) because "approved" field is missing
    // and "task_ids" is an unknown field
    expect(status).toBe(422);

    const body = await response.json();
    expect(body).toHaveProperty('detail');

    console.log('[API Contract] Incorrect format correctly rejected with 422');
  });
});
