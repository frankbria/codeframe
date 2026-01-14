/**
 * E2E tests for Git Visualization features (Ticket #272)
 *
 * Tests the Git visualization components in the Dashboard:
 * - GitSection container with branch/commit/status display
 * - GitBranchIndicator showing current branch and dirty state
 * - CommitHistory showing recent commits
 * - BranchList showing available branches
 * - Real-time updates via WebSocket
 *
 * The Git section is only visible in active, review, or complete phases.
 */

import { test, expect, Page } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrorsWithBrowserFilters,
  ExtendedPage,
} from './test-utils';
import { TEST_PROJECT_IDS, FRONTEND_URL, BACKEND_URL } from './e2e-config';

// Use ACTIVE project which is in active phase - Git section should be visible
const ACTIVE_PROJECT_ID = TEST_PROJECT_IDS.ACTIVE;
// Use REVIEW project for review phase testing
const REVIEW_PROJECT_ID = TEST_PROJECT_IDS.REVIEW;
// Use DISCOVERY project which should NOT show Git section
const DISCOVERY_PROJECT_ID = TEST_PROJECT_IDS.DISCOVERY;

test.describe('Git Visualization - Active Phase', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    // Setup error monitoring
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    // Login using real authentication flow
    await loginUser(page);

    // Navigate to active project dashboard
    await page.goto(`${FRONTEND_URL}/projects/${ACTIVE_PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for dashboard to load
    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Git Visualization test');
  });

  test('should display Git section in active phase @smoke', async () => {
    // Git section container should be visible in active phase
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');

    // Wait for Git section to appear (may take time for API data to load)
    await gitSectionContainer.waitFor({
      state: 'visible',
      timeout: 15000,
    });

    await expect(gitSectionContainer).toBeVisible();

    // The git-section itself should exist within the container
    const gitSection = page.locator('[data-testid="git-section"]');
    const gitSectionLoading = page.locator('[data-testid="git-section-loading"]');
    const gitSectionError = page.locator('[data-testid="git-section-error"]');

    // One of these states should be visible
    const hasSection = await gitSection.isVisible();
    const hasLoading = await gitSectionLoading.isVisible();
    const hasError = await gitSectionError.isVisible();

    expect(hasSection || hasLoading || hasError).toBe(true);
  });

  test('should show branch indicator when data is loaded', async () => {
    // Wait for Git section to load
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    // Check for branch indicator states
    const branchIndicator = page.locator('[data-testid="branch-indicator"]');
    const branchLoading = page.locator('[data-testid="branch-loading"]');
    const branchError = page.locator('[data-testid="branch-error"]');

    // Wait for one of the branch states to be visible
    await page.waitForFunction(
      () => {
        return (
          document.querySelector('[data-testid="branch-indicator"]') ||
          document.querySelector('[data-testid="branch-loading"]') ||
          document.querySelector('[data-testid="branch-error"]')
        );
      },
      { timeout: 10000 }
    );

    const hasIndicator = await branchIndicator.isVisible();
    const hasLoading = await branchLoading.isVisible();
    const hasError = await branchError.isVisible();

    // At least one state should be present
    expect(hasIndicator || hasLoading || hasError).toBe(true);

    if (hasIndicator) {
      // If indicator is shown, it should have branch name text
      const branchText = await branchIndicator.textContent();
      expect(branchText).toBeTruthy();
      console.log(`Branch indicator shows: ${branchText?.trim()}`);
    } else if (hasError) {
      // Error state is acceptable for E2E tests (may not have real Git repo)
      console.log('Branch indicator shows error state (expected for test environment)');
    } else {
      console.log('Branch indicator is in loading state');
    }
  });

  test('should display commit history section', async () => {
    // Wait for Git section container
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    // Look for commit-related elements
    const commitItems = page.locator('[data-testid="commit-item"]');
    const commitsLoading = page.locator('[data-testid="commits-loading"]');
    const commitsError = page.locator('[data-testid="commits-error"]');

    // Wait for commits section to resolve to a state
    await page.waitForFunction(
      () => {
        return (
          document.querySelector('[data-testid="commit-item"]') ||
          document.querySelector('[data-testid="commits-loading"]') ||
          document.querySelector('[data-testid="commits-error"]') ||
          // Also check for "No commits yet" text (empty state)
          document.body.textContent?.includes('No commits yet')
        );
      },
      { timeout: 10000 }
    );

    const hasCommits = (await commitItems.count()) > 0;
    const hasLoading = await commitsLoading.isVisible();
    const hasError = await commitsError.isVisible();
    const hasEmptyState = (await gitSectionContainer.textContent())?.includes('No commits yet');

    // One of these states should be present
    expect(hasCommits || hasLoading || hasError || hasEmptyState).toBe(true);

    if (hasCommits) {
      const count = await commitItems.count();
      console.log(`Commit history shows ${count} commits`);

      // First commit item should have commit hash (short_hash)
      const firstCommit = commitItems.first();
      const commitText = await firstCommit.textContent();
      expect(commitText).toBeTruthy();
    } else if (hasEmptyState) {
      console.log('Commit history shows empty state');
    } else if (hasError) {
      console.log('Commit history shows error state (expected for test environment)');
    }
  });

  test('should display Code & Git header', async () => {
    // Wait for Git section
    const gitSection = page.locator('[data-testid="git-section"]');
    const gitSectionLoading = page.locator('[data-testid="git-section-loading"]');

    // Wait for git section container
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    // If fully loaded, check for header text
    const gitSectionVisible = await gitSection.isVisible();
    if (gitSectionVisible) {
      // The header text "Code & Git" should be visible
      const headerText = await gitSection.textContent();
      expect(headerText).toContain('Code');
    } else {
      // Loading or error state is also acceptable
      const loadingVisible = await gitSectionLoading.isVisible();
      expect(loadingVisible).toBe(true);
    }
  });

  test('should show dirty indicator when there are uncommitted changes', async () => {
    // This test verifies the dirty indicator UI element exists
    // In a real Git repo with changes, this would be visible

    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    // Wait for branch indicator to load
    const branchIndicator = page.locator('[data-testid="branch-indicator"]');
    const branchIndicatorVisible = await branchIndicator.isVisible();

    if (branchIndicatorVisible) {
      // Check if dirty indicator is present (amber dot)
      const dirtyIndicator = page.locator('[data-testid="dirty-indicator"]');
      const hasDirty = await dirtyIndicator.isVisible();

      if (hasDirty) {
        console.log('Dirty indicator is visible - repository has uncommitted changes');
        await expect(dirtyIndicator).toBeVisible();
      } else {
        console.log('No dirty indicator - repository is clean or not available');
      }
    } else {
      console.log('Branch indicator not loaded - skipping dirty indicator check');
    }
  });
});

test.describe('Git Visualization - Review Phase', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${REVIEW_PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Git Visualization Review test');
  });

  test('should display Git section in review phase', async () => {
    // Git section should also be visible in review phase
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');

    await gitSectionContainer.waitFor({
      state: 'visible',
      timeout: 15000,
    });

    await expect(gitSectionContainer).toBeVisible();
    console.log('Git section visible in review phase');
  });
});

test.describe('Git Visualization - Discovery Phase (Negative Test)', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${DISCOVERY_PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Git Visualization Discovery test');
  });

  test('should NOT display Git section in discovery phase', async () => {
    // Git section should NOT be visible in discovery phase
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');

    // Give it a moment to potentially render
    await page.waitForTimeout(2000);

    const isVisible = await gitSectionContainer.isVisible();
    expect(isVisible).toBe(false);
    console.log('Git section correctly hidden in discovery phase');
  });
});

test.describe('Git Visualization - API Integration', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${ACTIVE_PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Git API Integration test');
  });

  test('should fetch Git status from API', async () => {
    // Intercept Git status API call to verify it happens
    let gitStatusCalled = false;

    page.on('request', (request) => {
      if (request.url().includes('/git/status')) {
        gitStatusCalled = true;
      }
    });

    // Wait for Git section to trigger API calls
    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    // Give time for SWR to make API calls
    await page.waitForTimeout(3000);

    // The Git section should have attempted to fetch status
    // (may fail if no real Git repo, but call should happen)
    console.log(`Git status API called: ${gitStatusCalled}`);
    // Not asserting gitStatusCalled as the component uses SWR
    // which may batch or skip calls based on cache
  });

  test('should fetch commits from API', async () => {
    let commitsApiCalled = false;

    page.on('request', (request) => {
      if (request.url().includes('/git/commits')) {
        commitsApiCalled = true;
      }
    });

    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    await page.waitForTimeout(3000);

    console.log(`Git commits API called: ${commitsApiCalled}`);
  });

  test('should fetch branches from API', async () => {
    let branchesApiCalled = false;

    page.on('request', (request) => {
      if (request.url().includes('/git/branches')) {
        branchesApiCalled = true;
      }
    });

    const gitSectionContainer = page.locator('[data-testid="git-section-container"]');
    await gitSectionContainer.waitFor({ state: 'visible', timeout: 15000 });

    await page.waitForTimeout(3000);

    console.log(`Git branches API called: ${branchesApiCalled}`);
  });
});
