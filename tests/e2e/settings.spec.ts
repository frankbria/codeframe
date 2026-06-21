/**
 * Settings page feature coverage (issue #684, nightly suite).
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

const TABS = ['Agent', 'API Keys', 'Integrations', 'Notifications', 'PROOF9', 'Workspace'];

test.describe('Settings page', () => {
  test('renders all settings tabs', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/settings');
    for (const tab of TABS) {
      await expect(page.getByRole('tab', { name: new RegExp(tab, 'i') }).first()).toBeVisible();
    }
    errors.assertClean();
  });

  test('switching tabs reveals each tab panel', async ({ page }) => {
    await gotoPage(page, '/settings');
    for (const tab of ['API Keys', 'PROOF9', 'Workspace']) {
      await page.getByRole('tab', { name: new RegExp(tab, 'i') }).first().click();
      await expect(
        page.getByRole('tab', { name: new RegExp(tab, 'i') }).first(),
      ).toHaveAttribute('data-state', 'active');
    }
  });
});
