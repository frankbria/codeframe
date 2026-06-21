/**
 * Shared helpers for the browser E2E suite (issue #684).
 */
import { Page, expect } from '@playwright/test';

/** The current Phase-3+ workspace pages and a stable landmark on each. */
export interface PageCheck {
  path: string;
  /** A heading/text reliably present once the page renders. */
  heading: RegExp;
}

export const CORE_PAGES: PageCheck[] = [
  { path: '/', heading: /workspace|tasks|overview|dashboard/i },
  { path: '/prd', heading: /prd|product requirements/i },
  { path: '/tasks', heading: /tasks|backlog|ready/i },
  { path: '/execution', heading: /execution|batch|run/i },
  { path: '/blockers', heading: /blocker/i },
  { path: '/proof', heading: /proof9|requirements/i },
  { path: '/review', heading: /review|changes|diff/i },
  { path: '/sessions', heading: /session/i },
  { path: '/settings', heading: /settings|agent|api keys/i },
  { path: '/costs', heading: /cost|spend/i },
];

/**
 * Benign console messages that don't indicate a real UI failure. Keep this list
 * SHORT and specific — the point of the guard is to catch real wiring bugs.
 */
const BENIGN_CONSOLE = [
  /favicon/i,
  /ResizeObserver loop/i,
  /Download the React DevTools/i,
  /\[Fast Refresh\]/i,
  // Browser-emitted network logs for expected 4xx responses (e.g. /review/diff
  // 400 on a non-git dir, optional integrations not configured). We still flag
  // 5xx and uncaught JS exceptions — those are real wiring bugs.
  /Failed to load resource: the server responded with a status of 4\d\d/i,
  // Background real-time channels (task SSE stream, agent websocket) are
  // best-effort against an idle seeded workspace — a stream that never produces
  // events or closes on navigation is not a page-render failure.
  /EventSource|\/stream\b|websocket|ws:\/\//i,
];

/**
 * Attach a console/page-error collector. Returns a function that asserts no
 * unexpected errors were seen. Network 401s on a clean (pre-login) page are
 * expected, so callers can pass `ignore` patterns.
 */
export function trackConsoleErrors(page: Page, ignore: RegExp[] = []) {
  const errors: string[] = [];
  const filters = [...BENIGN_CONSOLE, ...ignore];

  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (filters.some((re) => re.test(text))) return;
    errors.push(text);
  });
  page.on('pageerror', (err) => {
    const text = err.message;
    if (filters.some((re) => re.test(text))) return;
    errors.push(text);
  });

  return {
    assertClean() {
      expect(errors, `Unexpected console errors:\n${errors.join('\n')}`).toEqual([]);
    },
    get errors() {
      return errors;
    },
  };
}

/** Visit a page and wait for the app shell + main content to settle. */
export async function gotoPage(page: Page, urlPath: string) {
  await page.goto(urlPath, { waitUntil: 'domcontentloaded' });
  // The shell renders <main> once the client auth guard resolves.
  await expect(page.locator('main, [role="main"]').first()).toBeVisible({ timeout: 15000 });
}
