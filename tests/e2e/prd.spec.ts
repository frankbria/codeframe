/**
 * PRD page feature coverage (issue #684, nightly suite).
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe('PRD page', () => {
  test('renders the seeded PRD content', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/prd');
    await expect(page.getByText(/E2E Demo PRD/i).first()).toBeVisible();
    await expect(page.locator('body')).toContainText(/metrics dashboard/i);
    errors.assertClean();
  });

  test('exposes the Stress Test action', async ({ page }) => {
    await gotoPage(page, '/prd');
    const stressTest = page.getByRole('button', { name: /stress test/i });
    await expect(stressTest.first()).toBeVisible();
  });
});
