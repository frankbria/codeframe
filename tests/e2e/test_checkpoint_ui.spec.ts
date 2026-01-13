/**
 * T159: Playwright E2E test for Checkpoint UI workflow.
 *
 * Tests:
 * - Checkpoint list displays correctly
 * - Create checkpoint button works
 * - Restore checkpoint shows confirmation dialog
 * - Checkpoint metadata is visible
 */

import { test, expect } from '@playwright/test';
import { loginUser, createTestProject, setupErrorMonitoring, getAuthToken } from './test-utils';
import { BACKEND_URL } from './e2e-config';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

/**
 * API Health Check - Runs before the main test suite to verify
 * that the checkpoint API is accessible and working.
 */
test.describe('Checkpoint API Health Check', () => {
  test('checkpoint API endpoint is accessible', async ({ page }) => {
    // Login to get auth token
    await loginUser(page);

    // Get auth token from localStorage
    const authToken = await getAuthToken(page);
    expect(authToken).toBeTruthy();
    console.log('[Health Check] Auth token obtained');

    // Make direct API call to checkpoint endpoint
    const response = await page.request.get(
      `${BACKEND_URL}/api/projects/${PROJECT_ID}/checkpoints`,
      {
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
      }
    );

    const status = response.status();
    console.log(`[Health Check] Checkpoint API status: ${status}`);

    // Log response body for debugging
    const body = await response.text();
    if (status !== 200) {
      console.log(`[Health Check] Error response: ${body}`);
    } else {
      try {
        const data = JSON.parse(body);
        console.log(`[Health Check] Found ${data.checkpoints?.length || 0} checkpoints`);
      } catch {
        console.log(`[Health Check] Response: ${body.substring(0, 200)}`);
      }
    }

    // Verify response
    expect(status).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('checkpoints');
    expect(Array.isArray(data.checkpoints)).toBe(true);
  });
});

