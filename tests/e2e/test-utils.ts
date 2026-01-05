/**
 * Test utilities for E2E tests
 *
 * This module provides:
 * - Error monitoring: Catch console errors, network failures, and failed requests
 * - API response validation: Verify responses return expected status and data
 * - WebSocket monitoring: Track connection health and message flow
 * - Authentication helpers: Login, register, and manage auth state
 * - Project utilities: Create and navigate projects
 */

import type { Page, WebSocket } from '@playwright/test';

// ============================================================================
// ERROR MONITORING
// ============================================================================

/**
 * Monitor for tracking errors during test execution
 */
export interface ErrorMonitor {
  /** Console errors captured */
  errors: string[];
  /** Console warnings captured */
  warnings: string[];
  /** Network-specific errors (net::ERR_*, Failed to fetch, etc.) */
  networkErrors: string[];
  /** Failed HTTP requests with URL and error details */
  failedRequests: Array<{ url: string; error: string }>;
}

/**
 * Set up comprehensive error monitoring on a page
 *
 * Captures:
 * - Console errors and warnings
 * - Network-specific errors (CORS, connection refused, etc.)
 * - Failed HTTP requests
 *
 * @param page - Playwright page object
 * @returns ErrorMonitor object to track errors throughout test
 *
 * @example
 * test.beforeEach(async ({ page }) => {
 *   const monitor = setupErrorMonitoring(page);
 *   (page as any).__errorMonitor = monitor;
 * });
 */
export function setupErrorMonitoring(page: Page): ErrorMonitor {
  const monitor: ErrorMonitor = {
    errors: [],
    warnings: [],
    networkErrors: [],
    failedRequests: []
  };

  // Monitor console errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text();
      monitor.errors.push(text);

      // Track network-specific errors for easier diagnosis
      if (
        text.includes('net::ERR_') ||
        text.includes('Failed to fetch') ||
        text.includes('WebSocket') ||
        text.includes('NetworkError') ||
        text.includes('CORS') ||
        text.includes('Connection refused')
      ) {
        monitor.networkErrors.push(text);
      }
    } else if (msg.type() === 'warning') {
      monitor.warnings.push(msg.text());
    }
  });

  // Monitor failed HTTP requests
  page.on('requestfailed', request => {
    const failure = request.failure();
    monitor.failedRequests.push({
      url: request.url(),
      error: failure?.errorText || 'Unknown error'
    });
  });

  return monitor;
}

/**
 * Assert no network errors occurred during test execution
 *
 * @param monitor - ErrorMonitor from setupErrorMonitoring
 * @param context - Optional test context for error messages
 * @throws Error if network errors or failed requests were captured
 *
 * @example
 * test.afterEach(async ({ page }) => {
 *   const monitor = (page as any).__errorMonitor;
 *   assertNoNetworkErrors(monitor, 'Dashboard test');
 * });
 */
export function assertNoNetworkErrors(monitor: ErrorMonitor, context?: string): void {
  const prefix = context ? `[${context}] ` : '';

  if (monitor.networkErrors.length > 0) {
    throw new Error(
      `${prefix}Network errors detected:\n${monitor.networkErrors.join('\n')}`
    );
  }

  if (monitor.failedRequests.length > 0) {
    const failures = monitor.failedRequests
      .map(f => `  - ${f.url}: ${f.error}`)
      .join('\n');
    throw new Error(
      `${prefix}Failed requests detected:\n${failures}`
    );
  }
}

// ============================================================================
// API RESPONSE VALIDATION
// ============================================================================

/**
 * Wait for an API response and validate its status and data
 *
 * Unlike `withOptionalWarning`, this function FAILS if the API doesn't respond
 * correctly, ensuring tests actually validate API functionality.
 *
 * @param page - Playwright page object
 * @param urlPattern - URL pattern to match (string or RegExp)
 * @param options - Validation options
 * @returns Response status and parsed JSON data
 * @throws Error if response doesn't match expectations
 *
 * @example
 * const response = await waitForAPIResponse(
 *   page,
 *   '/api/projects/1',
 *   { expectedStatus: 200, timeout: 10000 }
 * );
 * expect(response.data.id).toBeDefined();
 */
export async function waitForAPIResponse(
  page: Page,
  urlPattern: string | RegExp,
  options: { timeout?: number; expectedStatus?: number } = {}
): Promise<{ status: number; data: any }> {
  const timeout = options.timeout || 10000;
  const expectedStatus = options.expectedStatus || 200;

  const response = await page.waitForResponse(
    r => {
      const url = r.url();
      if (typeof urlPattern === 'string') {
        return url.includes(urlPattern);
      }
      return urlPattern.test(url);
    },
    { timeout }
  );

  const status = response.status();
  if (status !== expectedStatus) {
    throw new Error(
      `API response status ${status} does not match expected ${expectedStatus} for ${response.url()}`
    );
  }

  const data = await response.json().catch(() => null);
  if (data === null) {
    throw new Error(`API response has no valid JSON data for ${response.url()}`);
  }

  return { status, data };
}

// ============================================================================
// WEBSOCKET MONITORING
// ============================================================================

