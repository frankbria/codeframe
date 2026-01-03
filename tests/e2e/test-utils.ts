/**
 * Test utilities for E2E tests
 */

import type { Page } from '@playwright/test';

/**
 * Log optional operation warnings (for operations that are expected to fail sometimes)
 *
 * Use this for operations like:
 * - Waiting for responses that might not happen
 * - Waiting for elements that might not be present
 * - Scrolling to elements that might not exist
 *
 * @param operation - Description of the operation
 * @param error - The error that occurred
 *
 * @example
 * await page.waitForResponse(...).catch((err) => logOptionalWarning('project API response', err));
 */
export function logOptionalWarning(operation: string, error: Error): void {
  if (process.env.DEBUG_TESTS) {
    console.warn(`[Test] Optional operation timed out (expected in some cases): ${operation}`);
    console.warn(`  Error: ${error.message}`);
  }
}

/**
 * Wrap a promise with optional error logging
 *
 * @param promise - The promise to wrap
 * @param operation - Description of the operation for logging
 *
 * @example
 * await withOptionalWarning(
 *   page.waitForResponse(response => response.url().includes('/api/')),
 *   'API response'
 * );
 */
export async function withOptionalWarning<T>(
  promise: Promise<T>,
  operation: string
): Promise<T | undefined> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof Error) {
      logOptionalWarning(operation, error);
    }
    return undefined;
  }
}

/**
 * Login a user via the login page UI
 *
 * Uses JWT authentication - token is stored in localStorage after successful login.
 *
 * @param page - Playwright page object
 * @param email - User email (defaults to test user)
 * @param password - User password (defaults to test password)
 */
export async function loginUser(
  page: Page,
  email = 'test@example.com',
  password = 'Testpassword123'
): Promise<void> {
  // Navigate to login page
  await page.goto('/login');

  // Fill in credentials using data-testid selectors
  await page.getByTestId('email-input').fill(email);
  await page.getByTestId('password-input').fill(password);

  // Click login button
  await page.getByTestId('login-button').click();

  // Wait for redirect to root page or projects page (URL includes full host)
  await page.waitForURL(/\/(projects)?$/);
}

/**
 * Register a new user via the signup page UI
 *
 * Uses JWT authentication - token is stored in localStorage after successful registration.
 *
 * @param page - Playwright page object
 * @param name - User's full name
 * @param email - User email
 * @param password - User password (must meet strength requirements)
 */
export async function registerUser(
  page: Page,
  name: string,
  email: string,
  password: string
): Promise<void> {
  // Navigate to signup page
  await page.goto('/signup');

  // Fill in registration form
  await page.getByTestId('name-input').fill(name);
  await page.getByTestId('email-input').fill(email);
  await page.getByTestId('password-input').fill(password);
  await page.getByTestId('confirm-password-input').fill(password);

  // Click signup button
  await page.getByTestId('signup-button').click();

  // Wait for redirect to root page (auto-login after registration, URL includes full host)
  await page.waitForURL(/\/(projects)?$/);
}

/**
 * Check if user is authenticated by checking localStorage for auth token
 *
 * @param page - Playwright page object
 * @returns true if auth_token exists in localStorage
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  const token = await page.evaluate(() => localStorage.getItem('auth_token'));
  return token !== null && token.length > 0;
}

/**
 * Clear authentication state
 *
 * @param page - Playwright page object
 */
export async function clearAuth(page: Page): Promise<void> {
  await page.evaluate(() => localStorage.removeItem('auth_token'));
}

/**
 * Get the auth token from localStorage
 *
 * @param page - Playwright page object
 * @returns The JWT token or null if not authenticated
 */
export async function getAuthToken(page: Page): Promise<string | null> {
  return await page.evaluate(() => localStorage.getItem('auth_token'));
}

/**
 * Create a new project via the UI
 *
 * @param page - Playwright page object
 * @param name - Project name (defaults to unique timestamped name)
 * @param description - Project description
 * @returns Project ID extracted from URL
 */
export async function createTestProject(
  page: Page,
  name?: string,
  description = 'Test project created via E2E test'
): Promise<string> {
  // Generate unique project name if not provided
  const projectName = name || `test-project-${Date.now()}`;

  // Navigate to root page
  await page.goto('/');

  // The root page shows the ProjectCreationForm directly (no button to click)
  // Wait for form to be visible
  await page.getByTestId('project-name-input').waitFor({ state: 'visible' });

  // Fill project name and description
  await page.getByTestId('project-name-input').fill(projectName);
  await page.getByTestId('project-description-input').fill(description);

  // Submit form
  await page.getByTestId('create-project-submit').click();

  // Wait for redirect to project dashboard
  await page.waitForURL(/\/projects\/\d+/);

  // Extract project ID from URL
  const url = page.url();
  const match = url.match(/\/projects\/(\d+)/);
  if (!match) {
    throw new Error('Failed to extract project ID from URL');
  }

  return match[1];
}

/**
 * Answer a discovery question
 *
 * @param page - Playwright page object
 * @param answer - Answer text to submit
 */
export async function answerDiscoveryQuestion(
  page: Page,
  answer: string
): Promise<void> {
  // Wait for discovery answer input to be visible
  await page.getByTestId('discovery-answer-input').waitFor({ state: 'visible' });

  // Fill answer
  await page.getByTestId('discovery-answer-input').fill(answer);

  // Click submit button
  await page.getByTestId('submit-answer-button').click();

  // Wait for submission to complete by detecting state changes
  // Strategy: Wait for either button text to change back from "Submitting..."
  // or for input to change (next question) or disappear (discovery completed)
  try {
    // Wait for the button to show "Submitting..." first (confirms click registered)
    await page.getByTestId('submit-answer-button').getByText('Submitting...').waitFor({
      state: 'visible',
      timeout: 2000
    });

    // Then wait for it to return to "Submit Answer" (submission complete)
    await page.getByTestId('submit-answer-button').getByText('Submit Answer').waitFor({
      state: 'visible',
      timeout: 10000
    });
  } catch {
    // If button disappeared entirely, discovery is likely completed
    // This is a valid end state, so we continue
  }
}
