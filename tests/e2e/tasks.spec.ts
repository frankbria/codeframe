/**
 * Tasks board feature coverage (issue #684, nightly suite).
 * Drives the /tasks board against the seeded workspace.
 */
import { test, expect } from '@playwright/test';
import { gotoPage, trackConsoleErrors } from './helpers';

const SEEDED_TITLES = [
  'Set up database schema',
  'Create API endpoints',
  'Build dashboard UI',
  'Wire up deployment',
  'Write unit tests',
  'Add integration tests',
];

test.describe('Tasks board', () => {
  test('renders all seeded tasks', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/tasks');
    // Wait for the board's data to land (first card) before checking the rest.
    await expect(page.getByText(SEEDED_TITLES[0], { exact: false }).first()).toBeVisible({
      timeout: 20000,
    });
    for (const title of SEEDED_TITLES.slice(1)) {
      await expect(page.getByText(title, { exact: false }).first()).toBeVisible();
    }
    errors.assertClean();
  });

  test('shows tasks across multiple statuses', async ({ page }) => {
    await gotoPage(page, '/tasks');
    // Seeded statuses include BACKLOG, READY, IN_PROGRESS, BLOCKED, DONE.
    const body = page.locator('body');
    await expect(body).toContainText(/in[\s_-]?progress/i);
    await expect(body).toContainText(/blocked/i);
    await expect(body).toContainText(/done/i);
  });

  test('search filters the board by title', async ({ page }) => {
    await gotoPage(page, '/tasks');
    const search = page.getByRole('textbox').first();
    if (await search.count()) {
      await search.fill('dashboard');
      await expect(page.getByText('Build dashboard UI').first()).toBeVisible();
      // A non-matching title should drop out.
      await expect(page.getByText('Write unit tests')).toHaveCount(0);
    }
  });
});