/**
 * Monitor for tracking WebSocket connection health
 */
export interface WebSocketMonitor {
  /** Whether the WebSocket successfully connected */
  connected: boolean;
  /** WebSocket close code (1000 = normal, 1008 = policy violation/auth error) */
  closeCode: number | null;
  /** WebSocket close reason message */
  closeReason: string | null;
  /** Messages received from the WebSocket */
  messages: string[];
  /** Errors encountered during WebSocket communication */
  errors: string[];
}

/**
 * Monitor WebSocket connection and messages
 *
 * @param page - Playwright page object
 * @param options - Monitoring options
 * @returns WebSocketMonitor with connection status and messages
 * @throws Error if WebSocket fails to connect or doesn't receive expected messages
 *
 * @example
 * const wsMonitor = await monitorWebSocket(page, {
 *   timeout: 15000,
 *   minMessages: 1
 * });
 * assertWebSocketHealthy(wsMonitor);
 */
export async function monitorWebSocket(
  page: Page,
  options: { timeout?: number; minMessages?: number; waitTime?: number } = {}
): Promise<WebSocketMonitor> {
  const timeout = options.timeout || 10000;
  const minMessages = options.minMessages || 1;
  const waitTime = options.waitTime || 3000;

  const monitor: WebSocketMonitor = {
    connected: false,
    closeCode: null,
    closeReason: null,
    messages: [],
    errors: []
  };

  try {
    const ws = await page.waitForEvent('websocket', { timeout });
    monitor.connected = true;

    // Listen for messages
    ws.on('framereceived', frame => {
      try {
        const payload = frame.payload.toString();
        if (payload) {
          monitor.messages.push(payload);
        }
      } catch (e) {
        monitor.errors.push(`Failed to parse frame: ${e}`);
      }
    });

    // Listen for close events
    ws.on('close', () => {
      // WebSocket closed - check if this was expected
      if (monitor.closeCode === null) {
        monitor.closeCode = 1000; // Assume normal close
      }
    });

    // Wait for messages to arrive
    await page.waitForTimeout(waitTime);

    // Verify we received expected messages
    if (monitor.messages.length < minMessages) {
      throw new Error(
        `Expected at least ${minMessages} WebSocket messages, got ${monitor.messages.length}`
      );
    }

    return monitor;
  } catch (error) {
    monitor.errors.push(`WebSocket connection failed: ${error}`);
    throw error;
  }
}

/**
 * Assert WebSocket connection is healthy
 *
 * @param monitor - WebSocketMonitor from monitorWebSocket
 * @throws Error if WebSocket had connection issues
 *
 * @example
 * const wsMonitor = await monitorWebSocket(page);
 * assertWebSocketHealthy(wsMonitor);
 */
export function assertWebSocketHealthy(monitor: WebSocketMonitor): void {
  if (!monitor.connected) {
    throw new Error('WebSocket never connected');
  }

  if (monitor.errors.length > 0) {
    throw new Error(`WebSocket errors: ${monitor.errors.join(', ')}`);
  }

  // Check for specific error close codes
  if (monitor.closeCode === 1008) {
    throw new Error('WebSocket closed with policy violation (code 1008) - likely auth error');
  }

  if (monitor.closeCode === 1003) {
    throw new Error('WebSocket closed with unsupported data error (code 1003)');
  }

  if (monitor.closeCode === 1006) {
    throw new Error('WebSocket closed abnormally (code 1006) - connection lost');
  }
}

// ============================================================================
// LEGACY HELPERS (Deprecated - use error monitoring instead)
// ============================================================================

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
 * The flow is: login -> project list page -> click "Create New Project" button ->
 * fill form -> submit -> navigate to dashboard
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

  // Navigate to root page (project list)
  await page.goto('/');

  // Click the "Create New Project" button to show the form
  await page.getByTestId('create-project-button').click();

  // Wait for form to be visible
  await page.getByTestId('project-name-input').waitFor({ state: 'visible' });

  // Fill project name and description
  await page.getByTestId('project-name-input').fill(projectName);
  await page.getByTestId('project-description-input').fill(description);

  // Submit form
  await page.getByTestId('create-project-submit').click();

  // Wait for redirect to project dashboard
  await page.waitForURL(/\/projects\/\d+/, { timeout: 10000 });

  // Extract project ID from URL
  const url = page.url();
  const match = url.match(/\/projects\/(\d+)/);
  if (!match) {
    throw new Error('Failed to extract project ID from URL');
  }

  return match[1];
}

/**
 * Navigate to an existing project from the project list
 *
 * @param page - Playwright page object
 * @param projectName - Name of the project to navigate to
 * @returns Project ID extracted from URL
 */
export async function navigateToProject(
  page: Page,
  projectName: string
): Promise<string> {
  // Navigate to root page (project list)
  await page.goto('/');

  // Wait for project list to load
  await page.getByTestId('project-list').waitFor({ state: 'visible', timeout: 5000 });

  // Find and click the project card
  const projectCard = page.locator(`text=${projectName}`).first();
  await projectCard.click();

  // Wait for navigation to project dashboard
  await page.waitForURL(/\/projects\/\d+/, { timeout: 5000 });

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
