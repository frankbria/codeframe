/**
 * E2E Tests: Project Creation Flow
 *
 * Tests the complete project creation user journey including:
 * - Displaying root page with create project option
 * - Creating a new project via UI
 * - Form validation for required fields
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

test.describe('Project Creation Flow', () => {
  // Clear session and login before each test
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  test('should display root page with create project option', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Assert create project button is visible
    await expect(page.getByTestId('create-project-button')).toBeVisible();

    // Assert project list container is visible
    await expect(page.getByTestId('project-list')).toBeVisible();
  });

  test('should create new project via UI', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Click create project button
    await page.getByTestId('create-project-button').click();

    // Fill project name
    const projectName = `my-e2e-test-project-${Date.now()}`;
    await page.getByTestId('project-name-input').fill(projectName);

    // Fill project description
    await page.getByTestId('project-description-input').fill('Created via E2E test');

    // Click submit button
    await page.getByTestId('create-project-submit').click();

    // Assert redirect to project dashboard
    await expect(page).toHaveURL(/\/projects\/\d+/);

    // Assert dashboard header is visible (indicating successful creation)
    await expect(page.getByTestId('dashboard-header')).toBeVisible();

    // Assert project name is displayed in dashboard
    await expect(page.locator('h1')).toContainText(projectName);
  });

  test('should validate project name is required', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Click create project button
    await page.getByTestId('create-project-button').click();

    // Click submit without filling fields
    await page.getByTestId('create-project-submit').click();

    // Wait for validation error to appear
    await page.waitForSelector('[data-testid="form-error"]', {
      state: 'visible',
      timeout: 3000
    });

    // Assert form error is shown
    const errorElement = page.getByTestId('form-error').first();
    await expect(errorElement).toBeVisible();
    await expect(errorElement).toContainText(/project name is required/i);

    // Assert we're still on the root page (not redirected)
    await expect(page).toHaveURL(/^\/$/);
  });
});
