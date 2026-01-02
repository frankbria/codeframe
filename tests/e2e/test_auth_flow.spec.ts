/**
 * E2E Tests: Authentication Flow
 *
 * Tests the complete authentication user journey including:
 * - Login page rendering
 * - Successful login with valid credentials
 * - Error handling for invalid credentials
 * - Logout functionality
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

test.describe('Authentication Flow', () => {
  // Clear session storage before each test to ensure we start logged out
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('should render login page', async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');

    // Assert login form elements are visible
    await expect(page.getByTestId('email-input')).toBeVisible();
    await expect(page.getByTestId('password-input')).toBeVisible();
    await expect(page.getByTestId('login-button')).toBeVisible();
  });

  test('should login successfully with valid credentials', async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');

    // Fill in credentials
    await page.getByTestId('email-input').fill('test@example.com');
    await page.getByTestId('password-input').fill('testpassword123');

    // Click login button
    await page.getByTestId('login-button').click();

    // Assert redirect to root or projects page
    await expect(page).toHaveURL(/^\/(projects)?$/);

    // Assert user menu is visible (logged in state)
    await expect(page.getByTestId('user-menu')).toBeVisible();
  });

  test('should show error with invalid credentials', async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');

    // Fill in invalid credentials
    await page.getByTestId('email-input').fill('test@example.com');
    await page.getByTestId('password-input').fill('WrongPassword123');

    // Click login button
    await page.getByTestId('login-button').click();

    // Wait for error message to appear
    await page.waitForSelector('[data-testid="auth-error"]', {
      state: 'visible',
      timeout: 5000
    });

    // Assert error message is shown
    const errorElement = page.getByTestId('auth-error');
    await expect(errorElement).toBeVisible();
    await expect(errorElement).toContainText(/invalid|failed|credentials/i);

    // Assert still on login page
    await expect(page).toHaveURL(/\/login/);
  });

  test('should logout successfully', async ({ page }) => {
    // Login using helper function
    await loginUser(page);

    // Assert we're logged in
    await expect(page.getByTestId('user-menu')).toBeVisible();

    // Click logout button
    await page.getByTestId('logout-button').click();

    // Assert redirect to login page
    await expect(page).toHaveURL(/\/login/);

    // Assert login form is visible (logged out state)
    await expect(page.getByTestId('email-input')).toBeVisible();
  });
});
