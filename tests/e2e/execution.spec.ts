/**
 * Execution (Build) surface coverage (issue #964).
 *
 * There was no execution e2e at all, so nothing verified that the Build step
 * renders against a real API — CI green said nothing about it. The batch is
 * seeded terminal (one COMPLETED, one FAILED) because a live batch needs a
 * real agent run, which cannot be made deterministic here.
 *
 * Seeded by tests/e2e/seed_workspace.py: batch id `e2e-batch-0001`.
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

const BATCH_ID = 'e2e-batch-0001';

test.describe('@smoke Execution page — batch monitor', () => {
  test('renders the seeded batch with its progress', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, `/execution?batch=${BATCH_ID}`);

    // Header states the batch size and strategy.
    await expect(page.getByText(/batch execution \(2 tasks\)/i)).toBeVisible({
      timeout: 20000,
    });
    // One of the two tasks completed, so progress must say 1/2 — not 0/2,
    // which is what a monitor that ignored results would show.
    await expect(page.getByText(/1\/2 complete/i)).toBeVisible();
    await expect(page.getByText(/strategy: serial/i)).toBeVisible();

    errors.assertClean();
  });

  test('shows terminal-state UI rather than live controls', async ({ page }) => {
    await gotoPage(page, `/execution?batch=${BATCH_ID}`);
    await expect(page.getByText(/batch execution/i)).toBeVisible({ timeout: 20000 });

    // A finished batch offers a way out, not stop/cancel.
    await expect(page.getByRole('button', { name: /back to tasks/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /stop batch/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /cancel batch/i })).toHaveCount(0);
  });

  test('lists each task in the batch with its outcome', async ({ page }) => {
    await gotoPage(page, `/execution?batch=${BATCH_ID}`);
    await expect(page.getByText(/batch execution/i)).toBeVisible({ timeout: 20000 });

    // The seeded batch holds one of each terminal outcome.
    await expect(page.getByText('Completed', { exact: true })).toBeVisible();
    await expect(page.getByText('Failed', { exact: true })).toBeVisible();
  });

  test('expands a task row to explain its result', async ({ page }) => {
    await gotoPage(page, `/execution?batch=${BATCH_ID}`);
    await expect(page.getByText(/batch execution/i)).toBeVisible({ timeout: 20000 });

    // Rows are collapsed for a terminal batch (nothing is IN_PROGRESS).
    const rows = page.locator('button[aria-expanded]');
    await rows.first().click();

    await expect(
      page.getByText(/task completed successfully|check diagnostics for details/i)
    ).toBeVisible();
  });

  test('navigates back to the task board', async ({ page }) => {
    await gotoPage(page, `/execution?batch=${BATCH_ID}`);
    await expect(page.getByRole('button', { name: /back to tasks/i })).toBeVisible({
      timeout: 20000,
    });

    await page.getByRole('button', { name: /back to tasks/i }).click();
    await expect(page).toHaveURL(/\/tasks/);
  });
});
