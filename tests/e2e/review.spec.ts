/**
 * Review page feature coverage (issue #684, nightly suite).
 * Seeded: workspace is a git repo with an uncommitted change to app.py.
 *
 * SERIAL, and it has to be (#964). The commit test consumes that seeded
 * working-tree change, so every test asserting on the diff must run before it.
 * The config sets `fullyParallel: true` and `retries: 2`, so relying on
 * declaration order alone was not enough: a retry of the commit test would
 * re-run against an already-committed repo and could never pass. `.serial`
 * makes the dependency enforced rather than commented, and skips the rest of
 * the file on a failure instead of reporting cascading phantom failures.
 *
 * The seed is also shared ACROSS PROJECTS (#1236): global-setup runs once per
 * `playwright test` invocation, and chromium → firefox → webkit run in turn
 * against that one workspace. Once chromium has committed app.py there is no
 * diff left for the next browser — which is how the nightly sweep stayed red
 * for 40 nights while the chromium-only smoke job stayed green. So the group
 * re-dirties app.py in `beforeAll`: every project (and every serial retry)
 * starts from an uncommitted change, whatever the previous one committed.
 */
import { test, expect } from '@playwright/test';
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { WORKSPACE_DIR } from './e2e-env';
import { gotoPage, trackConsoleErrors } from './helpers';

test.describe.serial('Review page', () => {
  test.beforeAll(({ browserName }) => {
    // Content must differ from whatever HEAD holds, or there is no diff.
    fs.writeFileSync(
      path.join(WORKSPACE_DIR, 'app.py'),
      `def hello():\n    return 'hello, e2e'  # reseeded for ${browserName} at ${Date.now()}\n`,
    );
  });

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

  // ── Commit flow (issue #964) ──────────────────────────────────────────────
  // Previously this file only asserted that one action button was visible, so
  // nothing exercised the Ship step end to end against a real API.
  //
  // ORDER MATTERS — see the .serial note in the file header: the commit test
  // consumes the seeded working-tree change, so it runs last.

  test('exports the working-tree patch', async ({ page }) => {
    await gotoPage(page, '/review');
    const exportBtn = page.getByRole('button', { name: /export patch/i });
    await expect(exportBtn).toBeVisible({ timeout: 20000 });
    await exportBtn.click();

    // The modal shows the patch itself, not just a spinner.
    await expect(page.getByText(/export patch/i).last()).toBeVisible();
    await expect(page.getByRole('textbox')).toContainText(/diff --git|app\.py/, {
      timeout: 20000,
    });
  });

  test('opens a PR from the checked-out branch (#1272)', async ({ page }) => {
    // The page used to send branch: '' and get a 422 before the handler ran.
    // GitHub is not reachable here, so the request is answered by a stub;
    // what is asserted is the payload the real page builds from git status.
    const branch = execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], {
      cwd: WORKSPACE_DIR,
      encoding: 'utf-8',
    }).trim();
    let sent: { branch?: string; title?: string } | null = null;
    await page.route('**/api/v2/pr?**', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      sent = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          number: 7, url: 'https://github.com/o/r/pull/7', state: 'open', title: 'T',
          body: '', created_at: new Date().toISOString(), merged_at: null,
          head_branch: branch, base_branch: 'main',
        }),
      });
    });

    await gotoPage(page, '/review');
    await page.getByLabel(/create pull request/i).check();
    await expect(page.getByText(`From branch ${branch}`)).toBeVisible();
    await page.getByLabel(/pr title/i).fill('E2E pull request');
    await page.getByRole('button', { name: /^create pr$/i }).click();

    await expect.poll(() => sent?.branch).toBe(branch);
    expect(branch).not.toBe('');
    expect(sent!.title).toBe('E2E pull request');
  });

  test('refuses to commit without a message', async ({ page }) => {
    await gotoPage(page, '/review');
    const box = page.getByLabel(/commit message/i);
    await expect(box).toBeVisible({ timeout: 20000 });
    // The page auto-generates a message once the diff loads. Wait for it, or a
    // generation that lands after the clear below re-enables Commit (#1272).
    await expect(box).not.toHaveValue('', { timeout: 20000 });

    await box.fill('');
    await expect(page.getByRole('button', { name: /^commit$/i })).toBeDisabled();
  });

  test('commits the seeded working-tree change', async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await gotoPage(page, '/review');

    // The seeded repo has one uncommitted file.
    await expect(page.getByText(/app\.py/).first()).toBeVisible({ timeout: 20000 });

    const message = page.getByLabel(/commit message/i);
    await expect(message).toBeVisible();
    await message.fill('test: commit from the e2e review flow');

    const commit = page.getByRole('button', { name: /^commit$/i });
    await expect(commit).toBeEnabled();
    await commit.click();

    // Outcome evidence: the page reports the new commit's short hash. A
    // "committed N files: <hash>" banner only appears after gitApi.commit
    // resolves, so this fails if the wiring is broken.
    await expect(page.getByText(/committed \d+ files?: [0-9a-f]{7}/i)).toBeVisible({
      timeout: 30000,
    });

    // And the diff empties, because the change is now committed.
    await expect(page.getByText(/no changed files|no changes/i).first()).toBeVisible({
      timeout: 20000,
    });

    errors.assertClean();
  });
});
