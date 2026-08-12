/**
 * The Golden Path through the browser, end to end (#1068).
 *
 * #948 deleted `tests/lifecycle/test_web_lifecycle.py` because it was green
 * theatre: a `@pytest.mark.skip` class whose methods raised NotImplementedError,
 * so `scripts/lifecycle --mode web` collected only skips and exited 0 while
 * CLAUDE.md advertised it as the pre-PR gate. #1147 replaced the API half; this
 * is the web half.
 *
 * What makes it different from every other spec here: the rest of the suite
 * asserts how a PRE-SEEDED workspace renders. This one starts from an empty
 * directory and drives the product — PRD upload, task generation, approval,
 * execution — entirely through the UI, then checks the workspace actually
 * changed. Rendering seeded rows cannot catch a broken write path; this can.
 *
 * Runs on `CODEFRAME_LLM_PROVIDER=mock` (set on the backend webServer in
 * playwright.config.ts), so it is free and deterministic.
 */
import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { spawnSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import {
  BACKEND_URL,
  LIFECYCLE_WORKSPACE_DIR,
  LS_AUTH_TOKEN,
  LS_WORKSPACE_PATH,
  STORAGE_STATE_PATH,
} from './e2e-env';
import { trackConsoleErrors } from './helpers';

const WORKSPACE = path.resolve(LIFECYCLE_WORKSPACE_DIR);

const PRD_TITLE = 'Lifecycle CSV Stats';

/**
 * What the mock provider answers the task-decomposition prompt with
 * (codeframe/adapters/llm/mock.py). Hard-coded on purpose: a lifecycle test
 * that accepts "some cards appeared" cannot tell decomposition from an empty
 * board with a spinner.
 */
const FIRST_TASK = 'Implement the core function';
const SECOND_TASK = 'Add a test for the core function';
const PRD_CONTENT = `# ${PRD_TITLE}

## Requirements

- Implement a mean function in stats.py
- Add a test for the mean function
`;

/** The JWT global-setup obtained, so this spec can call the API directly. */
function authToken(): string {
  const state = JSON.parse(fs.readFileSync(STORAGE_STATE_PATH, 'utf-8'));
  const entry = state.origins?.[0]?.localStorage?.find(
    (item: { name: string }) => item.name === LS_AUTH_TOKEN,
  );
  if (!entry?.value) throw new Error('no auth_token in storageState');
  return entry.value;
}

function git(...args: string[]) {
  const result = spawnSync('git', args, { cwd: WORKSPACE, encoding: 'utf-8' });
  if (result.status !== 0) {
    throw new Error(`git ${args.join(' ')} failed: ${result.stderr}`);
  }
}

/**
 * Point the browser at THIS spec's workspace instead of the seeded one.
 *
 * `addInitScript` runs before any page script on every navigation, which is the
 * only reliable moment: the app reads localStorage during its first render, so
 * writing it after `goto` races the auth guard.
 */
async function useLifecycleWorkspace(page: Page) {
  const token = authToken();
  await page.addInitScript(
    ([tokenKey, tokenValue, pathKey, pathValue]) => {
      window.localStorage.setItem(tokenKey, tokenValue);
      window.localStorage.setItem(pathKey, pathValue);
    },
    [LS_AUTH_TOKEN, token, LS_WORKSPACE_PATH, WORKSPACE] as const,
  );
}

/** Task title → status, read straight from the API. */
async function taskStatuses(request: APIRequestContext): Promise<Map<string, string>> {
  const res = await request.get(`${BACKEND_URL}/api/v2/tasks`, {
    headers: { Authorization: `Bearer ${authToken()}` },
    params: { workspace_path: WORKSPACE },
  });
  if (!res.ok()) return new Map();
  const body = await res.json();
  return new Map(
    body.tasks.map((t: { title: string; status: string }) => [t.title, t.status]),
  );
}

async function goto(page: Page, urlPath: string) {
  await page.goto(urlPath, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('main, [role="main"]').first()).toBeVisible({ timeout: 20000 });
}

// Serial: the later tests assert on state the first one created. fullyParallel
// is on for the rest of the suite, and an out-of-order run here would report a
// missing PRD rather than the pipeline failing.
test.describe.configure({ mode: 'serial' });

test.describe('@lifecycle Golden Path through the web UI', () => {
  test.beforeAll(async ({ request }) => {
    // A real git repo: workspace init and the gates both need one.
    fs.rmSync(WORKSPACE, { recursive: true, force: true });
    fs.mkdirSync(WORKSPACE, { recursive: true });
    git('init', '-q');
    git('config', 'user.email', 'e2e@test.local');
    git('config', 'user.name', 'E2E');
    fs.writeFileSync(path.join(WORKSPACE, 'README.md'), '# lifecycle demo\n');
    git('add', '-A');
    git('commit', '-qm', 'init');

    // Register it. The UI has no "create workspace from nothing" screen — it
    // reads a path out of localStorage — so this one step is API-side. Every
    // pipeline step after it goes through the browser.
    const res = await request.post(`${BACKEND_URL}/api/v2/workspaces`, {
      headers: { Authorization: `Bearer ${authToken()}` },
      data: { repo_path: WORKSPACE },
    });
    expect(res.status(), await res.text()).toBe(201);
  });

  test.beforeEach(async ({ page }) => {
    await useLifecycleWorkspace(page);
  });

  test('a user builds a project from an empty workspace', async ({ page, request }) => {
    const errors = trackConsoleErrors(page);

    // ---- THINK: upload a PRD -------------------------------------------
    await goto(page, '/prd');
    // Scoped to the header: the empty state renders its own Upload PRD CTA, so
    // an unscoped match is ambiguous on exactly the page this test starts from.
    await page
      .locator('header')
      .getByRole('button', { name: /upload prd|upload new/i })
      .click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByPlaceholder(/paste your prd markdown here/i).fill(PRD_CONTENT);
    await dialog.getByRole('button', { name: /create prd/i }).click();

    await expect(dialog).toBeHidden({ timeout: 20000 });
    // The editor shows what was saved, not just a success toast.
    await expect(page.getByText(/mean function in stats\.py/i).first()).toBeVisible({
      timeout: 20000,
    });

    // ---- THINK: generate tasks -----------------------------------------
    const generate = page.getByRole('button', { name: /generate tasks/i });
    await expect(generate).toBeEnabled();
    await generate.click();

    // Generation reports via a toast and does NOT navigate. Asserting the
    // count here is what distinguishes "the button did something" from "the
    // decomposer produced tasks".
    await expect(page.getByText(/generated \d+ tasks? from prd/i)).toBeVisible({
      timeout: 60000,
    });

    await goto(page, '/tasks');
    const card = page.getByLabel(`View details for ${FIRST_TASK}`);
    await expect(card).toBeVisible({ timeout: 30000 });
    // The decomposition has a real dependency edge, which is the thing the
    // prompt says an empty graph would mean it got wrong.
    await expect(page.getByLabel(`View details for ${SECOND_TASK}`)).toBeVisible();

    // ---- BUILD: approve one task ---------------------------------------
    // Scoped to the card, not the board: `.first()` would silently act on
    // whichever card the board happened to order first.
    await card.getByRole('button', { name: /mark ready/i }).click();

    // A READY task offers Execute; a BACKLOG one does not. Waiting on the
    // button is waiting on the status transition having actually landed.
    const execute = card.getByRole('button', { name: /^execute$/i });
    await expect(execute).toBeVisible({ timeout: 30000 });

    // ---- BUILD: run it --------------------------------------------------
    await execute.click();
    await expect(page).toHaveURL(/\/execution\//, { timeout: 30000 });
    await expect(page.getByText(FIRST_TASK).first()).toBeVisible({ timeout: 30000 });

    // The outcome is the task's status, polled from the API — NOT a text match
    // on the page. `/done|completed|failed|blocked/` would have matched the
    // sidebar's "Blockers" link and passed before the run finished, which is
    // the sort of assertion that reports success for a run that never
    // happened. mock completes in seconds; the budget is generous because this
    // is the one genuinely async step.
    await expect
      .poll(async () => (await taskStatuses(request)).get(FIRST_TASK), {
        timeout: 120000,
      })
      .toBe('DONE');

    errors.assertClean();
  });

  test('the workspace on disk reflects what the browser did', async ({ request }) => {
    // The UI can render anything. This asserts the pipeline actually wrote
    // through — the failure mode a render-only spec cannot see.
    const headers = { Authorization: `Bearer ${authToken()}` };
    const params = { workspace_path: WORKSPACE };

    // /latest, not the collection route — the list returns metadata only, so
    // asserting on its body would have passed for a PRD with no content at all.
    const prd = await request.get(`${BACKEND_URL}/api/v2/prd/latest`, { headers, params });
    expect(prd.status(), await prd.text()).toBe(200);
    expect(await prd.text()).toContain('mean function in stats.py');

    const statuses = await taskStatuses(request);

    // Exact, not "something moved": the approved task ran to completion and the
    // one that was never approved is untouched. A looser assertion would pass
    // if approval had leaked to the whole backlog — the #1146 failure mode.
    expect(statuses.get(FIRST_TASK)).toBe('DONE');
    expect(statuses.get(SECOND_TASK)).toBe('BACKLOG');
  });

  test('the seeded workspace was not touched', async ({ request }) => {
    // This spec writes for real, and every other spec asserts against the
    // seeded workspace. If the two ever share a directory those specs start
    // failing for reasons that have nothing to do with them.
    const { WORKSPACE_DIR } = await import('./e2e-env');
    const seeded = await request.get(`${BACKEND_URL}/api/v2/tasks`, {
      headers: { Authorization: `Bearer ${authToken()}` },
      params: { workspace_path: path.resolve(WORKSPACE_DIR) },
    });

    expect(seeded.status()).toBe(200);
    const titles = (await seeded.json()).tasks.map((t: { title: string }) => t.title);
    expect(titles).toContain('Set up database schema');
    expect(titles).not.toContain(PRD_TITLE);
  });
});
