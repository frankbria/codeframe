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

import type { Page, WebSocket, BrowserContext } from '@playwright/test';
import { BACKEND_URL } from './e2e-config';
import {
  BROWSER_TIMEOUTS,
  BROWSER_QUIRKS,
  BROWSER_EXPECTED_ERRORS,
  MOBILE_VIEWPORTS,
  type BrowserName,
  type ProjectName,
} from './browser-config';

// ============================================================================
// TYPE EXTENSIONS
// ============================================================================

/**
 * Extended Page interface with error monitoring support
 *
 * Usage: Cast page to ExtendedPage when accessing __errorMonitor
 * const monitor = (page as ExtendedPage).__errorMonitor;
 */
export interface ExtendedPage extends Page {
  __errorMonitor?: ErrorMonitor;
}

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
 *   const monitor = (page as ExtendedPage).__errorMonitor;
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

/**
 * Filter out expected errors from an ErrorMonitor
 *
 * Use this to exclude expected errors (e.g., auth failures in login tests)
 * before calling assertNoNetworkErrors.
 *
 * @param monitor - ErrorMonitor to filter
 * @param excludePatterns - Array of patterns to exclude (strings or RegExps)
 * @returns New ErrorMonitor with filtered errors
 *
 * @example
 * // In auth tests, filter out expected 401 errors
 * const filtered = filterExpectedErrors(monitor, ['401', '403', 'Invalid credentials']);
 * assertNoNetworkErrors(filtered, 'Auth test');
 */
export function filterExpectedErrors(
  monitor: ErrorMonitor,
  excludePatterns: (string | RegExp)[]
): ErrorMonitor {
  const matchesPattern = (text: string) =>
    excludePatterns.some(pattern =>
      typeof pattern === 'string'
        ? text.includes(pattern)
        : pattern.test(text)
    );

  return {
    errors: monitor.errors.filter(e => !matchesPattern(e)),
    warnings: monitor.warnings,
    networkErrors: monitor.networkErrors.filter(e => !matchesPattern(e)),
    failedRequests: monitor.failedRequests.filter(f => !matchesPattern(f.url) && !matchesPattern(f.error))
  };
}

/**
 * Standard afterEach handler for error monitoring
 *
 * Provides a consistent pattern for checking errors at the end of tests.
 * Use filterPatterns to exclude expected errors (e.g., auth failures in login tests).
 *
 * @param page - Playwright page object (cast to ExtendedPage internally)
 * @param context - Test context name for error messages
 * @param filterPatterns - Optional patterns to exclude from error checking
 *
 * @example
 * test.afterEach(async ({ page }) => {
 *   await checkTestErrors(page, 'Dashboard test');
 * });
 *
 * // With filtering for auth tests
 * test.afterEach(async ({ page }) => {
 *   await checkTestErrors(page, 'Auth test', ['401', '403']);
 * });
 */
