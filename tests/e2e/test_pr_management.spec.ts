/**
 * E2E tests for Pull Request Management features (Tickets #284, #285)
 *
 * Tests the PR management components in the Dashboard:
 * - PRList showing pull requests with filtering
 * - PRCreationDialog for creating new PRs
 * - PRMergeDialog for merging PRs
 * - Real-time updates via WebSocket
 *
 * Note: PR creation/merge actions require GitHub integration (GITHUB_TOKEN).
 * Tests are designed to validate UI behavior even when GitHub is not configured.
 */

import { test, expect, Page } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrorsWithBrowserFilters,
  ExtendedPage,
} from './test-utils';
import { TEST_PROJECT_IDS, FRONTEND_URL, BACKEND_URL } from './e2e-config';

// Use ACTIVE project for PR management tests
const PROJECT_ID = TEST_PROJECT_IDS.ACTIVE;

test.describe('PR Management - Tab Navigation', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    // Setup error monitoring
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    // Login using real authentication flow
    await loginUser(page);

    // Navigate to project dashboard
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for dashboard to load
    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'PR Management test');
  });

  test('should display Pull Requests tab in dashboard @smoke', async () => {
    // Pull Requests tab should be visible in the dashboard
    const prTab = page.locator('[data-testid="pull-requests-tab"]');

    await prTab.waitFor({
      state: 'visible',
      timeout: 10000,
    });

    await expect(prTab).toBeVisible();
    console.log('Pull Requests tab is visible in dashboard');
  });

  test('should navigate to Pull Requests panel on tab click @smoke', async () => {
    // Click the Pull Requests tab
    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    // PR panel should become visible
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    await prPanel.waitFor({ state: 'visible', timeout: 10000 });
    await expect(prPanel).toBeVisible();

    // Tab should show as selected (aria-selected)
    const isSelected = await prTab.getAttribute('aria-selected');
    expect(isSelected).toBe('true');

    console.log('Successfully navigated to Pull Requests panel');
  });

  test('should display PR panel header with icon', async () => {
    // Navigate to PR tab
    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    await prPanel.waitFor({ state: 'visible', timeout: 10000 });

    // Panel should contain "Pull Requests" header text
    const panelText = await prPanel.textContent();
    expect(panelText).toContain('Pull Requests');
  });
});

test.describe('PR Management - PR List', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Navigate to PR tab
    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });

    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    await page.locator('[data-testid="pull-requests-panel"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'PR List test');
  });

  test('should display filter buttons for PR status', async () => {
    // Wait for the PR panel to be fully loaded
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');

    // Filter buttons should be visible (All, Open, Merged, Closed)
    // Use role=tablist to find the filter container
    const filterContainer = prPanel.locator('[role="tablist"]');

    // Wait for filters to appear
    await filterContainer.waitFor({ state: 'visible', timeout: 10000 });

    // Check for All filter button
    const allFilter = filterContainer.getByRole('tab', { name: 'All' });
    await expect(allFilter).toBeVisible();

    // Check for Open filter button
    const openFilter = filterContainer.getByRole('tab', { name: 'Open' });
    await expect(openFilter).toBeVisible();

    // Check for Merged filter button
    const mergedFilter = filterContainer.getByRole('tab', { name: 'Merged' });
    await expect(mergedFilter).toBeVisible();

    // Check for Closed filter button
    const closedFilter = filterContainer.getByRole('tab', { name: 'Closed' });
    await expect(closedFilter).toBeVisible();

    console.log('All PR status filter buttons are visible');
  });

  test('should filter PRs when filter button is clicked', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    const filterContainer = prPanel.locator('[role="tablist"]');
    await filterContainer.waitFor({ state: 'visible', timeout: 10000 });

    // Click Open filter
    const openFilter = filterContainer.getByRole('tab', { name: 'Open' });
    await openFilter.click();

    // Filter should become selected
    const isSelected = await openFilter.getAttribute('aria-selected');
    expect(isSelected).toBe('true');

    // The data-active attribute should also be true
    const isActive = await openFilter.getAttribute('data-active');
    expect(isActive).toBe('true');

    console.log('Filter successfully changed to "Open"');
  });

  test('should display Create PR button', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');

    // Find Create PR button
    const createButton = prPanel.locator('[data-testid="create-pr-button"]');
    await createButton.waitFor({ state: 'visible', timeout: 10000 });
    await expect(createButton).toBeVisible();

    console.log('Create PR button is visible');
  });

  test('should display empty state or PR cards @smoke', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');

    // Wait for loading to complete (check for loading skeleton disappearance)
    await page.waitForFunction(
      () => {
        // Loading state gone
        const loading = document.querySelector('[data-testid="pr-list-loading"]');
        if (loading) return false;

        // Either PR cards or empty state should be visible
        const cards = document.querySelectorAll('[data-testid="pr-card"]');
        const emptyText = document.body.textContent?.includes('No pull requests');
        return cards.length > 0 || emptyText;
      },
      { timeout: 15000 }
    );

    // Check which state we're in
    const prCards = page.locator('[data-testid="pr-card"]');
    const cardCount = await prCards.count();

    if (cardCount > 0) {
      console.log(`PR list displays ${cardCount} pull request(s)`);

      // Verify first card has expected elements
      const firstCard = prCards.first();
      const cardText = await firstCard.textContent();
      expect(cardText).toBeTruthy();
    } else {
      // Empty state should show "No pull requests" message
      const panelText = await prPanel.textContent();
      expect(panelText).toContain('No pull requests');
      console.log('PR list shows empty state');
    }
  });

  test('should display PR card with status badge when PRs exist', async () => {
    const prCards = page.locator('[data-testid="pr-card"]');

    // Wait for either PR cards or empty state
    await page.waitForFunction(
      () => {
        const loading = document.querySelector('[data-testid="pr-list-loading"]');
        return !loading;
      },
      { timeout: 10000 }
    );

    const cardCount = await prCards.count();

    if (cardCount > 0) {
      const firstCard = prCards.first();

      // Card should have a status attribute
      const status = await firstCard.getAttribute('data-status');
      expect(['open', 'merged', 'closed', 'draft']).toContain(status);

      console.log(`First PR card has status: ${status}`);
    } else {
      console.log('No PR cards to verify - empty state');
    }
  });
});

