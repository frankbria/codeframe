/**
 * E2E Authentication Flow Tests
 *
 * Tests the unified BetterAuth authentication system, verifying:
 * - Login with valid/invalid credentials
 * - Logout functionality
 * - Session persistence across reloads and navigation
 * - Protected route access
 * - Redirect behavior for unauthenticated users
 * - BetterAuth API integration
 * - Database integration (plural table names)
 *
 * These tests validate that BetterAuth correctly uses CodeFRAME's
 * existing `users` and `sessions` tables with plural naming.
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

const TEST_USER_EMAIL = process.env.E2E_TEST_USER_EMAIL || 'test@example.com';
const TEST_USER_PASSWORD = process.env.E2E_TEST_USER_PASSWORD || 'testpassword123';

test.describe('Authentication Flow', () => {
  // Clear cookies before each test to ensure we start unauthenticated
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test.describe('Login Page', () => {
    test('should render login page with all form elements', async ({ page }) => {
      // Navigate to login page
      await page.goto('/login');

      // Assert login form elements are visible
      await expect(page.getByTestId('email-input')).toBeVisible();
      await expect(page.getByTestId('password-input')).toBeVisible();
      await expect(page.getByTestId('login-button')).toBeVisible();
    });
  });

  test.describe('Login Success', () => {
    test('should login successfully with valid credentials', async ({ page }) => {
      // Navigate to login page
      await page.goto('/login');

      // Fill in credentials
      await page.getByTestId('email-input').fill(TEST_USER_EMAIL);
      await page.getByTestId('password-input').fill(TEST_USER_PASSWORD);

      // Click login button
      await page.getByTestId('login-button').click();

      // Assert redirect to root or projects page
      await expect(page).toHaveURL(/^\/(projects)?$/, { timeout: 10000 });

      // Assert user menu is visible (logged in state)
      await expect(page.getByTestId('user-menu')).toBeVisible();

      // Verify session cookie was set by BetterAuth
      const cookies = await page.context().cookies();
      const sessionCookie = cookies.find(c => c.name === 'better-auth.session_token');
      expect(sessionCookie).toBeDefined();
      expect(sessionCookie?.value).toBeTruthy();
    });

    test('should use loginUser helper for quick authentication', async ({ page }) => {
      // Use helper function
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Verify we're authenticated
      await expect(page).toHaveURL(/^\/(projects)?$/);
      await expect(page.getByTestId('user-menu')).toBeVisible();
    });
  });

  test.describe('Login Failures', () => {
    test('should show error with invalid password', async ({ page }) => {
      // Navigate to login page
      await page.goto('/login');

      // Fill in valid email but wrong password
      await page.getByTestId('email-input').fill(TEST_USER_EMAIL);
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

    test('should show error with invalid email', async ({ page }) => {
      // Navigate to login page
      await page.goto('/login');

      // Fill in nonexistent email
      await page.getByTestId('email-input').fill('nonexistent@example.com');
      await page.getByTestId('password-input').fill(TEST_USER_PASSWORD);

      // Click login button
      await page.getByTestId('login-button').click();

      // Wait for error message
      await page.waitForSelector('[data-testid="auth-error"]', {
        state: 'visible',
        timeout: 5000
      });

      // Assert error is shown and we're still on login page
      await expect(page.getByTestId('auth-error')).toBeVisible();
      await expect(page).toHaveURL(/\/login/);
    });

    test('should handle empty form submission', async ({ page }) => {
      // Navigate to login page
      await page.goto('/login');

      // Click login button without filling fields
      await page.getByTestId('login-button').click();

      // Wait for validation
      await page.waitForTimeout(500);

      // Form should still be visible (not submitted)
      await expect(page.getByTestId('email-input')).toBeVisible();
      await expect(page.getByTestId('password-input')).toBeVisible();

      // Should still be on login page
      await expect(page).toHaveURL(/\/login/);
    });
  });

  test.describe('Logout', () => {
    test('should logout successfully', async ({ page }) => {
      // Login using helper function
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Assert we're logged in
      await expect(page.getByTestId('user-menu')).toBeVisible();

      // Click logout button
      await page.getByTestId('logout-button').click();

      // Assert redirect to login page
      await expect(page).toHaveURL(/\/login/);

      // Assert login form is visible (logged out state)
      await expect(page.getByTestId('email-input')).toBeVisible();

      // Verify session cookie was removed
      const cookies = await page.context().cookies();
      const sessionCookie = cookies.find(c => c.name === 'better-auth.session_token');
      expect(sessionCookie).toBeUndefined();
    });

    test('should not access protected routes after logout', async ({ page }) => {
      // Login first
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Logout
      await page.getByTestId('logout-button').click();
      await expect(page).toHaveURL(/\/login/);

      // Try to access protected route
      await page.goto('/projects/1');

      // Should redirect to login (if AUTH_REQUIRED=true)
      const authRequired = process.env.AUTH_REQUIRED?.toLowerCase() === 'true';
      if (authRequired) {
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
      }
    });
  });

  test.describe('Session Persistence', () => {
    test('should persist session across page reloads', async ({ page }) => {
      // Login
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Get session cookie before reload
      const cookiesBefore = await page.context().cookies();
      const sessionBefore = cookiesBefore.find(c => c.name === 'better-auth.session_token');
      expect(sessionBefore).toBeDefined();

      // Reload the page
      await page.reload();

      // Wait for page to load
      await page.waitForLoadState('networkidle');

      // Verify we're still authenticated (not redirected to login)
      expect(page.url()).not.toContain('/login');

      // Verify session cookie is still present
      const cookiesAfter = await page.context().cookies();
      const sessionAfter = cookiesAfter.find(c => c.name === 'better-auth.session_token');
      expect(sessionAfter).toBeDefined();
      expect(sessionAfter?.value).toBe(sessionBefore?.value);
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
      const cookies = await page.context().cookies();
      const sessionCookie = cookies.find(c => c.name === 'better-auth.session_token');
      expect(sessionCookie).toBeDefined();
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

    test('should redirect to login when accessing protected routes unauthenticated', async ({ page }) => {
      // Ensure we're not authenticated
      await page.context().clearCookies();

      // Try to access protected route
      await page.goto('/projects/1');

      // Should redirect to login (if AUTH_REQUIRED=true)
      const authRequired = process.env.AUTH_REQUIRED?.toLowerCase() === 'true';
      if (authRequired) {
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
      } else {
        console.log('⚠️  AUTH_REQUIRED=false: Skipping redirect test (migration mode)');
      }
    });
  });

  test.describe('BetterAuth API Integration', () => {
    test('should call BetterAuth sign-in API on login', async ({ page }) => {
      // Set up request monitoring
      const apiCalls: string[] = [];
      page.on('request', request => {
        if (request.url().includes('/api/auth/')) {
          apiCalls.push(request.url());
        }
      });

      // Navigate to login page
      await page.goto('/login');

      // Fill credentials and submit
      await page.getByTestId('email-input').fill(TEST_USER_EMAIL);
      await page.getByTestId('password-input').fill(TEST_USER_PASSWORD);
      await page.getByTestId('login-button').click();

      // Wait for redirect
      await expect(page).toHaveURL(/^\/(projects)?$/, { timeout: 10000 });

      // Verify BetterAuth sign-in API was called
      const signInCall = apiCalls.find(url => url.includes('/api/auth/sign-in'));
      expect(signInCall).toBeDefined();
    });
  });

  test.describe('Database Integration', () => {
    test('should create session in CodeFRAME sessions table', async ({ page, request }) => {
      // Login via UI
      await loginUser(page, TEST_USER_EMAIL, TEST_USER_PASSWORD);

      // Get session cookie
      const cookies = await page.context().cookies();
      const sessionCookie = cookies.find(c => c.name === 'better-auth.session_token');
      expect(sessionCookie).toBeDefined();

      // Verify backend can validate the session
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8080';
      const response = await request.get(`${backendUrl}/api/projects`, {
        headers: {
          Authorization: `Bearer ${sessionCookie?.value}`,
        },
      });

      // Backend should accept the session token (validates DB integration)
      expect(response.ok()).toBeTruthy();
    });
  });
});
