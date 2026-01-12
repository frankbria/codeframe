/**
 * E2E Tests for Assign Tasks Button (Issue #248)
 *
 * Tests the "Assign Tasks" button functionality in the TaskList component.
 * This button allows users to manually trigger task assignment for stuck
 * pending tasks that haven't been automatically assigned.
 *
 * Test Project: PROJECT_ID=7 (e2e-assign-tasks-project)
 * - Active phase project
 * - Has pending unassigned tasks (triggers button visibility)
 * - NO in-progress tasks (ensures button is enabled)
 */

import { test, expect, Page } from '@playwright/test';
import { TEST_PROJECT_IDS, FRONTEND_URL, BACKEND_URL } from './e2e-config';
import { loginUser } from './test-utils';

// Use Project 7 which is specifically seeded for Assign Tasks button testing
const PROJECT_ID = TEST_PROJECT_IDS.ASSIGN_TASKS;

test.describe('Assign Tasks Button', () => {
  test.beforeEach(async ({ page }) => {
    // Login and navigate to the project
    await loginUser(page);
  });

  test('should display Assign Tasks banner when pending unassigned tasks exist @smoke', async ({ page }) => {
    // Navigate to the project dashboard
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);

    // Wait for dashboard to load
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();

    // Wait for TaskList to load
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Verify the Assign Tasks banner is visible
    const banner = page.getByTestId('assign-tasks-banner');
    await expect(banner).toBeVisible();

    // Verify the banner contains informative text about tasks waiting assignment
    await expect(banner).toContainText(/waiting.*assigned|assigned.*agents/i);
  });

  test('should display Assign Tasks button that is clickable', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Find the Assign Tasks button
    const button = page.getByTestId('assign-tasks-button');
    await expect(button).toBeVisible();
    await expect(button).toBeEnabled();

    // Verify button text
    await expect(button).toContainText(/assign.*tasks/i);
  });

  test('should call API when Assign Tasks button is clicked', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Setup API response interception
    let apiCalled = false;
    let apiRequestBody: unknown = null;

    await page.route(`**/api/projects/${PROJECT_ID}/tasks/assign`, async (route) => {
      apiCalled = true;
      apiRequestBody = route.request().postData();

      // Return a success response
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          pending_count: 3,
          message: 'Started execution for 3 pending tasks',
        }),
      });
    });

    // Click the Assign Tasks button
    const button = page.getByTestId('assign-tasks-button');
    await button.click();

    // Wait for the API call to complete
    await page.waitForTimeout(500);

    // Verify API was called
    expect(apiCalled).toBe(true);
  });

  test('should show loading state while assigning tasks', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Setup a delayed API response to observe loading state
    await page.route(`**/api/projects/${PROJECT_ID}/tasks/assign`, async (route) => {
      // Delay response to allow loading state to be visible
      await new Promise((resolve) => setTimeout(resolve, 500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          pending_count: 3,
          message: 'Started execution for 3 pending tasks',
        }),
      });
    });

    // Click the button
    const button = page.getByTestId('assign-tasks-button');
    await button.click();

    // Verify loading state is shown (button text changes or spinner appears)
    // The button should be disabled during loading
    await expect(button).toBeDisabled();

    // Wait for loading to complete
    await page.waitForTimeout(600);

    // Button should be re-enabled after loading completes
    // (unless tasks were assigned and banner disappears)
  });

  test('should display error message when API call fails', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Setup API to return error
    await page.route(`**/api/projects/${PROJECT_ID}/tasks/assign`, async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Internal server error',
        }),
      });
    });

    // Click the button
    const button = page.getByTestId('assign-tasks-button');
    await button.click();

    // Wait for error to be displayed
    await page.waitForTimeout(500);

    // Verify error message is shown (use the specific test ID)
    const errorMessage = page.getByTestId('assignment-error');
    await expect(errorMessage).toBeVisible();
  });

  test('should handle "no pending tasks" response gracefully', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Setup API to return "no pending tasks" response
    await page.route(`**/api/projects/${PROJECT_ID}/tasks/assign`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          pending_count: 0,
          message: 'No pending unassigned tasks to execute',
        }),
      });
    });

    // Click the button
    const button = page.getByTestId('assign-tasks-button');
    await button.click();

    // Should not show an error - this is a valid response
    await page.waitForTimeout(500);

    // No error should be visible
    const errorElement = page.locator('[data-testid="assignment-error"]');
    await expect(errorElement).not.toBeVisible();
  });
});

test.describe('Assign Tasks Button - Visibility Conditions', () => {
  test.beforeEach(async ({ page }) => {
    await loginUser(page);
  });

  test('should NOT show Assign Tasks banner when no pending unassigned tasks', async ({ page }) => {
    // Use Project 5 (completed) which has no pending tasks
    const completedProjectId = TEST_PROJECT_IDS.COMPLETED;

    await page.goto(`${FRONTEND_URL}/projects/${completedProjectId}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab if visible (may not be present for completed projects)
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    if (await tasksTab.isVisible()) {
      await tasksTab.click();
      await page.waitForTimeout(500);

      // The Assign Tasks banner should NOT be visible
      const banner = page.getByTestId('assign-tasks-banner');
      await expect(banner).not.toBeVisible();
    }
  });

  test('should show button as disabled when tasks are in progress', async ({ page }) => {
    // Use Project 3 (active) which has in_progress tasks
    const activeProjectId = TEST_PROJECT_IDS.ACTIVE;

    await page.goto(`${FRONTEND_URL}/projects/${activeProjectId}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // The banner may or may not be visible depending on task state
    // But if there's a button, it should be disabled because there are in_progress tasks
    const button = page.getByTestId('assign-tasks-button');
    if (await button.isVisible()) {
      await expect(button).toBeDisabled();
    }
  });
});

test.describe('Assign Tasks Button - API Integration', () => {
  test.beforeEach(async ({ page }) => {
    await loginUser(page);
  });

  test('should include auth token in API request', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForSelector('[data-testid="dashboard-header"]', { timeout: 10000 });

    // Navigate to Tasks tab
    const tasksTab = page.getByRole('tab', { name: /tasks/i });
    await tasksTab.click();
    await page.waitForSelector('[data-testid="task-list"]', { timeout: 10000 });

    // Capture the API request to verify auth header
    let authHeader: string | null = null;

    await page.route(`**/api/projects/${PROJECT_ID}/tasks/assign`, async (route) => {
      authHeader = route.request().headers()['authorization'] || null;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          pending_count: 3,
          message: 'Started execution',
        }),
      });
    });

    // Click the button
    const button = page.getByTestId('assign-tasks-button');
    await button.click();
    await page.waitForTimeout(500);

    // Verify auth header was included
    expect(authHeader).toBeTruthy();
    expect(authHeader).toContain('Bearer');
  });
});