test.describe('PR Management - Create PR Dialog', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Navigate to PR tab
    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });

    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    await page.locator('[data-testid="pull-requests-panel"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'Create PR Dialog test');
  });

  test('should open Create PR dialog when button is clicked @smoke', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    const createButton = prPanel.locator('[data-testid="create-pr-button"]');

    await createButton.waitFor({ state: 'visible', timeout: 10000 });
    await createButton.click();

    // Dialog should open
    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 5000 });
    await expect(dialog).toBeVisible();

    // Dialog title should be "Create Pull Request"
    const dialogTitle = dialog.locator('text=Create Pull Request');
    await expect(dialogTitle).toBeVisible();

    console.log('Create PR dialog opened successfully');
  });

  test('should display form fields in Create PR dialog', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    const createButton = prPanel.locator('[data-testid="create-pr-button"]');

    await createButton.click();

    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 5000 });

    // Source Branch field
    const branchLabel = dialog.locator('text=Source Branch');
    await expect(branchLabel).toBeVisible();

    const branchInput = dialog.locator('#branch');
    await expect(branchInput).toBeVisible();

    // Target Branch field
    const targetLabel = dialog.locator('text=Target Branch');
    await expect(targetLabel).toBeVisible();

    // Title field
    const titleLabel = dialog.locator('text=Title');
    await expect(titleLabel).toBeVisible();

    const titleInput = dialog.locator('#title');
    await expect(titleInput).toBeVisible();

    // Description field
    const descLabel = dialog.locator('text=Description');
    await expect(descLabel).toBeVisible();

    console.log('All Create PR form fields are visible');
  });

  test('should show validation errors for empty required fields', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    const createButton = prPanel.locator('[data-testid="create-pr-button"]');

    await createButton.click();

    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 5000 });

    // Click Create without filling form
    const submitButton = dialog.getByRole('button', { name: 'Create' });
    await submitButton.click();

    // Validation errors should appear
    const branchError = dialog.locator('text=Branch is required');
    const titleError = dialog.locator('text=Title is required');

    // At least one validation error should appear
    const hasBranchError = await branchError.isVisible();
    const hasTitleError = await titleError.isVisible();

    expect(hasBranchError || hasTitleError).toBe(true);
    console.log('Form validation working correctly');
  });

  test('should close dialog when Cancel is clicked', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    const createButton = prPanel.locator('[data-testid="create-pr-button"]');

    await createButton.click();

    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 5000 });

    // Click Cancel
    const cancelButton = dialog.getByRole('button', { name: 'Cancel' });
    await cancelButton.click();

    // Dialog should close
    await expect(dialog).not.toBeVisible();
    console.log('Dialog closed successfully on Cancel');
  });

  test('should allow entering branch name and title', async () => {
    const prPanel = page.locator('[data-testid="pull-requests-panel"]');
    const createButton = prPanel.locator('[data-testid="create-pr-button"]');

    await createButton.click();

    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 5000 });

    // Fill in branch name
    const branchInput = dialog.locator('#branch');
    await branchInput.fill('feature/test-branch');
    await expect(branchInput).toHaveValue('feature/test-branch');

    // Fill in title
    const titleInput = dialog.locator('#title');
    await titleInput.fill('Test PR Title');
    await expect(titleInput).toHaveValue('Test PR Title');

    console.log('Form fields accept input correctly');
  });
});

