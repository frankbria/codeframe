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

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test.describe('Checkpoint UI Workflow', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to dashboard for test project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for API calls to complete
    await page.waitForResponse(response =>
      response.url().includes(`/projects/${PROJECT_ID}`) && response.status() === 200,
      { timeout: 10000 }
    ).catch(() => {});

    // Navigate to checkpoint section
    const checkpointTab = page.locator('[data-testid="checkpoint-tab"]');
    await checkpointTab.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
    if (await checkpointTab.isVisible()) {
      await checkpointTab.click();
      await page.waitForTimeout(500); // Wait for tab switch animation
    }
  });

  test('should display checkpoint panel', async ({ page }) => {
    const checkpointPanel = page.locator('[data-testid="checkpoint-panel"]');

    // Scroll panel into view before waiting
    await checkpointPanel.scrollIntoViewIfNeeded().catch(() => {});

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

    // Wait for checkpoints API response
    await page.waitForResponse(response =>
      response.url().includes('/checkpoints') && response.status() === 200,
      { timeout: 10000 }
    ).catch(() => {});

    // Wait for DOM to update
    await page.waitForTimeout(500);

    // Check if checkpoints are displayed (or empty state)
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
    const count = await checkpointItems.count();

    if (count === 0) {
      // Empty state should be visible
      const emptyState = page.locator('[data-testid="checkpoint-empty-state"]');
      await expect(emptyState).toBeVisible();
    } else {
      // At least one checkpoint should be visible
      expect(count).toBeGreaterThan(0);

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

    // Try to save without name
    await saveButton.click();

    // Validation error should appear (wait for React state update)
    const error = modal.locator('[data-testid="checkpoint-name-error"]');
    await expect(error).toBeVisible({ timeout: 2000 });

    // Enter valid name
    await nameInput.fill('Test Checkpoint');

    // Error should disappear (wait for React state update)
    await expect(error).not.toBeVisible({ timeout: 2000 });
  });

  test('should show restore confirmation dialog', async ({ page }) => {
    const checkpointList = page.locator('[data-testid="checkpoint-list"]');
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');

    if (await checkpointItems.count() > 0) {
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
    }
  });

  test('should display checkpoint diff preview', async ({ page }) => {
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');

    if (await checkpointItems.count() > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Click to expand checkpoint details
      await firstCheckpoint.click();

      // Diff preview should be visible
      const diffPreview = firstCheckpoint.locator('[data-testid="checkpoint-diff"]');

      // Diff might be async, wait a bit
      await page.waitForTimeout(1000);

      // Diff or "no changes" message should be visible
      const hasDiff = await diffPreview.count() > 0;
      const hasNoChanges = await firstCheckpoint.locator('[data-testid="no-changes-message"]').count() > 0;

      expect(hasDiff || hasNoChanges).toBe(true);
    }
  });

  test('should display checkpoint metadata', async ({ page }) => {
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');

    if (await checkpointItems.count() > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Metadata should be visible
      await expect(firstCheckpoint.locator('[data-testid="checkpoint-name"]')).toBeVisible();
      await expect(firstCheckpoint.locator('[data-testid="checkpoint-timestamp"]')).toBeVisible();

      // Git SHA should be visible
      const gitSha = firstCheckpoint.locator('[data-testid="checkpoint-git-sha"]');
      if (await gitSha.count() > 0) {
        const shaText = await gitSha.textContent();
        expect(shaText).toMatch(/[0-9a-f]{7,40}/); // Git SHA format
      }
    }
  });

  test('should allow deleting checkpoint', async ({ page }) => {
    const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');

    if (await checkpointItems.count() > 0) {
      const firstCheckpoint = checkpointItems.first();

      // Click delete button
      const deleteButton = firstCheckpoint.locator('[data-testid="checkpoint-delete-button"]');
      await deleteButton.click();

      // Confirmation dialog should appear
      const confirmDialog = page.locator('[data-testid="delete-confirmation-dialog"]');
      await expect(confirmDialog).toBeVisible();

      // Dialog should have warning
      await expect(confirmDialog.locator('[data-testid="delete-warning"]')).toBeVisible();
    }
  });
});
