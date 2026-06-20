/**
 * Review page feature coverage (issue #684, nightly suite).
 * Seeded: workspace is a git repo with an uncommitted change to app.py.
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe('Review page', () => {
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
});
