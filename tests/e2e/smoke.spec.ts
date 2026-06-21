/**
 * Smoke suite (issue #684) — runs on PRs (chromium, @smoke).
 *
 * Proves the current Phase-3+ UI boots, authenticates, and every page renders
 * against a seeded workspace with no uncaught console errors.
 */
import { test, expect } from '@playwright/test';
import { CORE_PAGES, gotoPage, trackConsoleErrors } from './helpers';
import { FRONTEND_URL, LS_AUTH_TOKEN, LS_WORKSPACE_PATH, TEST_USER } from './e2e-env';

test.describe('@smoke auth', () => {
  // Real login starts from a clean, unauthenticated browser.
  test.use({ storageState: { cookies: [], origins: [] } });

  test('logs in via /login and lands in the app', async ({ page }) => {
    // Seed only the workspace path so post-login pages have data; no token yet.
    await page.addInitScript(
      ([key, value]) => window.localStorage.setItem(key, value),
      [LS_WORKSPACE_PATH, process.env.E2E_WORKSPACE_DIR || ''],
    );

    await page.goto('/login');
    await page.locator('#email').fill(TEST_USER.email);
    await page.locator('#password').fill(TEST_USER.password);
    await page.getByRole('button', { name: /sign in/i }).click();

    // Redirected off /login and a JWT is now stored.
    await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 });
    const token = await page.evaluate((k) => window.localStorage.getItem(k), LS_AUTH_TOKEN);
    expect(token, 'auth_token should be set after login').toBeTruthy();
  });

  test('rejects bad credentials', async ({ page }) => {
    const wrongPw = 'wrong-' + 'password';
    await page.goto('/login');
    await page.locator('#email').fill(TEST_USER.email);
    await page.locator('#password').fill(wrongPw);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page.getByRole('alert')).toBeVisible({ timeout: 15000 });
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('@smoke pages render', () => {
  for (const { path, heading } of CORE_PAGES) {
    test(`renders ${path}`, async ({ page }) => {
      const errors = trackConsoleErrors(page);
      await gotoPage(page, path);
      await expect(page.getByText(heading).first()).toBeVisible({ timeout: 15000 });
      errors.assertClean();
    });
  }
});

test.describe('@smoke session', () => {
  test('storageState keeps the user authenticated', async ({ page }) => {
    await page.goto('/');
    const token = await page.evaluate((k) => window.localStorage.getItem(k), LS_AUTH_TOKEN);
    expect(token).toBeTruthy();
    // Never bounced to /login.
    await expect(page).not.toHaveURL(/\/login/);
    expect(FRONTEND_URL).toContain('http');
  });
});
