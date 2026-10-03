/**
 * The session terminal runs what you type (#1291).
 *
 * bash ran on pipes, so it never treated xterm.js's Enter ("\r") as end of
 * line: the terminal on /sessions/[id] connected and accepted keystrokes, and
 * nothing ever ran. This types through the real xterm.js component, so Enter
 * reaches the server exactly as a user's does, and asserts on computed output
 * ($((6*7)) -> 42), which an echo of the typed text cannot satisfy.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { BACKEND_URL, LS_AUTH_TOKEN, STORAGE_STATE_PATH, WORKSPACE_DIR } from './e2e-env';
import { gotoPage } from './helpers';

function authToken(): string {
  const state = JSON.parse(fs.readFileSync(STORAGE_STATE_PATH, 'utf-8'));
  const entry = state.origins?.[0]?.localStorage?.find(
    (item: { name: string }) => item.name === LS_AUTH_TOKEN,
  );
  if (!entry?.value) throw new Error('no auth_token in storageState');
  return entry.value;
}

test.describe('Session terminal', () => {
  test('runs a command typed with Enter @smoke', async ({ page, request }) => {
    const res = await request.post(`${BACKEND_URL}/api/v2/sessions`, {
      headers: { Authorization: `Bearer ${authToken()}` },
      data: { workspace_path: path.resolve(WORKSPACE_DIR), agent_type: 'claude' },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    const { id } = await res.json();

    await gotoPage(page, `/sessions/${id}`);
    const terminal = page.locator('.xterm').first();
    await expect(terminal).toBeVisible();
    await terminal.click();

    await page.keyboard.type('echo HELLO_$((6*7))');
    await page.keyboard.press('Enter');

    await expect(page.locator('.xterm-rows')).toContainText('HELLO_42', { timeout: 15_000 });
  });
});
