/**
 * Blockers page feature coverage (issue #684, nightly suite).
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

const SEEDED_QUESTION = 'Which database should we use for the dashboard?';

test.describe('Blockers page', () => {
  test('lists the seeded open blocker', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/blockers');
    await expect(page.getByText(SEEDED_QUESTION).first()).toBeVisible();
    errors.assertClean();
  });

  test('blocker count badge appears in the sidebar', async ({ page }) => {
    await gotoPage(page, '/blockers');
    // The sidebar shows an open-blocker count badge (seeded: 1).
    const blockersNav = page.getByRole('link', { name: /blockers/i });
    await expect(blockersNav).toContainText(/1/);
  });
});