export function checkTestErrors(
  page: Page,
  context: string,
  filterPatterns?: (string | RegExp)[]
): void {
  const extPage = page as ExtendedPage;
  const monitor = extPage.__errorMonitor;

  if (!monitor) {
    return; // No monitor set up, skip check
  }

  const filteredMonitor = filterPatterns
    ? filterExpectedErrors(monitor, filterPatterns)
    : monitor;

  // Only check if there are actual errors
  if (filteredMonitor.networkErrors.length > 0 || filteredMonitor.failedRequests.length > 0) {
    console.error(`🔴 [${context}] Network errors detected:`, {
      networkErrors: filteredMonitor.networkErrors,
      failedRequests: filteredMonitor.failedRequests
    });
    assertNoNetworkErrors(filteredMonitor, context);
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
 * Uses event-based waiting with polling instead of fixed timeouts to avoid
 * race conditions in CI environments.
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
  options: { timeout?: number; minMessages?: number; pollInterval?: number } = {}
): Promise<WebSocketMonitor> {
  const timeout = options.timeout || 10000;
  const minMessages = options.minMessages || 1;
  const pollInterval = options.pollInterval || 100;

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

    // Listen for close events - capture the WebSocket for close code extraction
    // Note: Playwright's WebSocket doesn't expose close code directly,
    // but we can detect abnormal closes via the 'close' event timing
    let wsClosed = false;
    ws.on('close', () => {
      wsClosed = true;
      // If closed before receiving expected messages, likely an error
      if (monitor.messages.length < minMessages && monitor.closeCode === null) {
        monitor.closeCode = 1006; // Abnormal closure
      }
    });

    // Event-based waiting: poll until we have enough messages or timeout
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
      // Check if we have enough messages
      if (monitor.messages.length >= minMessages) {
        return monitor;
      }

      // Check if WebSocket closed prematurely
      if (wsClosed) {
        break;
      }

      // Poll at interval
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    // Final check after timeout
    if (monitor.messages.length < minMessages) {
      throw new Error(
        `Expected at least ${minMessages} WebSocket messages, got ${monitor.messages.length}` +
        (wsClosed ? ' (WebSocket closed prematurely)' : ' (timeout)')
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
 * Create a new project via the UI and start discovery
 *
 * The flow is: login -> project list page -> click "Create New Project" button ->
 * fill form -> submit -> navigate to dashboard -> start discovery
 *
 * Note: Project creation and discovery start are separate operations:
 * - POST /api/projects creates the project record
 * - POST /api/projects/{id}/start initializes the LeadAgent and begins discovery
 *
 * @param page - Playwright page object
 * @param name - Project name (defaults to unique timestamped name)
 * @param description - Project description
 * @param startDiscovery - Whether to start discovery after creation (default: true)
 * @returns Project ID extracted from URL
 */
export async function createTestProject(
  page: Page,
  name?: string,
  description = 'Test project created via E2E test',
  startDiscovery = true
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

  const projectId = match[1];

  // Start discovery process if requested
  if (startDiscovery) {
    const authToken = await getAuthToken(page);
    if (!authToken) {
      throw new Error('No auth token available to start discovery');
    }

    // Call the start endpoint to initialize LeadAgent and begin discovery
    const startResponse = await page.request.post(
      `${BACKEND_URL}/api/projects/${projectId}/start`,
      {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!startResponse.ok()) {
      const errorText = await startResponse.text();
      throw new Error(`Failed to start discovery: ${startResponse.status()} - ${errorText}`);
    }

    // Wait for discovery to initialize (first question should appear)
    await page.waitForTimeout(2000);
  }

  return projectId;
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

// ============================================================================
// STATE VERIFICATION HELPERS (for returning user tests)
// ============================================================================

/**
 * Expected task state counts by status
 */
export interface ExpectedTaskState {
  inProgress?: number;
  completed?: number;
  pending?: number;
  blocked?: number;
  total?: number;
}

/**
 * Verify task state from API matches expected counts
 *
 * Use this to validate that API returns expected task data before checking UI.
 * This is critical for returning user tests where WebSocket is blocked.
 *
 * @param page - Playwright page object
 * @param projectId - Project ID to check
 * @param expected - Expected task counts by status
 * @throws Error if task counts don't match
 *
 * @example
 * await verifyTaskStateFromAPI(page, '3', {
 *   inProgress: 2,
 *   completed: 1,
 *   total: 5
 * });
 */
export async function verifyTaskStateFromAPI(
  page: Page,
  projectId: string,
  expected: ExpectedTaskState
): Promise<{ tasks: any[]; counts: Required<ExpectedTaskState> }> {
  // Get auth token
  const token = await getAuthToken(page);
  if (!token) {
    throw new Error('No auth token available');
  }

  // Fetch tasks from API
  const response = await page.request.get(`${BACKEND_URL}/api/projects/${projectId}/tasks`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok()) {
    throw new Error(`Failed to fetch tasks: ${response.status()}`);
  }

  const data = await response.json();
  const tasks = data.tasks || [];

  // Count tasks by status
  const counts = {
    inProgress: tasks.filter((t: { status: string }) => t.status === 'in_progress').length,
    completed: tasks.filter((t: { status: string }) => t.status === 'completed').length,
    pending: tasks.filter((t: { status: string }) => t.status === 'pending').length,
    blocked: tasks.filter((t: { status: string }) => t.status === 'blocked').length,
    total: tasks.length,
  };

  // Validate expected counts
  if (expected.inProgress !== undefined && counts.inProgress !== expected.inProgress) {
    throw new Error(`Expected ${expected.inProgress} in-progress tasks, got ${counts.inProgress}`);
  }
  if (expected.completed !== undefined && counts.completed !== expected.completed) {
    throw new Error(`Expected ${expected.completed} completed tasks, got ${counts.completed}`);
  }
  if (expected.pending !== undefined && counts.pending !== expected.pending) {
    throw new Error(`Expected ${expected.pending} pending tasks, got ${counts.pending}`);
  }
  if (expected.blocked !== undefined && counts.blocked !== expected.blocked) {
    throw new Error(`Expected ${expected.blocked} blocked tasks, got ${counts.blocked}`);
  }
  if (expected.total !== undefined && counts.total !== expected.total) {
    throw new Error(`Expected ${expected.total} total tasks, got ${counts.total}`);
  }

  return { tasks, counts };
}

/**
 * Verify project phase from API
 *
 * @param page - Playwright page object
 * @param projectId - Project ID to check
 * @param expectedPhase - Expected phase (discovery, planning, active, review, complete)
 * @throws Error if phase doesn't match
 */
export async function verifyProjectPhaseFromAPI(
  page: Page,
  projectId: string,
  expectedPhase: string
): Promise<{ project: any }> {
  const token = await getAuthToken(page);
  if (!token) {
    throw new Error('No auth token available');
  }

  const response = await page.request.get(`${BACKEND_URL}/api/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok()) {
    throw new Error(`Failed to fetch project: ${response.status()}`);
  }

  const project = await response.json();

  if (project.phase !== expectedPhase) {
    throw new Error(`Expected project phase '${expectedPhase}', got '${project.phase}'`);
  }

  return { project };
}

/**
 * Verify task state from DOM elements
 *
 * Checks the actual UI for task status indicators.
 * Use after page has loaded to verify UI matches expected state.
 *
 * @param page - Playwright page object
 * @param expected - Expected task counts by status
 * @returns Object with actual counts and whether validation passed
 */
export async function verifyTaskStateFromDOM(
  page: Page,
  expected: ExpectedTaskState
): Promise<{ actualCounts: ExpectedTaskState; passed: boolean; errors: string[] }> {
  const errors: string[] = [];

  // Look for task items with status indicators
  // Common patterns: data-status, data-task-status, status badge classes
  const inProgressLocator = page.locator('[data-status="in_progress"], [data-task-status="in_progress"]');
  const completedLocator = page.locator('[data-status="completed"], [data-task-status="completed"]');
  const pendingLocator = page.locator('[data-status="pending"], [data-task-status="pending"]');
  const blockedLocator = page.locator('[data-status="blocked"], [data-task-status="blocked"]');
  const allTasksLocator = page.locator('[data-testid="task-item"], [data-testid="task-card"]');

  const actualCounts: ExpectedTaskState = {
    inProgress: await inProgressLocator.count(),
    completed: await completedLocator.count(),
    pending: await pendingLocator.count(),
    blocked: await blockedLocator.count(),
    total: await allTasksLocator.count(),
  };

  // Validate expected counts
  if (expected.inProgress !== undefined && actualCounts.inProgress !== expected.inProgress) {
    errors.push(`Expected ${expected.inProgress} in-progress tasks in DOM, found ${actualCounts.inProgress}`);
  }
  if (expected.completed !== undefined && actualCounts.completed !== expected.completed) {
    errors.push(`Expected ${expected.completed} completed tasks in DOM, found ${actualCounts.completed}`);
  }
  if (expected.pending !== undefined && actualCounts.pending !== expected.pending) {
    errors.push(`Expected ${expected.pending} pending tasks in DOM, found ${actualCounts.pending}`);
  }
  if (expected.blocked !== undefined && actualCounts.blocked !== expected.blocked) {
    errors.push(`Expected ${expected.blocked} blocked tasks in DOM, found ${actualCounts.blocked}`);
  }
  if (expected.total !== undefined && actualCounts.total !== expected.total) {
    errors.push(`Expected ${expected.total} total tasks in DOM, found ${actualCounts.total}`);
  }

  return { actualCounts, passed: errors.length === 0, errors };
}

/**
 * Verify project completion state from UI
 *
 * Checks for completion indicators in the UI.
 *
 * @param page - Playwright page object
 * @returns Object with completion state details
 */
export async function verifyProjectCompletionFromDOM(
  page: Page
): Promise<{ isComplete: boolean; hasActiveWork: boolean; details: string }> {
  // Check for completion badge/status
  const statusBadge = page.locator('[data-testid="project-status"], [data-testid="phase-badge"]');
  let statusText = '';
  if (await statusBadge.first().isVisible()) {
    statusText = await statusBadge.first().textContent() || '';
  }

  const isComplete = /complete|done|finished/i.test(statusText);

  // Check for any in-progress or pending tasks
  const inProgressTasks = await page.locator('[data-status="in_progress"]').count();
  const pendingTasks = await page.locator('[data-status="pending"]').count();
  const hasActiveWork = inProgressTasks > 0 || pendingTasks > 0;

  return {
    isComplete,
    hasActiveWork,
    details: `Status: "${statusText}", In-progress: ${inProgressTasks}, Pending: ${pendingTasks}`,
  };
}

/**
 * Block WebSocket connections to simulate returning user scenario
 *
 * CRITICAL: Call this BEFORE navigating to the project page.
 * Returns a cleanup function to restore WebSocket connections.
 *
 * @param page - Playwright page object
 * @returns Cleanup function to unblock WebSocket
 *
 * @example
 * const unblock = await blockWebSocketConnections(page);
 * await page.goto('/projects/3');
 * // ... test assertions ...
 * await unblock();
 */
export async function blockWebSocketConnections(page: Page): Promise<() => Promise<void>> {
  // Block all WebSocket upgrade requests
  await page.route('**/ws**', async (route) => {
    await route.abort('connectionrefused');
  });

  await page.route('**/localhost**/ws**', async (route) => {
    await route.abort('connectionrefused');
  });

  return async () => {
    await page.unroute('**/ws**');
    await page.unroute('**/localhost**/ws**');
  };
}

// ============================================================================
// BROWSER DETECTION UTILITIES
// ============================================================================

/**
 * Extended Page interface with browser info for cross-browser testing
 */
export interface BrowserInfo {
  browserName: BrowserName;
  projectName: string;
  isMobile: boolean;
  isFirefox: boolean;
  isWebKit: boolean;
  isChromium: boolean;
}

/**
 * Get browser information from page context
 *
 * Uses the browser context to determine which browser is running.
 * This is more reliable than user agent parsing.
 *
 * @param page - Playwright page object
 * @returns BrowserInfo object with browser detection flags
 */
export function getBrowserInfo(page: Page): BrowserInfo {
  const context = page.context();
  const browser = context.browser();
  const browserType = browser?.browserType();
  const browserName = (browserType?.name() || 'chromium') as BrowserName;

  // Get project name from test info if available
  // This is set in playwright.config.ts for each project
  const projectName = (page as any)._browserContext?._options?.projectName || browserName;

  const isMobile =
    projectName.toLowerCase().includes('mobile') ||
    projectName.toLowerCase().includes('pixel') ||
    projectName.toLowerCase().includes('iphone') ||
    projectName.toLowerCase().includes('galaxy');

  return {
    browserName,
    projectName,
    isMobile,
    isFirefox: browserName === 'firefox',
    isWebKit: browserName === 'webkit',
    isChromium: browserName === 'chromium',
  };
}

/**
 * Check if current browser is Firefox
 */
export function isFirefox(page: Page): boolean {
  return getBrowserInfo(page).isFirefox;
}

/**
 * Check if current browser is WebKit (Safari)
 */
export function isWebKit(page: Page): boolean {
  return getBrowserInfo(page).isWebKit;
}

/**
 * Check if current browser is a mobile browser
 */
export function isMobileBrowser(page: Page): boolean {
  return getBrowserInfo(page).isMobile;
}

/**
 * Check if current browser is Chromium
 */
export function isChromium(page: Page): boolean {
  return getBrowserInfo(page).isChromium;
}

// ============================================================================
// BROWSER-SPECIFIC TIMEOUT UTILITIES
// ============================================================================

/**
 * Get the appropriate timeout for the current browser
 *
 * @param page - Playwright page object
 * @param baseTimeout - Base timeout in milliseconds
 * @param category - Timeout category (action, expect, navigation, etc.)
 * @returns Adjusted timeout for the current browser
 */
export function getBrowserTimeout(
  page: Page,
  baseTimeout: number,
  category: 'action' | 'expect' | 'navigation' | 'formValidation' | 'animation' = 'action'
): number {
  const { browserName, isMobile } = getBrowserInfo(page);

  // Get browser-specific multiplier
  const browserTimeouts = isMobile
    ? BROWSER_TIMEOUTS.mobile
    : BROWSER_TIMEOUTS[browserName] || BROWSER_TIMEOUTS.chromium;

  const chromiumBase = BROWSER_TIMEOUTS.chromium[category];
  const browserSpecific = browserTimeouts[category];

  // Calculate multiplier based on browser's specific timeout vs chromium baseline
  const multiplier = browserSpecific / chromiumBase;

  return Math.round(baseTimeout * multiplier);
}

/**
 * Get Firefox-specific timeout (1.5x base timeout)
 *
 * @param baseTimeout - Base timeout in milliseconds
 * @returns Timeout adjusted for Firefox, or original if not Firefox
 */
export function getFirefoxTimeout(page: Page, baseTimeout: number): number {
  if (isFirefox(page)) {
    return Math.round(baseTimeout * 1.5);
  }
  return baseTimeout;
}

/**
 * Get WebKit-specific timeout (1.4x base timeout)
 *
 * @param baseTimeout - Base timeout in milliseconds
 * @returns Timeout adjusted for WebKit, or original if not WebKit
 */
export function getWebKitTimeout(page: Page, baseTimeout: number): number {
  if (isWebKit(page)) {
    return Math.round(baseTimeout * 1.4);
  }
  return baseTimeout;
}

// ============================================================================
// MOBILE-SPECIFIC UTILITIES
// ============================================================================

/**
 * Wait for mobile viewport to stabilize
 *
 * Mobile browsers need time after page load for:
 * - Viewport stabilization
 * - Touch event registration
 * - Responsive layout transitions
 *
 * @param page - Playwright page object
 * @param timeout - Maximum wait time in milliseconds
 */
export async function waitForMobileReady(page: Page, timeout: number = 5000): Promise<void> {
  if (!isMobileBrowser(page)) {
    return;
  }

  // Wait for load state first
  await page.waitForLoadState('networkidle', { timeout });

  // Wait for viewport to stabilize (no resize events)
  await page.waitForTimeout(300);

  // Verify viewport is set correctly
  const viewport = page.viewportSize();
  if (!viewport) {
    throw new Error('Mobile viewport not set');
  }
}

/**
 * Get current mobile viewport dimensions
 *
 * @param page - Playwright page object
 * @returns Viewport dimensions or null if not mobile
 */
export function getMobileViewport(page: Page): { width: number; height: number } | null {
  if (!isMobileBrowser(page)) {
    return null;
  }

  const viewport = page.viewportSize();
  return viewport || null;
}

/**
 * Perform a mobile-friendly click using tap for touch devices
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 */
export async function mobileClick(page: Page, selector: string): Promise<void> {
  const element = page.locator(selector);

  if (isMobileBrowser(page)) {
    // Scroll into view first (mobile viewports are smaller)
    await element.scrollIntoViewIfNeeded();

    // Use tap for touch devices
    await element.tap();
  } else {
    await element.click();
  }
}

/**
 * Scroll element into view with mobile-specific handling
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 */
export async function scrollIntoViewMobile(page: Page, selector: string): Promise<void> {
  const element = page.locator(selector);

  await element.scrollIntoViewIfNeeded();

  // Mobile needs extra time for scroll animation
  if (isMobileBrowser(page)) {
    await page.waitForTimeout(200);
  }
}

/**
 * Wait for responsive layout to complete
 *
 * Useful after viewport changes or page load to ensure CSS media queries
 * have been applied.
 *
 * @param page - Playwright page object
 * @param timeout - Maximum wait time
 */
export async function waitForResponsiveLayout(page: Page, timeout: number = 3000): Promise<void> {
  const { isMobile, isFirefox } = getBrowserInfo(page);

  // Wait for any pending layout operations
  await page.waitForLoadState('domcontentloaded', { timeout });

  // Additional wait for mobile CSS transitions
  if (isMobile) {
    await page.waitForTimeout(300);
  }

  // Firefox needs extra time for CSS rendering
  if (isFirefox) {
    await page.waitForTimeout(200);
  }
}

// ============================================================================
// FIREFOX-SPECIFIC UTILITIES
// ============================================================================

/**
 * Wait for Firefox form validation to complete
 *
 * Firefox renders validation messages asynchronously, which can cause
 * tests to fail if we check for errors too quickly.
 *
 * @param page - Playwright page object
 * @param selector - Form or input selector
 * @param timeout - Maximum wait time
 */
export async function waitForFirefoxFormValidation(
  page: Page,
  selector: string,
  timeout: number = 5000
): Promise<void> {
  if (!isFirefox(page)) {
    return;
  }

  // Wait for any validation UI to render
  await page.waitForTimeout(BROWSER_TIMEOUTS.firefox.formValidation);

  // Wait for validation state to stabilize
  await page.locator(selector).waitFor({ state: 'visible', timeout });
}

/**
 * Wait for Firefox network idle with extended timeout
 *
 * Firefox's NS_BINDING_ABORTED errors during navigation mean we need
 * to wait longer for network to settle.
 *
 * @param page - Playwright page object
 * @param timeout - Maximum wait time
 */
export async function waitForFirefoxNetworkIdle(
  page: Page,
  timeout: number = 10000
): Promise<void> {
  if (isFirefox(page)) {
    await page.waitForLoadState('networkidle', {
      timeout: getFirefoxTimeout(page, timeout),
    });
  } else {
    await page.waitForLoadState('networkidle', { timeout });
  }
}

/**
 * Safe click for Firefox that waits for element stability
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 */
export async function firefoxSafeClick(page: Page, selector: string): Promise<void> {
  const element = page.locator(selector);

  if (isFirefox(page)) {
    // Wait for element to be stable (not animating)
    await element.waitFor({ state: 'visible' });
    await page.waitForTimeout(100); // Brief wait for CSS transitions
  }

  await element.click();
}

/**
 * Check if an error is a benign Firefox navigation error
 *
 * @param error - Error message string
 * @returns true if error is expected Firefox behavior
 */
export function isFirefoxNavigationError(error: string): boolean {
  return BROWSER_EXPECTED_ERRORS.firefox.some((pattern) => error.includes(pattern));
}

// ============================================================================
// WEBKIT-SPECIFIC UTILITIES
// ============================================================================

/**
 * Wait for WebKit element to stabilize
 *
 * WebKit (Safari) often needs extra time after an element appears
 * before it's fully interactive.
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 * @param timeout - Maximum wait time
 */
export async function waitForWebKitElementStable(
  page: Page,
  selector: string,
  timeout: number = 5000
): Promise<void> {
  const element = page.locator(selector);

  // Wait for element to be visible
  await element.waitFor({ state: 'visible', timeout: getWebKitTimeout(page, timeout) });

  if (isWebKit(page)) {
    // Additional wait for WebKit element stabilization
    await page.waitForTimeout(200);

    // Verify element is still visible (WebKit can have delayed removal)
    const isVisible = await element.isVisible();
    if (!isVisible) {
      await element.waitFor({ state: 'visible', timeout: 2000 });
    }
  }
}

/**
 * Wait for WebKit animation to complete
 *
 * WebKit CSS animations can interfere with interactions.
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 */
export async function waitForWebKitAnimation(page: Page, selector: string): Promise<void> {
  if (!isWebKit(page)) {
    return;
  }

  const element = page.locator(selector);

  // Wait for element to be visible
  await element.waitFor({ state: 'visible' });

  // Wait for CSS transitions/animations to complete
  await page.waitForTimeout(BROWSER_TIMEOUTS.webkit.animation);
}

/**
 * Safe form fill for WebKit
 *
 * WebKit requires clicking on the input before filling in some cases.
 *
 * @param page - Playwright page object
 * @param selector - Input selector
 * @param value - Value to fill
 */
export async function webkitSafeFormFill(
  page: Page,
  selector: string,
  value: string
): Promise<void> {
  const element = page.locator(selector);

  if (isWebKit(page)) {
    // Click first to ensure input is focused
    await element.click();
    await page.waitForTimeout(100);
  }

  await element.fill(value);
}

/**
 * Safe wait for selector in WebKit with retry
 *
 * WebKit sometimes needs multiple attempts to find elements due to
 * delayed rendering.
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 * @param options - Wait options
 */
export async function webkitSafeWaitForSelector(
  page: Page,
  selector: string,
  options: { timeout?: number; state?: 'visible' | 'attached' } = {}
): Promise<void> {
  const timeout = options.timeout || 5000;
  const state = options.state || 'visible';

  if (isWebKit(page)) {
    // Try with extended timeout and retry
    const maxRetries = 3;
    let lastError: Error | null = null;

    for (let i = 0; i < maxRetries; i++) {
      try {
        await page.locator(selector).waitFor({
          state,
          timeout: timeout / maxRetries,
        });
        return; // Success
      } catch (error) {
        lastError = error as Error;
        // Brief wait before retry
        await page.waitForTimeout(200);
      }
    }

    throw lastError || new Error(`Element ${selector} not found after ${maxRetries} retries`);
  } else {
    await page.locator(selector).waitFor({ state, timeout });
  }
}

/**
 * Wait for WebKit network idle with extended timeout
 *
 * Safari's network stack can be slower than Chromium.
 *
 * @param page - Playwright page object
 * @param timeout - Maximum wait time
 */
export async function waitForWebKitNetworkIdle(
  page: Page,
  timeout: number = 10000
): Promise<void> {
  await page.waitForLoadState('networkidle', {
    timeout: getWebKitTimeout(page, timeout),
  });
}

// ============================================================================
// CROSS-BROWSER HELPER UTILITIES
// ============================================================================

/**
 * Get reliable selector with fallback
 *
 * Tries data-testid first, then falls back to role-based selector.
 *
 * @param page - Playwright page object
 * @param testId - data-testid value
 * @param fallbackRole - ARIA role for fallback
 * @param fallbackName - Accessible name for role-based selector
 */
export function getReliableSelector(
  page: Page,
  testId: string,
  fallbackRole?: string,
  fallbackName?: string | RegExp
): ReturnType<typeof page.locator> {
  // Try data-testid first
  const testIdLocator = page.getByTestId(testId);

  if (fallbackRole && fallbackName) {
    // Return a locator that tries testid first, then role
    return page.locator(`[data-testid="${testId}"]`).or(
      page.getByRole(fallbackRole as any, { name: fallbackName })
    );
  }

  return testIdLocator;
}

/**
 * Wait for element to be stable (position and size not changing)
 *
 * Critical for WebKit where elements can appear before they're fully rendered.
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 * @param timeout - Maximum wait time
 */
export async function waitForElementStable(
  page: Page,
  selector: string,
  timeout: number = 5000
): Promise<void> {
  const element = page.locator(selector);
  const browser = getBrowserInfo(page);

  // Wait for visibility first
  await element.waitFor({
    state: 'visible',
    timeout: getBrowserTimeout(page, timeout, 'expect'),
  });

  // WebKit and mobile need additional stabilization
  if (browser.isWebKit || browser.isMobile) {
    await page.waitForTimeout(200);

    // Double-check visibility
    const isVisible = await element.isVisible();
    if (!isVisible) {
      await element.waitFor({ state: 'visible', timeout: 2000 });
    }
  }
}

/**
 * Safe getByTestId wrapper with browser-specific handling
 *
 * @param page - Playwright page object
 * @param testId - data-testid value
 * @param options - Options for handling
 */
export async function safeGetByTestId(
  page: Page,
  testId: string,
  options: { timeout?: number; scrollIntoView?: boolean } = {}
): Promise<ReturnType<typeof page.locator>> {
  const timeout = options.timeout || 5000;
  const locator = page.getByTestId(testId);

  // Wait for element with browser-specific timeout
  await locator.waitFor({
    state: 'visible',
    timeout: getBrowserTimeout(page, timeout, 'expect'),
  });

  // Scroll into view for mobile
  if (options.scrollIntoView || isMobileBrowser(page)) {
    await locator.scrollIntoViewIfNeeded();
  }

  // WebKit stability wait
  if (isWebKit(page)) {
    await page.waitForTimeout(100);
  }

  return locator;
}

/**
 * Wait for text content with browser-specific handling
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 * @param expectedText - Text to wait for (string or RegExp)
 * @param timeout - Maximum wait time
 */
export async function waitForTextContent(
  page: Page,
  selector: string,
  expectedText: string | RegExp,
  timeout: number = 5000
): Promise<void> {
  const adjustedTimeout = getBrowserTimeout(page, timeout, 'expect');

  await page.locator(selector).filter({
    hasText: expectedText,
  }).waitFor({ state: 'visible', timeout: adjustedTimeout });
}

/**
 * Enhanced checkTestErrors with automatic browser-specific error filtering
 *
 * Automatically includes browser-specific expected errors in the filter patterns.
 *
 * @param page - Playwright page object
 * @param context - Test context name
 * @param additionalPatterns - Additional patterns to filter
 */
export function checkTestErrorsWithBrowserFilters(
  page: Page,
  context: string,
  additionalPatterns: (string | RegExp)[] = []
): void {
  const browser = getBrowserInfo(page);

  // Combine all expected error patterns
  const allPatterns: (string | RegExp)[] = [
    ...BROWSER_EXPECTED_ERRORS.all,
    ...additionalPatterns,
  ];

  // Add browser-specific patterns
  if (browser.isFirefox) {
    allPatterns.push(...BROWSER_EXPECTED_ERRORS.firefox);
  }
  if (browser.isWebKit) {
    allPatterns.push(...BROWSER_EXPECTED_ERRORS.webkit);
  }
  if (browser.isMobile) {
    allPatterns.push(...BROWSER_EXPECTED_ERRORS.mobile);
  }

  // Use existing checkTestErrors with combined patterns
  checkTestErrors(page, context, allPatterns);
}

/**
 * Browser-aware click that handles mobile tap, Firefox stability, and WebKit delays
 *
 * @param page - Playwright page object
 * @param selector - Element selector
 */
export async function browserAwareClick(page: Page, selector: string): Promise<void> {
  const element = page.locator(selector);
  const browser = getBrowserInfo(page);

  // Scroll into view for mobile
  if (browser.isMobile) {
    await element.scrollIntoViewIfNeeded();
    await page.waitForTimeout(100);
    await element.tap();
    return;
  }

  // Firefox stability wait
  if (browser.isFirefox) {
    await element.waitFor({ state: 'visible' });
    await page.waitForTimeout(50);
  }

  // WebKit element stability wait
  if (browser.isWebKit) {
    await waitForWebKitElementStable(page, selector);
  }

  await element.click();
}

/**
 * Browser-aware form fill that handles WebKit click-then-fill pattern
 *
 * @param page - Playwright page object
 * @param selector - Input selector
 * @param value - Value to fill
 */
export async function browserAwareFormFill(
  page: Page,
  selector: string,
  value: string
): Promise<void> {
  const element = page.locator(selector);
  const browser = getBrowserInfo(page);

  // Scroll into view for mobile
  if (browser.isMobile) {
    await element.scrollIntoViewIfNeeded();
    await page.waitForTimeout(100);
  }

  // WebKit needs click before fill
  if (browser.isWebKit) {
    await element.click();
    await page.waitForTimeout(100);
  }

  await element.fill(value);
}

// ============================================================================
// RE-EXPORTS FOR CONVENIENCE
// ============================================================================

export {
  BROWSER_TIMEOUTS,
  BROWSER_QUIRKS,
  BROWSER_EXPECTED_ERRORS,
  MOBILE_VIEWPORTS,
  type BrowserName,
  type ProjectName,
};
