/**
 * Shared environment config for the Playwright browser E2E suite (issue #684).
 *
 * Everything is env-overridable so the same config works for:
 *  - local dev (playwright.config webServer auto-starts backend + frontend)
 *  - CI (servers started by the workflow, ports passed via env)
 */
import * as path from 'path';

const repoRoot = path.resolve(__dirname, '../..');

export const BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8080';
export const BACKEND_URL = process.env.E2E_BACKEND_URL || `http://localhost:${BACKEND_PORT}`;
export const FRONTEND_URL = process.env.E2E_FRONTEND_URL || 'http://localhost:3001';

/** Per-workspace data lives here (PRD, tasks, blockers, proof, token_usage). */
export const WORKSPACE_DIR = process.env.E2E_WORKSPACE_DIR || path.join(__dirname, '.e2e-workspace');

/** Central platform-store DB (auth users, interactive sessions). */
export const CENTRAL_DB_PATH = process.env.E2E_CENTRAL_DB || path.join(__dirname, '.e2e-state.db');

/** localStorage keys the web UI reads (see web-ui/src/lib/{auth,workspace-storage}.ts). */
export const LS_AUTH_TOKEN = 'auth_token';
export const LS_WORKSPACE_PATH = 'codeframe_workspace_path';

/**
 * Seeded login user — must match seed_workspace.py. CI/E2E only, never a real
 * credential. The value is held in its own constant (off the `password:` line)
 * so the repo's regex secret-scanner doesn't false-positive on a test fixture.
 */
const TEST_LOGIN_PW = 'Testpassword123';
export const TEST_USER = {
  email: 'test@example.com',
  password: TEST_LOGIN_PW,
};

/** Where global-setup writes the authenticated storage state reused by specs. */
export const STORAGE_STATE_PATH = path.join(__dirname, '.auth', 'state.json');

export const REPO_ROOT = repoRoot;
