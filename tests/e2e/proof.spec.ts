/**
 * PROOF9 page feature coverage (issue #684, nightly suite).
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe('PROOF9 page', () => {
  test('lists the seeded requirement', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/proof');
    await expect(page.getByText('REQ-0001').first()).toBeVisible();
    await expect(page.getByText(/Task board must render seeded tasks/i).first()).toBeVisible();
    errors.assertClean();
  });

  test('exposes Capture Glitch and Run Gates actions', async ({ page }) => {
    await gotoPage(page, '/proof');
    // Accessible names come from aria-labels ("Capture a glitch…", "Run all proof gates").
    await expect(
      page.getByRole('button', { name: /capture (a )?glitch/i }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /run (all proof )?gates/i }).first(),
    ).toBeVisible();
  });

  test('navigates to the requirement detail page', async ({ page }) => {
    await gotoPage(page, '/proof');
    await page.getByRole('link', { name: /REQ-0001/i }).first().click();
    await expect(page).toHaveURL(/\/proof\/REQ-0001/i);
    await expect(page.getByText(/Task board must render seeded tasks/i).first()).toBeVisible();
  });
});
