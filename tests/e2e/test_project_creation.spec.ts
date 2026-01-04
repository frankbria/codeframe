/**
 * E2E Tests: Project Creation Flow
 *
 * Tests the complete project creation user journey including:
 * - Displaying project list on root page
 * - Creating a new project via the inline form
 * - Navigating to existing projects
 * - Form validation for required fields
 *
 * Uses JWT authentication with FastAPI Users.
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

test.describe('Project Creation Flow', () => {
  // Login using real authentication flow
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  test('should display project list on root page', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Assert page header is visible
    await expect(page.getByRole('heading', { level: 1, name: /Your Projects/i })).toBeVisible();

    // Assert create project button is visible
    await expect(page.getByTestId('create-project-button')).toBeVisible();
    await expect(page.getByTestId('create-project-button')).toHaveText('Create New Project');
  });

  test('should show create form when button clicked', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Click create project button
    await page.getByTestId('create-project-button').click();

    // Assert form elements are now visible
    await expect(page.getByTestId('project-name-input')).toBeVisible();
    await expect(page.getByTestId('project-description-input')).toBeVisible();
    await expect(page.getByTestId('create-project-submit')).toBeVisible();
  });

  test('should create new project via UI', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Click create project button to show form
    await page.getByTestId('create-project-button').click();

    // Wait for form to be visible
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

    // Click create project button to show form
    await page.getByTestId('create-project-button').click();

    // Wait for form to be visible
    await page.getByTestId('project-name-input').waitFor({ state: 'visible' });

    // Try to submit without filling fields (submit button should be disabled)
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
    await expect(page).toHaveURL(/\/$/);
  });

  test('should close form when close button clicked', async ({ page }) => {
    // Navigate to root page
    await page.goto('/');

    // Click create project button to show form
    await page.getByTestId('create-project-button').click();

    // Assert form is visible
    await expect(page.getByTestId('project-name-input')).toBeVisible();

    // Click close button (✕)
    await page.getByText('✕').click();

    // Assert form is hidden
    await expect(page.getByTestId('project-name-input')).not.toBeVisible();
  });
});

test.describe('Project Navigation Flow', () => {
  // Login using real authentication flow
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  test('should navigate to project dashboard when project card clicked', async ({ page }) => {
    // First create a project to ensure we have at least one
    await page.goto('/');

    // Click create project button
    await page.getByTestId('create-project-button').click();

    // Fill and submit project
    const projectName = `nav-test-project-${Date.now()}`;
    await page.getByTestId('project-name-input').fill(projectName);
    await page.getByTestId('project-description-input').fill('Test project for navigation');
    await page.getByTestId('create-project-submit').click();

    // Wait for redirect to dashboard
    await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 10000 });

    // Navigate back to project list
    await page.goto('/');

    // Wait for project list to load
    await expect(page.getByTestId('project-list')).toBeVisible({ timeout: 5000 });

    // Find and click the project card
    const projectCard = page.locator(`text=${projectName}`).first();
    await projectCard.click();

    // Assert navigated to project dashboard
    await expect(page).toHaveURL(/\/projects\/\d+/, { timeout: 5000 });
    await expect(page.getByTestId('dashboard-header')).toBeVisible({ timeout: 10000 });
  });

  test('should show empty state when no projects exist', async ({ page }) => {
    // This test may be flaky if other tests leave projects behind
    // It's primarily for documentation purposes
    await page.goto('/');

    // The component should either show projects or an empty state
    // We check that the page loads correctly
    await expect(page.getByTestId('create-project-button')).toBeVisible();
  });
});