test.describe('PR Management - PR Card Actions', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });

    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    await page.locator('[data-testid="pull-requests-panel"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'PR Card Actions test');
  });

  test('should display View button on PR cards', async () => {
    // Wait for loading to complete
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="pr-list-loading"]'),
      { timeout: 10000 }
    );

    const prCards = page.locator('[data-testid="pr-card"]');
    const cardCount = await prCards.count();

    if (cardCount > 0) {
      const firstCard = prCards.first();
      const viewButton = firstCard.getByRole('button', { name: 'View' });

      await expect(viewButton).toBeVisible();
      console.log('View button visible on PR card');
    } else {
      console.log('No PR cards to verify - skipping View button test');
    }
  });

  test('should display Merge button on open PR cards', async () => {
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="pr-list-loading"]'),
      { timeout: 10000 }
    );

    // Find open PR cards
    const openPrCards = page.locator('[data-testid="pr-card"][data-status="open"]');
    const openCount = await openPrCards.count();

    if (openCount > 0) {
      const firstOpenCard = openPrCards.first();
      const mergeButton = firstOpenCard.getByRole('button', { name: 'Merge' });

      await expect(mergeButton).toBeVisible();
      console.log('Merge button visible on open PR card');
    } else {
      console.log('No open PR cards - skipping Merge button test');
    }
  });

  test('should NOT display Merge button on merged/closed PR cards', async () => {
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="pr-list-loading"]'),
      { timeout: 10000 }
    );

    // Find merged PR cards
    const mergedPrCards = page.locator('[data-testid="pr-card"][data-status="merged"]');
    const mergedCount = await mergedPrCards.count();

    if (mergedCount > 0) {
      const firstMergedCard = mergedPrCards.first();
      const mergeButton = firstMergedCard.getByRole('button', { name: 'Merge' });

      // Merge button should NOT be visible on merged PRs
      await expect(mergeButton).not.toBeVisible();
      console.log('Merge button correctly hidden on merged PR');
    } else {
      console.log('No merged PR cards - skipping negative Merge button test');
    }
  });

  test('should display GitHub link when PR has URL', async () => {
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="pr-list-loading"]'),
      { timeout: 10000 }
    );

    const prCards = page.locator('[data-testid="pr-card"]');
    const cardCount = await prCards.count();

    if (cardCount > 0) {
      const firstCard = prCards.first();
      const githubLink = firstCard.locator('a[href*="github.com"]');

      const hasGitHubLink = await githubLink.isVisible();
      if (hasGitHubLink) {
        // Link should open in new tab
        const target = await githubLink.getAttribute('target');
        expect(target).toBe('_blank');

        // Should have aria-label for accessibility
        const ariaLabel = await githubLink.getAttribute('aria-label');
        expect(ariaLabel).toContain('GitHub');

        console.log('GitHub link is properly configured');
      } else {
        console.log('No GitHub link on this PR (pr_url may be null)');
      }
    }
  });
});

test.describe('PR Management - CI and Review Status Indicators', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });

    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    await page.locator('[data-testid="pull-requests-panel"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'PR Status Indicators test');
  });

  test('should display CI status indicator when available', async () => {
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="pr-list-loading"]'),
      { timeout: 10000 }
    );

    const ciStatusIndicators = page.locator('[data-testid="ci-status"]');
    const ciCount = await ciStatusIndicators.count();

    if (ciCount > 0) {
      const firstCi = ciStatusIndicators.first();
      const status = await firstCi.getAttribute('data-status');

      expect(['success', 'failure', 'pending', 'unknown']).toContain(status);
      console.log(`CI status indicator shows: ${status}`);
    } else {
      console.log('No CI status indicators visible (ci_status may be null)');
    }
  });

  test('should display review status indicator when available', async () => {
    await page.waitForFunction(
      () => !document.querySelector('[data-testid="pr-list-loading"]'),
      { timeout: 10000 }
    );

    const reviewStatusIndicators = page.locator('[data-testid="review-status"]');
    const reviewCount = await reviewStatusIndicators.count();

    if (reviewCount > 0) {
      const firstReview = reviewStatusIndicators.first();
      const status = await firstReview.getAttribute('data-status');

      expect(['approved', 'changes_requested', 'pending', 'dismissed']).toContain(status);
      console.log(`Review status indicator shows: ${status}`);
    } else {
      console.log('No review status indicators visible (review_status may be null)');
    }
  });
});

test.describe('PR Management - API Integration', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await loginUser(page);
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    await page.locator('[data-testid="dashboard-header"]').waitFor({
      state: 'visible',
      timeout: 15000,
    });
  });

  test.afterEach(async ({ page }) => {
    checkTestErrorsWithBrowserFilters(page, 'PR API Integration test');
  });

  test('should fetch PRs from API when tab is clicked', async () => {
    let prApiCalled = false;
    let prApiResponse: number | null = null;

    page.on('response', (response) => {
      if (response.url().includes('/prs') && response.request().method() === 'GET') {
        prApiCalled = true;
        prApiResponse = response.status();
      }
    });

    // Click PR tab to trigger API call
    const prTab = page.locator('[data-testid="pull-requests-tab"]');
    await prTab.waitFor({ state: 'visible', timeout: 10000 });
    await prTab.click();

    // Wait for panel to load
    await page.locator('[data-testid="pull-requests-panel"]').waitFor({
      state: 'visible',
      timeout: 10000,
    });

    // Give time for API call
    await page.waitForTimeout(2000);

    console.log(`PR API called: ${prApiCalled}, Response status: ${prApiResponse}`);

    // API should have been called
    expect(prApiCalled).toBe(true);

    // Response should be successful
    if (prApiResponse !== null) {
      expect(prApiResponse).toBe(200);
    }
  });
});
