/**
 * Accessibility baseline (#1298) — runs with the PR smoke suite.
 *
 * axe-core (WCAG 2.1 A/AA) over every core page at a laptop and a phone width.
 * Fails on any serious or critical violation; moderate and minor ones are left
 * to review. There was no automated a11y check anywhere before this, and the
 * first scan found 138 serious nodes: nameless nav links below 1024px, a
 * role=button task card wrapping its own actions, and AA contrast failures.
 */
import { test, expect } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';
import { CORE_PAGES, gotoPage } from './helpers';

const WIDTHS = [1280, 390];
const BLOCKING = new Set(['serious', 'critical']);

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
        // Buttons fade in over transition-all as they become enabled: a frame
        // mid-fade is no longer `disabled` (which axe skips) but still half
        // transparent, and read as a contrast failure. Scan settled frames only.
        await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running'));

        const { violations } = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();
        const blocking = violations
          .filter((v) => v.impact && BLOCKING.has(v.impact))
          .map(
            (v) =>
              `${v.id} (${v.impact}): ${v.help} — ` +
              v.nodes
                .map((n) => `${n.target.join(' ')} ${n.html.slice(0, 120)} [${(n.failureSummary ?? '').replace(/\s+/g, ' ').slice(0, 220)}]`)
                .join(' | ')
          );

        expect(blocking, `axe violations on ${path} at ${width}px`).toEqual([]);
      });
    }
  });
}
