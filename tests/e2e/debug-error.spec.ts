/**
 * Debug test to capture browser console errors
 */

import { test } from '@playwright/test';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test('capture browser console errors', async ({ page }) => {
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
  console.log('\n=== Navigating to dashboard ===');
  await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);

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
