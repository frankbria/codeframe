/**
 * Review page feature coverage (issue #684, nightly suite).
 * Seeded: workspace is a git repo with an uncommitted change to app.py.
 *
 * SERIAL, and it has to be (#964). The commit test consumes that seeded
 * working-tree change, so every test asserting on the diff must run before it.
 * The config sets `fullyParallel: true` and `retries: 2`, so relying on
 * declaration order alone was not enough: a retry of the commit test would
 * re-run against an already-committed repo and could never pass. `.serial`
 * makes the dependency enforced rather than commented, and skips the rest of
 * the file on a failure instead of reporting cascading phantom failures.
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe.serial('Review page', () => {
  test('renders the working-tree diff for the seeded change', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/review');
    // The seeded change touches app.py.
    await expect(page.getByText(/app\.py/).first()).toBeVisible({ timeout: 20000 });
    errors.assertClean();
  });

  test('exposes review actions', async ({ page }) => {
    await gotoPage(page, '/review');
    // At least one of the review actions is present.
    const actions = page.getByRole('button', { name: /run gates|export patch|commit|create pr/i });
    await expect(actions.first()).toBeVisible();
  });

  // ── Commit flow (issue #964) ──────────────────────────────────────────────
  // Previously this file only asserted that one action button was visible, so
  // nothing exercised the Ship step end to end against a real API.
  //
  // ORDER MATTERS — see the .serial note in the file header: the commit test
  // consumes the seeded working-tree change, so it runs last.

  test('exports the working-tree patch', async ({ page }) => {
    await gotoPage(page, '/review');
    const exportBtn = page.getByRole('button', { name: /export patch/i });
    await expect(exportBtn).toBeVisible({ timeout: 20000 });
    await exportBtn.click();

    // The modal shows the patch itself, not just a spinner.
    await expect(page.getByText(/export patch/i).last()).toBeVisible();
    await expect(page.getByRole('textbox')).toContainText(/diff --git|app\.py/, {
      timeout: 20000,
    });
  });

  test('refuses to commit without a message', async ({ page }) => {
    await gotoPage(page, '/review');
    await expect(page.getByLabel(/commit message/i)).toBeVisible({ timeout: 20000 });

    await page.getByLabel(/commit message/i).fill('');
    await expect(page.getByRole('button', { name: /^commit$/i })).toBeDisabled();
  });

  test('commits the seeded working-tree change', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/review');

    // The seeded repo has one uncommitted file.
    await expect(page.getByText(/app\.py/).first()).toBeVisible({ timeout: 20000 });

    const message = page.getByLabel(/commit message/i);
    await expect(message).toBeVisible();
    await message.fill('test: commit from the e2e review flow');

    const commit = page.getByRole('button', { name: /^commit$/i });
    await expect(commit).toBeEnabled();
    await commit.click();

    // Outcome evidence: the page reports the new commit's short hash. A
    // "committed N files: <hash>" banner only appears after gitApi.commit
    // resolves, so this fails if the wiring is broken.
    await expect(page.getByText(/committed \d+ files?: [0-9a-f]{7}/i)).toBeVisible({
      timeout: 30000,
    });

    // And the diff empties, because the change is now committed.
    await expect(page.getByText(/no changed files|no changes/i).first()).toBeVisible({
      timeout: 20000,
    });

    errors.assertClean();
  });
});