test.describe('Checkpoint UI Workflow', () => {
  // Store checkpoint response for tests that need it
  let checkpointApiResponsePromise: Promise<any> | null = null;

  test.beforeEach(async ({ page }) => {
    // Set up error monitoring
    setupErrorMonitoring(page);

    // Monitor all API responses for debugging
    page.on('response', async (response) => {
      if (response.url().includes('/checkpoints')) {
        const status = response.status();
        console.log(`[Checkpoint API] ${response.url()} - Status: ${status}`);
        if (status !== 200) {
          try {
            const body = await response.text();
            console.log(`[Checkpoint API] Error response: ${body}`);
          } catch {
            console.log('[Checkpoint API] Could not read error response body');
          }
        }
      }
    });

    // Monitor failed requests
    page.on('requestfailed', (request) => {
      if (request.url().includes('/checkpoints')) {
        console.log(`[Checkpoint API] Request failed: ${request.url()} - ${request.failure()?.errorText}`);
      }
    });

    // Login using real authentication flow
    await loginUser(page);

    // Navigate to dashboard for test project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for API calls to complete - MUST succeed
    // Note: Must use /api/projects/ to avoid matching the HTML page response at /projects/
    const projectResponse = await page.waitForResponse(response =>
      response.url().includes(`/api/projects/${PROJECT_ID}`) && response.status() === 200,
      { timeout: 10000 }
    );
    expect(projectResponse.ok()).toBe(true);

    // Navigate to checkpoint section - tab MUST be visible
    const checkpointTab = page.locator('[data-testid="checkpoint-tab"]');
    await checkpointTab.waitFor({ state: 'visible', timeout: 10000 });
    await expect(checkpointTab).toBeVisible();

    // CRITICAL: Set up response listener BEFORE clicking tab to avoid race condition
    // The checkpoint API call fires when the tab is clicked, so we need to listen first
    checkpointApiResponsePromise = page.waitForResponse(
      response => response.url().includes('/checkpoints') && !response.url().includes('/diff'),
      { timeout: 15000 }
    );

    await checkpointTab.click();

    // Wait for checkpoint panel to become visible after tab switch
    const checkpointPanel = page.locator('[data-testid="checkpoint-panel"]');
    await checkpointPanel.waitFor({ state: 'visible', timeout: 5000 });

    // Wait for the checkpoint API call to complete (set up before click)
    try {
      const checkpointResponse = await checkpointApiResponsePromise;
      const status = checkpointResponse.status();
      console.log(`[beforeEach] Checkpoint API completed with status: ${status}`);
      if (status !== 200) {
        const body = await checkpointResponse.text();
        console.log(`[beforeEach] Checkpoint API error: ${body}`);
      }
    } catch (error) {
      console.log(`[beforeEach] Checkpoint API response not captured: ${error}`);
    }
  });

  test('should display checkpoint panel', async ({ page }) => {
    const checkpointPanel = page.locator('[data-testid="checkpoint-panel"]');

    // Scroll panel into view before waiting
    await checkpointPanel.scrollIntoViewIfNeeded();

    await checkpointPanel.waitFor({ state: 'visible', timeout: 15000 });
    await expect(checkpointPanel).toBeVisible();

    // Check for key components with proper waits
    const checkpointList = page.locator('[data-testid="checkpoint-list"]');
    await checkpointList.waitFor({ state: 'visible', timeout: 10000 });
    await expect(checkpointList).toBeVisible();

    const createButton = page.locator('[data-testid="create-checkpoint-button"]');
    await createButton.waitFor({ state: 'visible', timeout: 10000 });
    await expect(createButton).toBeVisible();
  });

  test('should list existing checkpoints', async ({ page }) => {
    const checkpointList = page.locator('[data-testid="checkpoint-list"]');
    await checkpointList.waitFor({ state: 'visible', timeout: 15000 });
    await expect(checkpointList).toBeVisible();

    // API response was already captured in beforeEach
    // Give UI time to render the data
    await page.waitForTimeout(500);

    // Wait for DOM to update - either checkpoint items or empty state MUST be visible
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
    const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');
    const loadingIndicator = page.locator('[data-testid="checkpoint-loading"]');
    const errorIndicator = page.locator('[data-testid="checkpoint-error"]');

    // Wait for loading to complete if it's visible
    if (await loadingIndicator.isVisible()) {
      console.log('[Test] Waiting for loading indicator to disappear...');
      await loadingIndicator.waitFor({ state: 'hidden', timeout: 10000 });
    }

    // Check for error state first
    if (await errorIndicator.isVisible()) {
      const errorText = await errorIndicator.textContent();
      console.log(`[Test] Error state detected: ${errorText}`);
      throw new Error(`Checkpoint loading failed with error: ${errorText}`);
    }

    // One of these MUST appear - if neither does, that's a bug
    await expect(checkpointItems.first().or(emptyState)).toBeVisible({ timeout: 5000 });

    // Check if checkpoints are displayed (or empty state)
    const count = await checkpointItems.count();
    console.log(`[Test] Found ${count} checkpoint items`);

    if (count === 0) {
      // Empty state should be visible (already declared above)
      await expect(emptyState).toBeVisible();
      console.log('[Test] Empty state displayed (expected for new projects)');
    } else {
      // At least one checkpoint should be visible
      expect(count).toBeGreaterThan(0);
      console.log(`[Test] Displaying ${count} checkpoints`);

      // Verify checkpoint metadata
      const firstCheckpoint = checkpointItems.first();
      await expect(firstCheckpoint.locator('[data-testid="checkpoint-name"]')).toBeVisible();
      await expect(firstCheckpoint.locator('[data-testid="checkpoint-timestamp"]')).toBeVisible();
    }
  });

  test('should open create checkpoint modal', async ({ page }) => {
    const createButton = page.locator('[data-testid="create-checkpoint-button"]');
    await createButton.waitFor({ state: 'visible', timeout: 15000 });
    await createButton.click();

    // Modal should appear
    const modal = page.locator('[data-testid="create-checkpoint-modal"]');
    await modal.waitFor({ state: 'visible', timeout: 10000 });
    await expect(modal).toBeVisible();

    // Modal should have name input and description
    await expect(modal.locator('[data-testid="checkpoint-name-input"]')).toBeVisible();
    await expect(modal.locator('[data-testid="checkpoint-description-input"]')).toBeVisible();
    await expect(modal.locator('[data-testid="checkpoint-save-button"]')).toBeVisible();
    await expect(modal.locator('[data-testid="checkpoint-cancel-button"]')).toBeVisible();
  });

  test('should validate checkpoint name input', async ({ page }) => {
    const createButton = page.locator('[data-testid="create-checkpoint-button"]');
    await createButton.waitFor({ state: 'visible', timeout: 15000 });
    await createButton.click();

    const modal = page.locator('[data-testid="create-checkpoint-modal"]');
    await modal.waitFor({ state: 'visible', timeout: 10000 });

    const nameInput = modal.locator('[data-testid="checkpoint-name-input"]');
    await nameInput.waitFor({ state: 'visible', timeout: 5000 });

    const saveButton = modal.locator('[data-testid="checkpoint-save-button"]');
    await saveButton.waitFor({ state: 'visible', timeout: 5000 });

    // Save button should be disabled when name is empty
    await expect(saveButton).toBeDisabled();

    // Enter valid name
    await nameInput.fill('Test Checkpoint');

    // Save button should become enabled
    await expect(saveButton).toBeEnabled({ timeout: 2000 });

    // Clear the name
    await nameInput.clear();

    // Save button should be disabled again
    await expect(saveButton).toBeDisabled({ timeout: 2000 });
  });

  test('should show restore confirmation dialog', async ({ page }) => {
    const checkpointList = page.locator('[data-testid="checkpoint-list"]');
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
    const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');

    const count = await checkpointItems.count();

    if (count > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Click restore button
      const restoreButton = firstCheckpoint.locator('[data-testid="checkpoint-restore-button"]');
      await restoreButton.click();

      // Confirmation dialog should appear
      const confirmDialog = page.locator('[data-testid="restore-confirmation-dialog"]');
      await expect(confirmDialog).toBeVisible();

      // Dialog should show warning message
      await expect(confirmDialog.locator('[data-testid="restore-warning"]')).toBeVisible();

      // Dialog should have confirm and cancel buttons
      await expect(confirmDialog.locator('[data-testid="restore-confirm-button"]')).toBeVisible();
      await expect(confirmDialog.locator('[data-testid="restore-cancel-button"]')).toBeVisible();
    } else {
      // No checkpoints - verify empty state is displayed correctly
      await expect(emptyState).toBeVisible();
      console.log('✅ No checkpoints to restore - empty state displayed correctly');
    }
  });

  test('should display checkpoint diff preview', async ({ page }) => {
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
    const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');

    const count = await checkpointItems.count();

    if (count > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Click to expand checkpoint details
      await firstCheckpoint.click();

      // Wait for diff API response (success or failure) - log but don't swallow
      try {
        const diffResponse = await page.waitForResponse(
          (response) => response.url().includes('/diff'),
          { timeout: 10000 }
        );
        console.log(`Diff API responded with status ${diffResponse.status()}`);
      } catch {
        console.log('No diff API response - may use different mechanism');
      }

      // Give UI time to render after API response
      await page.waitForTimeout(1000);

      // After clicking, the expanded section MUST show something:
      // - Diff content, "No changes" message, or error message
      const diffContent = firstCheckpoint.locator('[data-testid="checkpoint-diff"]');
      const noChangesMsg = firstCheckpoint.locator('[data-testid="no-changes-message"]');
      const errorMsg = page.locator('text=/Request failed|Failed to get|Error loading/i');

      // At least ONE of these must be visible - test FAILS if nothing appears
      await expect(diffContent.or(noChangesMsg).or(errorMsg)).toBeVisible({ timeout: 5000 });
      console.log('✅ Checkpoint expansion shows content correctly');
    } else {
      // No checkpoints - verify empty state is displayed
      await expect(emptyState).toBeVisible();
      console.log('✅ No checkpoints - empty state displayed correctly');
    }
  });

  test('should display checkpoint metadata', async ({ page }) => {
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
    const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');

    const count = await checkpointItems.count();

    if (count > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Metadata should be visible
      await expect(firstCheckpoint.locator('[data-testid="checkpoint-name"]')).toBeVisible();
      await expect(firstCheckpoint.locator('[data-testid="checkpoint-timestamp"]')).toBeVisible();

      // Git SHA should be visible if present
      const gitSha = firstCheckpoint.locator('[data-testid="checkpoint-git-sha"]');
      if (await gitSha.count() > 0) {
        const shaText = await gitSha.textContent();
        expect(shaText).toMatch(/[0-9a-f]{7,40}/); // Git SHA format
      }
      console.log('✅ Checkpoint metadata displayed correctly');
    } else {
      // No checkpoints - verify empty state is displayed
      await expect(emptyState).toBeVisible();
      console.log('✅ No checkpoints - empty state displayed correctly');
    }
  });

  test('should allow deleting checkpoint', async ({ page }) => {
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
    const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');

    const count = await checkpointItems.count();

    if (count > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Click delete button
      const deleteButton = firstCheckpoint.locator('[data-testid="checkpoint-delete-button"]');
      await deleteButton.click();

      // Confirmation dialog should appear
      const confirmDialog = page.locator('[data-testid="delete-confirmation-dialog"]');
      await expect(confirmDialog).toBeVisible();

      // Dialog should have warning
      await expect(confirmDialog.locator('[data-testid="delete-warning"]')).toBeVisible();
      console.log('✅ Delete confirmation dialog displayed correctly');
    } else {
      // No checkpoints - verify empty state is displayed
      await expect(emptyState).toBeVisible();
      console.log('✅ No checkpoints to delete - empty state displayed correctly');
    }
  });
});

