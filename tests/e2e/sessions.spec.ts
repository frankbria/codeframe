/**
 * Sessions + Execution page feature coverage (issue #684, nightly suite).
 *
 * These pages are workspace-scoped views over agent activity. With no live
 * agent run seeded, they render their list/empty state cleanly — which is the
 * contract we assert (page is wired up, no crash).
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe('Sessions page', () => {
  test('renders the sessions view', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/sessions');
    await expect(page.getByText(/session/i).first()).toBeVisible();
    errors.assertClean();
  });
});

test.describe('Execution page', () => {
  test('renders the execution/batch view', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/execution');
    await expect(page.getByText(/execution|batch|ready/i).first()).toBeVisible();
    errors.assertClean();
  });
});
