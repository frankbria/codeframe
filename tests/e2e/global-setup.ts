/**
 * Global setup for the browser E2E suite (issue #684).
 *
 * Runs AFTER Playwright's webServer is up (backend reachable). Steps:
 *   1. Wipe + recreate the test workspace dir.
 *   2. Seed deterministic data (workspace PRD/tasks/blockers/proof/costs +
 *      the central JWT login user) via seed_workspace.py.
 *   3. Log in through the real API to get a JWT.
 *   4. Write a storageState file so authenticated specs start already signed in
 *      with a workspace selected (localStorage auth_token + workspace path).
 */
import { request as playwrightRequest, FullConfig } from '@playwright/test';
import { spawnSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import {
  BACKEND_URL,
  CENTRAL_DB_PATH,
  FRONTEND_URL,
  LS_AUTH_TOKEN,
  LS_WORKSPACE_PATH,
  REPO_ROOT,
  STORAGE_STATE_PATH,
  TEST_USER,
  WORKSPACE_DIR,
} from './e2e-env';

async function globalSetup(_config: FullConfig) {
  const workspaceDir = path.resolve(WORKSPACE_DIR);

  // 1. Fresh workspace dir.
  fs.rmSync(workspaceDir, { recursive: true, force: true });
  fs.mkdirSync(workspaceDir, { recursive: true });

  // 2. Seed. The backend already initialized the central DB at startup, so the
  //    users table exists for the login-user insert.
  const seed = spawnSync(
    'uv',
    ['run', 'python', path.join(__dirname, 'seed_workspace.py'), workspaceDir, path.resolve(CENTRAL_DB_PATH)],
    { cwd: REPO_ROOT, stdio: 'inherit', encoding: 'utf-8' },
  );
  if (seed.status !== 0) {
    throw new Error(`seed_workspace.py failed with exit code ${seed.status}`);
  }

  // 3. Real login → JWT.
  const api = await playwrightRequest.newContext();
  const res = await api.post(`${BACKEND_URL}/auth/jwt/login`, {
    form: { username: TEST_USER.email, password: TEST_USER.password },
  });
  if (!res.ok()) {
    throw new Error(`Login failed: ${res.status()} ${await res.text()}`);
  }
  const token = (await res.json()).access_token as string;
  if (!token) throw new Error('Login response had no access_token');
  await api.dispose();

  // 4. storageState: authenticated + workspace selected.
  fs.mkdirSync(path.dirname(STORAGE_STATE_PATH), { recursive: true });
  fs.writeFileSync(
    STORAGE_STATE_PATH,
    JSON.stringify({
      cookies: [],
      origins: [
        {
          origin: FRONTEND_URL,
          localStorage: [
            { name: LS_AUTH_TOKEN, value: token },
            { name: LS_WORKSPACE_PATH, value: workspaceDir },
          ],
        },
      ],
    }),
  );

  console.log(`✅ E2E setup ready — workspace=${workspaceDir} backend=${BACKEND_URL}`);
}

export default globalSetup;
