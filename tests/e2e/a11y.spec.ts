/**
 * Accessibility baseline (#1298) — runs with the PR smoke suite.
 *
 * axe-core (WCAG 2.1 A/AA) over every core page at a laptop and a phone width.
 * Fails on any serious or critical violation; moderate and minor ones are left
 * to review. There was no automated a11y check anywhere before this, and the
 * first scan found 138 serious nodes: nameless nav links below 1024px, a
 * role=button task card wrapping its own actions, and AA contrast failures.
 */
import { test, expect, Page } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';
import { CORE_PAGES, gotoPage } from './helpers';
import { LS_WORKSPACE_PATH } from './e2e-env';

const WIDTHS = [1280, 390];
const BLOCKING = new Set(['serious', 'critical']);

/** Serious/critical axe violations on the current, settled frame. */
async function blockingViolations(page: Page): Promise<string[]> {
  // Buttons fade in over transition-all as they become enabled: a frame
  // mid-fade is no longer `disabled` (which axe skips) but still half
  // transparent, and read as a contrast failure. Scan settled frames only.
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'));
  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return violations
    .filter((v) => v.impact && BLOCKING.has(v.impact))
    .map(
      (v) =>
        `${v.id} (${v.impact}): ${v.help} — ` +
        v.nodes
          .map((n) => `${n.target.join(' ')} ${n.html.slice(0, 120)} [${(n.failureSummary ?? '').replace(/\s+/g, ' ').slice(0, 220)}]`)
          .join(' | ')
    );
}

for (const width of WIDTHS) {
  test.describe(`@smoke a11y at ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    for (const { path, heading } of CORE_PAGES) {
      test(`${path} has no serious or critical axe violations`, async ({ page }) => {
        await gotoPage(page, path);
        // Scan the rendered page, not the loading shell. /execution redirects
        // to a running task client-side; scanning mid-navigation saw no <title>.
        await expect(page.getByText(heading).first()).toBeVisible({ timeout: 15000 });
        // Not networkidle: the execution page holds an SSE stream open forever.
        await expect(page).toHaveTitle(/.+/);

        expect(await blockingViolations(page), `axe violations on ${path} at ${width}px`).toEqual([]);
      });
    }

    // Two views the seeded core pages never show (#1393).
    test('the workspace selector (no workspace chosen) has no serious or critical axe violations', async ({ page }) => {
      // Opening the seeded workspace registers it, so it lists as a recent
      // project; then drop the selection to land on the selector.
      await gotoPage(page, '/');
      await page.evaluate((key) => window.localStorage.removeItem(key), LS_WORKSPACE_PATH);
      await page.goto('/', { waitUntil: 'domcontentloaded' });
      await expect(page.getByText('Recent Projects', { exact: true }).first()).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: /Remove .* from recent projects/ }).first()).toBeVisible();

      expect(await blockingViolations(page), `axe violations on the workspace selector at ${width}px`).toEqual([]);
    });

    test('the proof page with run history has no serious or critical axe violations', async ({ page }) => {
      await gotoPage(page, '/proof');
      await expect(page.getByRole('heading', { name: 'Recent Runs' })).toBeVisible({ timeout: 15000 });
      // The seeded run (#1393): a row in the table, its control a button in a cell.
      await expect(page.locator('table').getByRole('button', { pressed: false }).first()).toBeVisible();

      expect(await blockingViolations(page), `axe violations on /proof run history at ${width}px`).toEqual([]);
    });
  });
}
