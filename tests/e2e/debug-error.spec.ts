/**
 * Debug test to capture browser console errors
 *
 * NOTE: This test is excluded from CI runs (see playwright.config.ts testIgnore).
 * Use it locally to debug frontend issues:
 *   npx playwright test debug-error.spec.ts
 */

import { test } from '@playwright/test';
import { loginUser } from './test-utils';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';
// Use Project 2 for testing late-joining user scenarios (matches late-joining tests)
const PROJECT_ID = process.env.E2E_TEST_PROJECT_PLANNING_ID || '2';

test('capture browser console errors', async ({ page }) => {
  // Login first to access protected routes
  await loginUser(page);
  const consoleMessages: string[] = [];
  const errors: string[] = [];

  // Capture console messages
  page.on('console', msg => {
    const text = `[${msg.type()}] ${msg.text()}`;
    consoleMessages.push(text);
    console.log(text);
  });

  // Capture page errors
  page.on('pageerror', error => {
    const text = `[PAGE ERROR] ${error.toString()}\n${error.stack}`;
    errors.push(text);
    console.error(text);
  });

  // Navigate to dashboard
  const targetUrl = `${FRONTEND_URL}/projects/${PROJECT_ID}`;
  console.log(`\n=== Navigating to dashboard ===`);
  console.log(`Target URL: ${targetUrl}`);
  console.log(`PROJECT_ID: ${PROJECT_ID}`);
  await page.goto(targetUrl);
  console.log(`Current URL after navigation: ${page.url()}`);

  // Wait a bit to see what happens
  await page.waitForTimeout(5000);

  // Print summary
  console.log('\n=== CONSOLE MESSAGES ===');
  consoleMessages.forEach(msg => console.log(msg));

  console.log('\n=== PAGE ERRORS ===');
  errors.forEach(err => console.error(err));

  // Take screenshot
  await page.screenshot({ path: '/tmp/dashboard-debug.png', fullPage: true });
  console.log('\n=== Screenshot saved to /tmp/dashboard-debug.png ===');
});