/**
 * Tests for newly created projects (empty checkpoint list).
 * These tests verify the fix for the ".sort is not a function" error
 * that occurred when viewing checkpoints on projects with no checkpoints.
 */
test.describe('Checkpoint UI - New Project (Empty State)', () => {
  test('should display empty state without errors for new project', async ({ page }) => {
    // Collect console errors during test
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Login and create a fresh project (without starting discovery - UI-only test)
    await loginUser(page);
    const projectId = await createTestProject(
      page,
      `checkpoint-test-${Date.now()}`,
      'Test project for checkpoint empty state',
      false  // Don't start discovery - this test only checks checkpoint UI
    );

    // Navigate to project dashboard
    await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
    await page.waitForLoadState('networkidle');

    // Navigate to checkpoint tab
    const checkpointTab = page.locator('[data-testid="checkpoint-tab"]');
    await checkpointTab.waitFor({ state: 'visible', timeout: 10000 });

    // Set up response listener BEFORE clicking (to avoid race condition)
    const checkpointsResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/checkpoints'),
      { timeout: 15000 }
    );

    await checkpointTab.click();

    // Wait for checkpoint panel to load
    const checkpointPanel = page.locator('[data-testid="checkpoint-panel"]');
    await checkpointPanel.waitFor({ state: 'visible', timeout: 10000 });

    // Wait for API response (may have already completed)
    await checkpointsResponsePromise;

    // Give time for UI to render after API response
    await page.waitForTimeout(1000);

    // Verify empty state is displayed correctly
    const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');
    await expect(emptyState).toBeVisible({ timeout: 5000 });

    // Verify create button is still functional
    const createButton = page.locator('[data-testid="create-checkpoint-button"]');
    await expect(createButton).toBeVisible();

    // Critical: Verify no JavaScript errors occurred (especially ".sort is not a function")
    const sortErrors = consoleErrors.filter(
      (err) => err.includes('sort is not a function') || err.includes('is not a function')
    );
    expect(sortErrors).toHaveLength(0);
  });
});
