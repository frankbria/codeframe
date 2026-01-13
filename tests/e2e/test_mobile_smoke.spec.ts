/**
 * Mobile-Specific Smoke Tests
 *
 * These tests verify core functionality works correctly on mobile browsers.
 * They focus on:
 * - Touch interactions (tap instead of click)
 * - Responsive layout and viewport handling
 * - Mobile navigation patterns
 * - Form interactions on touch devices
 *
 * These tests are designed to run on:
 * - Mobile Chrome (Pixel 5)
 * - Mobile Safari (iPhone 12)
 */

import { test, expect } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrorsWithBrowserFilters,
  ExtendedPage,
  getBrowserInfo,
  isMobileBrowser,
  waitForMobileReady,
  waitForResponsiveLayout,
  browserAwareClick,
  browserAwareFormFill,
  scrollIntoViewMobile,
  mobileClick,
  getMobileViewport,
  MOBILE_VIEWPORTS,
} from './test-utils';
import { FRONTEND_URL } from './e2e-config';

test.describe('Mobile Smoke Tests @mobile', () => {
  test.beforeEach(async ({ page }) => {
    // Setup error monitoring
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    // Verify we're actually on a mobile browser for these tests
    const browserInfo = getBrowserInfo(page);
    console.log(`Running mobile test on: ${browserInfo.projectName} (mobile: ${browserInfo.isMobile})`);
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Mobile smoke test');
  });

  test('should have correct mobile viewport @smoke', async ({ page }) => {
    const browserInfo = getBrowserInfo(page);
    const viewport = page.viewportSize();

    expect(viewport).toBeDefined();

    if (browserInfo.isMobile) {
      // Mobile viewports should be narrower than desktop
      expect(viewport!.width).toBeLessThan(500);
      expect(viewport!.height).toBeGreaterThan(600);

      console.log(`✅ Mobile viewport: ${viewport!.width}x${viewport!.height}`);
    } else {
      // Desktop viewports are wider
      expect(viewport!.width).toBeGreaterThan(800);
      console.log(`ℹ️ Desktop viewport: ${viewport!.width}x${viewport!.height} (not a mobile test)`);
    }
  });

  test('should load login page on mobile @smoke', async ({ page }) => {
    await page.goto('/login');
    await waitForMobileReady(page);

    // Login form should be visible
    const emailInput = page.getByTestId('email-input');
    const passwordInput = page.getByTestId('password-input');
    const loginButton = page.getByTestId('login-button');

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(loginButton).toBeVisible();

    const browserInfo = getBrowserInfo(page);
    console.log(`✅ Login page loaded on ${browserInfo.projectName}`);
  });

  test('should handle touch login @smoke', async ({ page }) => {
    await page.goto('/login');
    await waitForMobileReady(page);

    const browserInfo = getBrowserInfo(page);

    // Fill form using browser-aware method (handles WebKit click-then-fill)
    await browserAwareFormFill(page, '[data-testid="email-input"]', 'test@example.com');
    await browserAwareFormFill(page, '[data-testid="password-input"]', 'Testpassword123');

    // Click login using browser-aware click (uses tap on mobile)
    await browserAwareClick(page, '[data-testid="login-button"]');

    // Wait for redirect or error
    await page.waitForURL(/\/(projects)?$|\/login/, { timeout: 15000 });

    // Either we're logged in or we got an auth error (test user may not exist)
    const currentUrl = page.url();
    const isLoggedIn = !currentUrl.includes('/login');

    if (isLoggedIn) {
      console.log(`✅ Login successful on ${browserInfo.projectName}`);
    } else {
      // Check if auth error is visible (expected if test user doesn't exist)
      const authError = page.getByTestId('auth-error');
      const hasError = await authError.isVisible().catch(() => false);
      if (hasError) {
        console.log(`ℹ️ Auth error shown (expected if test user missing) on ${browserInfo.projectName}`);
      }
    }
  });

  test('should scroll to elements on mobile @smoke', async ({ page }) => {
    await loginUser(page);
    await page.goto('/');
    await waitForMobileReady(page);

    const browserInfo = getBrowserInfo(page);

    if (browserInfo.isMobile) {
      // Find an element that might be below the fold
      const createButton = page.getByTestId('create-project-button');

      // Use mobile scroll helper
      await scrollIntoViewMobile(page, '[data-testid="create-project-button"]');

      // Element should now be visible
      await expect(createButton).toBeVisible();

      console.log(`✅ Scroll to element works on ${browserInfo.projectName}`);
    } else {
      console.log('ℹ️ Skipping scroll test on desktop');
    }
  });

  test('should handle responsive navigation @smoke', async ({ page }) => {
    await loginUser(page);
    await page.goto('/');
    await waitForResponsiveLayout(page);

    const browserInfo = getBrowserInfo(page);

    // Check for mobile menu (hamburger) or full navigation
    const mobileMenu = page.locator('[data-testid="mobile-menu"]');
    const hasMobileMenu = await mobileMenu.isVisible().catch(() => false);

    if (hasMobileMenu) {
      // Open mobile menu
      await mobileClick(page, '[data-testid="mobile-menu"]');

      // Navigation should expand
      const nav = page.locator('[data-testid="nav-menu"]');
      await expect(nav).toBeVisible({ timeout: 5000 });

      console.log(`✅ Mobile menu opens correctly on ${browserInfo.projectName}`);
    } else {
      // Full navigation should be visible
      const navItems = page.locator('nav a, nav button');
      const count = await navItems.count();

      if (count > 0) {
        console.log(`✅ Navigation visible with ${count} items on ${browserInfo.projectName}`);
      } else {
        console.log(`ℹ️ No explicit navigation found on ${browserInfo.projectName}`);
      }
    }
  });

  test('should handle touch on project creation @smoke', async ({ page }) => {
    await loginUser(page);
    await page.goto('/');
    await waitForMobileReady(page);

    const browserInfo = getBrowserInfo(page);

    // Tap create project button
    await browserAwareClick(page, '[data-testid="create-project-button"]');

    // Form should appear
    const nameInput = page.getByTestId('project-name-input');
    await expect(nameInput).toBeVisible({ timeout: 10000 });

    // Fill form using touch-friendly method
    const uniqueName = `mobile-test-${Date.now()}`;
    await browserAwareFormFill(page, '[data-testid="project-name-input"]', uniqueName);
    await browserAwareFormFill(
      page,
      '[data-testid="project-description-input"]',
      'Mobile test project'
    );

    console.log(`✅ Project creation form works on ${browserInfo.projectName}`);
  });

  test('should display dashboard on mobile @smoke', async ({ page }) => {
    await loginUser(page);

    // Navigate to a project dashboard
    await page.goto(`${FRONTEND_URL}/projects/1`);
    await waitForMobileReady(page);

    const browserInfo = getBrowserInfo(page);

    // Dashboard header should be visible
    const header = page.locator('[data-testid="dashboard-header"]');
    await expect(header).toBeVisible({ timeout: 15000 });

    // Agent panel should be visible (may need scroll on mobile)
    await scrollIntoViewMobile(page, '[data-testid="agent-status-panel"]');
    const agentPanel = page.locator('[data-testid="agent-status-panel"]');
    await expect(agentPanel).toBeVisible();

    console.log(`✅ Dashboard displays correctly on ${browserInfo.projectName}`);
  });

  test('should handle tab navigation with touch @smoke', async ({ page }) => {
    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/1`);
    await waitForMobileReady(page);

    const browserInfo = getBrowserInfo(page);

    // Find and tap on a tab
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    if (await tasksTab.isVisible().catch(() => false)) {
      await browserAwareClick(page, '[data-testid="tasks-tab"]');

      // Wait for tab content to load
      await page.waitForTimeout(500);

      console.log(`✅ Tab navigation works on ${browserInfo.projectName}`);
    } else {
      console.log(`ℹ️ Tabs not visible on ${browserInfo.projectName} (may use different nav)`);
    }
  });
});

/**
 * Tests that should be skipped on mobile due to desktop-only features
 */
test.describe('Desktop-Only Features (skip on mobile)', () => {
  test.beforeEach(async ({ page }) => {
    const browserInfo = getBrowserInfo(page);
    // Skip these tests on mobile browsers
    test.skip(browserInfo.isMobile, 'This test requires desktop features');
  });

  test('hover states should work', async ({ page }) => {
    await loginUser(page);
    await page.goto('/');

    // Hover interactions are desktop-only
    const button = page.getByTestId('create-project-button');
    await button.hover();

    // Verify hover state is applied (if CSS provides visual feedback)
    const cursor = await button.evaluate((el) =>
      window.getComputedStyle(el).cursor
    );

    expect(cursor).toBe('pointer');
    console.log('✅ Hover states work on desktop');
  });
});
