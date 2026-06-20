/**
 * Costs page feature coverage (issue #684, nightly suite).
 * Seeded: 3 token_usage rows (~$0.054 total) across claude-code / codex.
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe('Costs page', () => {
  test('shows seeded spend summary', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/costs');
    // Stable data-testids from the costs cards (#557).
    await expect(page.getByTestId('total-spend')).toBeVisible();
    await expect(page.getByTestId('total-tasks')).toBeVisible();
    // Seeded total is non-zero.
    await expect(page.getByTestId('total-spend')).toContainText(/\$0\.0[0-9]/);
    errors.assertClean();
  });

  test('time-range selector switches the range', async ({ page }) => {
    await gotoPage(page, '/costs');
    // Native <select data-testid="time-range-select"> (costs/page.tsx).
    const select = page.getByTestId('time-range-select');
    await expect(select).toBeVisible();
    await select.selectOption('7');
    await expect(select).toHaveValue('7');
  });
});
