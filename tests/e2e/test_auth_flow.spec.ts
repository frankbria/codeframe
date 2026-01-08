/**
 * E2E Authentication Flow Tests
 *
 * Tests the JWT authentication system using FastAPI Users, verifying:
 * - Registration with valid credentials
 * - Login with valid/invalid credentials
 * - Logout functionality
 * - Session persistence via localStorage JWT token
 * - Protected route access
 * - Redirect behavior for unauthenticated users
 */

import { test, expect } from '@playwright/test';
import {
  loginUser,
  registerUser,
  isAuthenticated,
  clearAuth,
  getAuthToken,
  setupErrorMonitoring,
  checkTestErrors,
  ExtendedPage
} from './test-utils';

const TEST_USER_EMAIL = process.env.E2E_TEST_USER_EMAIL || 'test@example.com';
const TEST_USER_PASSWORD = process.env.E2E_TEST_USER_PASSWORD || 'Testpassword123';

// CI-aware timeout: longer in CI environments to account for slower execution
const AUTH_ERROR_TIMEOUT = process.env.CI ? 10000 : 5000;

test.describe('Authentication Flow', () => {
  // Clear localStorage before each test to ensure we start unauthenticated
  test.beforeEach(async ({ page }) => {
    // Setup error monitoring
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    // Navigate to any page to access localStorage
    await page.goto('/login');
    await clearAuth(page);
  });

  // Verify no critical network errors occurred during each test
  // Filter out expected errors during auth testing:
  // Auth tests intentionally trigger auth errors - only filter EXPECTED auth failures
  // WebSocket and network errors should NOT be filtered - they indicate real problems
  test.afterEach(async ({ page }) => {
    checkTestErrors(page, 'Auth flow test', [
      // Auth-related errors that are EXPECTED in auth tests (testing invalid credentials)
      '401', '403',
      'Invalid credentials', 'LOGIN_BAD_CREDENTIALS',
      'Unauthorized', 'Forbidden',
      // Navigation cancellation is normal browser behavior
      'net::ERR_ABORTED',
      // Next.js RSC payload fetch during navigation - transient, non-blocking
      'Failed to fetch RSC payload'
    ]);
  });

  test.describe('Registration', () => {
    test('user can register and auto-login', async ({ page }) => {
      // Generate unique email for this test
      const uniqueEmail = `test-${Date.now()}@example.com`;
      const password = 'SecurePassword123';
      const name = 'Test User';

      // Navigate to signup page
      await page.goto('/signup');

      // Fill registration form
      await page.getByTestId('name-input').fill(name);
      await page.getByTestId('email-input').fill(uniqueEmail);
      await page.getByTestId('password-input').fill(password);
      await page.getByTestId('confirm-password-input').fill(password);

      // Submit form
      await page.getByTestId('signup-button').click();

      // Should redirect to home after auto-login (URL includes full host)
      await expect(page).toHaveURL(/\/(projects)?$/, { timeout: 10000 });

      // Verify user is logged in (user menu visible)
      await expect(page.getByTestId('user-menu')).toBeVisible();

      // Verify JWT token was stored
      const authenticated = await isAuthenticated(page);
      expect(authenticated).toBe(true);
    });

    test('should show error for weak password', async ({ page }) => {
      await page.goto('/signup');

      // Fill form with weak password
      await page.getByTestId('name-input').fill('Test User');
      await page.getByTestId('email-input').fill('weak@example.com');
      await page.getByTestId('password-input').fill('weak');
      await page.getByTestId('confirm-password-input').fill('weak');

      // Submit form
      await page.getByTestId('signup-button').click();

      // Should show validation error
      await expect(page.getByTestId('auth-error')).toBeVisible({ timeout: AUTH_ERROR_TIMEOUT });
      await expect(page.getByTestId('auth-error')).toContainText(/password/i);

      // Should still be on signup page
      await expect(page).toHaveURL(/\/signup/);
    });

    test('should show error for mismatched passwords', async ({ page }) => {
      await page.goto('/signup');

      // Fill form with mismatched passwords
      await page.getByTestId('name-input').fill('Test User');
      await page.getByTestId('email-input').fill('mismatch@example.com');
      await page.getByTestId('password-input').fill('SecurePassword123');
      await page.getByTestId('confirm-password-input').fill('DifferentPassword123');

      // Submit form
      await page.getByTestId('signup-button').click();

      // Should show error
      await expect(page.getByTestId('auth-error')).toBeVisible({ timeout: AUTH_ERROR_TIMEOUT });
      await expect(page.getByTestId('auth-error')).toContainText(/match/i);
    });
  });

  test.describe('Login Page', () => {
    test('should render login page with all form elements', async ({ page }) => {
      await page.goto('/login');

      // Assert login form elements are visible
      await expect(page.getByTestId('email-input')).toBeVisible();
      await expect(page.getByTestId('password-input')).toBeVisible();
      await expect(page.getByTestId('login-button')).toBeVisible();
    });
  });

  test.describe('Login Success', () => {
    test('should login successfully with valid credentials @smoke', async ({ page }) => {
      await page.goto('/login');

      // Fill in credentials
      await page.getByTestId('email-input').fill(TEST_USER_EMAIL);
      await page.getByTestId('password-input').fill(TEST_USER_PASSWORD);

      // Click login button
      await page.getByTestId('login-button').click();

      // Assert redirect to root or projects page (URL includes full host)
      await expect(page).toHaveURL(/\/(projects)?$/, { timeout: 10000 });

      // Assert user menu is visible (logged in state)
      await expect(page.getByTestId('user-menu')).toBeVisible();

      // Verify JWT token was stored in localStorage
      const token = await getAuthToken(page);
      expect(token).toBeTruthy();
      expect(token?.length).toBeGreaterThan(0);
    });

    test('should use loginUser helper for quick authentication', async ({ page }) => {
      // Use helper function
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Verify we're authenticated (URL includes full host)
      await expect(page).toHaveURL(/\/(projects)?$/);
      await expect(page.getByTestId('user-menu')).toBeVisible();
    });
  });

  test.describe('Login Failures', () => {
    test('should show error with invalid password', async ({ page }) => {
      await page.goto('/login');

      // Fill in valid email but wrong password
      await page.getByTestId('email-input').fill(TEST_USER_EMAIL);
      await page.getByTestId('password-input').fill('WrongPassword123');

      // Click login button
      await page.getByTestId('login-button').click();

      // Wait for error message to appear
      await page.waitForSelector('[data-testid="auth-error"]', {
        state: 'visible',
        timeout: AUTH_ERROR_TIMEOUT
      });

      // Assert error message is shown
      const errorElement = page.getByTestId('auth-error');
      await expect(errorElement).toBeVisible();
      await expect(errorElement).toContainText(/invalid|failed|credentials/i);

      // Assert still on login page
      await expect(page).toHaveURL(/\/login/);
    });

    test('should show error with invalid email', async ({ page }) => {
      await page.goto('/login');

      // Fill in nonexistent email
      await page.getByTestId('email-input').fill('nonexistent@example.com');
      await page.getByTestId('password-input').fill(TEST_USER_PASSWORD);

      // Click login button
      await page.getByTestId('login-button').click();

      // Wait for error message
      await page.waitForSelector('[data-testid="auth-error"]', {
        state: 'visible',
        timeout: AUTH_ERROR_TIMEOUT
      });

      // Assert error is shown and we're still on login page
      await expect(page.getByTestId('auth-error')).toBeVisible();
      await expect(page).toHaveURL(/\/login/);
    });

    test('should handle empty form submission', async ({ page }) => {
      await page.goto('/login');

      // Click login button without filling fields
      await page.getByTestId('login-button').click();

      // Wait for validation
      await page.waitForTimeout(500);

      // Form should still be visible (not submitted due to HTML5 validation)
      await expect(page.getByTestId('email-input')).toBeVisible();
      await expect(page.getByTestId('password-input')).toBeVisible();

      // Should still be on login page
      await expect(page).toHaveURL(/\/login/);
    });
  });

  test.describe('Logout', () => {
    test('should logout successfully', async ({ page }) => {
      // Login first
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Assert we're logged in
      await expect(page.getByTestId('user-menu')).toBeVisible();

      // Verify token exists before logout
      const tokenBefore = await getAuthToken(page);
      expect(tokenBefore).toBeTruthy();

      // Click logout button
      await page.getByTestId('logout-button').click();

      // Assert redirect to login page
      await expect(page).toHaveURL(/\/login/);

      // Assert login form is visible (logged out state)
      await expect(page.getByTestId('email-input')).toBeVisible();

      // Verify token was removed from localStorage
      const tokenAfter = await getAuthToken(page);
      expect(tokenAfter).toBeNull();
    });

    test('should not access protected routes after logout', async ({ page }) => {
      // Login first
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Logout
      await page.getByTestId('logout-button').click();
      await expect(page).toHaveURL(/\/login/);

      // Try to access protected route
      await page.goto('/projects/1');

      // Should redirect to login - authentication is always required
      await expect(page).toHaveURL(/\/login/, { timeout: AUTH_ERROR_TIMEOUT });
    });
  });

  test.describe('Session Persistence', () => {
    test('should persist session across page reloads', async ({ page }) => {
      // Login
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Get token before reload
      const tokenBefore = await getAuthToken(page);
      expect(tokenBefore).toBeTruthy();

      // Reload the page
      await page.reload();

      // Wait for page to load
      await page.waitForLoadState('networkidle');

      // Verify we're still authenticated (not redirected to login)
      expect(page.url()).not.toContain('/login');

      // Verify token is still present
      const tokenAfter = await getAuthToken(page);
      expect(tokenAfter).toBeTruthy();
      expect(tokenAfter).toBe(tokenBefore);
    });

    test('should persist session across navigation', async ({ page }) => {
      // Login
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Navigate to different pages
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      expect(page.url()).not.toContain('/login');

      // Navigate to another page
      await page.goto('/projects/1').catch(() => {
        // Page might not exist, that's OK
      });

      // Verify we're still authenticated
      const authenticated = await isAuthenticated(page);
      expect(authenticated).toBe(true);
    });
  });

  test.describe('Protected Routes', () => {
    test('should access protected routes when authenticated', async ({ page }) => {
      // Login
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Navigate to protected route
      await page.goto('/projects/1');

      // Should successfully load (not redirect to login)
      await page.waitForLoadState('networkidle');
      expect(page.url()).toContain('/projects/1');
      expect(page.url()).not.toContain('/login');
    });

    test('protected route redirects to login when unauthenticated', async ({ page }) => {
      // Ensure we're not authenticated
      await page.goto('/login');
      await clearAuth(page);

      // Try to access protected route
      await page.goto('/projects/1');

      // Should redirect to login - authentication is always required
      await expect(page).toHaveURL(/\/login/, { timeout: AUTH_ERROR_TIMEOUT });
    });
  });

  test.describe('API Integration', () => {
    test('should call FastAPI auth endpoint on login', async ({ page }) => {
      // Set up request monitoring
      const apiCalls: string[] = [];
      page.on('request', request => {
        if (request.url().includes('/auth/')) {
          apiCalls.push(request.url());
        }
      });

      await page.goto('/login');

      // Fill credentials and submit
      await page.getByTestId('email-input').fill(TEST_USER_EMAIL);
      await page.getByTestId('password-input').fill(TEST_USER_PASSWORD);
      await page.getByTestId('login-button').click();

      // Wait for redirect (URL includes full host)
      await expect(page).toHaveURL(/\/(projects)?$/, { timeout: 10000 });

      // Verify FastAPI auth endpoint was called
      const loginCall = apiCalls.find(url => url.includes('/auth/jwt/login'));
      expect(loginCall).toBeDefined();
    });

    test('should include JWT token in API requests after login', async ({ page, request }) => {
      // Login via UI
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Get the JWT token
      const token = await getAuthToken(page);
      expect(token).toBeTruthy();

      // Verify backend accepts the token
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8080';
      const response = await request.get(`${backendUrl}/users/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      // Backend should accept the JWT token
      expect(response.ok()).toBeTruthy();

      const userData = await response.json();
      expect(userData.email).toBe(TEST_USER_EMAIL);
    });
  });
});
