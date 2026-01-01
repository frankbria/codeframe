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
 * @param page - Playwright page object
 * @param email - User email (defaults to test user)
 * @param password - User password (defaults to test password)
 */
export async function loginUser(
  page: Page,
  email = 'test@example.com',
  password = 'testpassword123'
): Promise<void> {
  // Navigate to login page
  await page.goto('/login');

  // Fill in credentials using data-testid selectors
  await page.getByTestId('email-input').fill(email);
  await page.getByTestId('password-input').fill(password);

  // Click login button
  await page.getByTestId('login-button').click();

  // Wait for redirect to root page or projects page
  await page.waitForURL(/^\/(projects)?$/);
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

  // Click create project button
  await page.getByTestId('create-project-button').click();

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

  // Wait for either next question or completion (with timeout)
  await page.waitForTimeout(2000);
}
