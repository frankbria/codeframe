/**
 * E2E Tests: Project Creation Flow
 *
 * Tests the complete project creation user journey including:
 * - Displaying root page with create project option
 * - Creating a new project via UI
 * - Form validation for required fields
 *
 * Uses unified BetterAuth authentication system aligned with CodeFRAME's
 * existing `users` and `sessions` tables (plural naming).
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

test.describe('Project Creation Flow', () => {
  // Login using real authentication flow
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  test('should display root page with create project form', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Assert project creation form is visible (shown directly on root page)
    await expect(page.getByTestId('project-name-input')).toBeVisible();
    await expect(page.getByTestId('project-description-input')).toBeVisible();
    await expect(page.getByTestId('create-project-submit')).toBeVisible();

    // Assert welcome message is visible
    await expect(page.getByText('Welcome to CodeFRAME')).toBeVisible();
  });

  test('should create new project via UI', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Wait for form to be visible (it's shown directly, no button to click)
    await page.getByTestId('project-name-input').waitFor({ state: 'visible' });

    // Fill project name
    const projectName = `my-e2e-test-project-${Date.now()}`;
    await page.getByTestId('project-name-input').fill(projectName);

    // Fill project description
    await page.getByTestId('project-description-input').fill('Created via E2E test');

    // Click submit button
    await page.getByTestId('create-project-submit').click();

    // Assert redirect to project dashboard (proves project was created successfully)
    await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 10000 });

    // Verify dashboard loads successfully with the new project
    await expect(page.getByTestId('dashboard-header')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('h1')).toContainText(projectName);

    // Extract project ID from URL for verification
    const currentUrl = page.url();
    const projectId = currentUrl.match(/\/projects\/(\d+)/)?.[1];
    expect(projectId).toBeTruthy();
  });

  test('should validate project name is required', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Wait for form to be visible
    await page.getByTestId('project-name-input').waitFor({ state: 'visible' });

    // Try to submit without filling fields (submit button should be disabled)
    // First check if button is disabled
    const submitButton = page.getByTestId('create-project-submit');
    await expect(submitButton).toBeDisabled();

    // Fill description but not name to trigger validation
    await page.getByTestId('project-description-input').fill('Test description without name');

    // Submit button should still be disabled since name is empty
    await expect(submitButton).toBeDisabled();

    // Fill an invalid name (too short) to trigger different validation
    await page.getByTestId('project-name-input').fill('ab');
    await page.getByTestId('project-name-input').blur();

    // Wait for validation error to appear
    await page.waitForSelector('[data-testid="form-error-name"]', {
      state: 'visible',
      timeout: 3000
    });

    // Assert form error is shown
    const errorElement = page.getByTestId('form-error-name');
    await expect(errorElement).toBeVisible();
    await expect(errorElement).toContainText(/at least 3 characters|project name/i);

    // Assert we're still on the root page (not redirected)
    await expect(page).toHaveURL(/\/$/); // Matches URLs ending with /
  });
});
