/**
 * Temporary authentication bypass for E2E tests.
 *
 * TEMPORARY SOLUTION: This file bypasses the login UI by setting session cookies directly.
 *
 * WHY: Frontend uses BetterAuth (separate schema) while backend uses CodeFRAME auth.
 * E2E tests seed users into CodeFRAME's `users` table, but BetterAuth expects its own `user` table.
 * This mismatch prevents the login UI from working in tests.
 *
 * TRACKING: GitHub issue #158 - Align BetterAuth with CodeFRAME authentication system
 *
 * MIGRATION: Once auth is aligned, replace calls to setTestUserSession() with loginUser()
 * from test-utils.ts. The loginUser() helper is already written and will work once auth is fixed.
 *
 * DELETE THIS FILE after auth alignment is complete.
 */

import { Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Set test user session cookie to bypass login UI.
 *
 * This function reads the session token created by global-setup.ts (via seed-test-data.py)
 * and sets it as a cookie. This allows tests to skip the login page and go directly to
 * authenticated pages.
 *
 * @param page - Playwright page object
 *
 * @example
 * test.beforeEach(async ({ page }) => {
 *   await setTestUserSession(page);
 *   // Now authenticated as test@example.com, can navigate to protected pages
 * });
 */
export async function setTestUserSession(page: Page): Promise<void> {
  // Read session token from file created by seed-test-data.py
  const tokenFile = path.join(__dirname, '.codeframe', 'test-session-token.txt');

  if (!fs.existsSync(tokenFile)) {
    throw new Error(
      `Session token file not found: ${tokenFile}\n` +
      `Ensure global-setup.ts has run successfully and seeded the database.`
    );
  }

  const sessionToken = fs.readFileSync(tokenFile, 'utf-8').trim();

  if (!sessionToken) {
    throw new Error('Session token file is empty');
  }

  // Set CodeFRAME session cookie
  // Note: This bypasses BetterAuth entirely and uses CodeFRAME's backend auth
  await page.context().addCookies([{
    name: 'session_token',
    value: sessionToken,
    domain: 'localhost',
    path: '/',
    httpOnly: true,
    secure: false, // localhost uses HTTP
    sameSite: 'Lax',
    expires: Math.floor(Date.now() / 1000) + 86400 * 7 // 7 days from now
  }]);

  // For debugging: log that we've set the session
  if (process.env.DEBUG_TESTS) {
    console.log(`[Auth Bypass] Set session cookie: ${sessionToken.substring(0, 20)}...`);
    console.log(`[Auth Bypass] Authenticated as: test@example.com`);
  }
}

/**
 * Get test user credentials.
 *
 * Returns the credentials for the test user created by seed-test-data.py.
 * These credentials are currently only used for reference, as we bypass login with cookies.
 *
 * Once auth is aligned (GitHub issue #158), these credentials will be used with
 * the loginUser() helper from test-utils.ts.
 */
export function getTestUserCredentials() {
  return {
    email: 'test@example.com',
    password: 'testpassword123',
  };
}
