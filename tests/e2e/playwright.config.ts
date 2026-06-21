import { defineConfig, devices } from '@playwright/test';
import {
  BACKEND_PORT,
  BACKEND_URL,
  CENTRAL_DB_PATH,
  FRONTEND_URL,
  STORAGE_STATE_PATH,
} from './e2e-env';

/**
 * Playwright config for the rewritten browser E2E suite (issue #684).
 *
 * Targets the current Phase-3+ workspace UI. `global-setup.ts` seeds a workspace
 * and writes an authenticated storageState that authenticated specs reuse.
 *
 * Selection:
 *   - PR smoke:  playwright test --project=chromium --grep @smoke
 *   - Nightly:   playwright test            (all projects, all specs)
 */

const frontendPort = new URL(FRONTEND_URL).port || '3001';
const AUTH_SECRET = 'e2e-test-secret-not-a-real-credential';

// Point ALL client transports at the test backend at build time (Next.js bakes
// NEXT_PUBLIC_* into client code). Without SSE/WS, streaming hooks fall back to
// :8000 and fail cross-origin.
const WS_URL = BACKEND_URL.replace(/^http/, 'ws');
const FRONTEND_BUILD_ENV =
  `NEXT_PUBLIC_API_URL=${BACKEND_URL} NEXT_PUBLIC_SSE_URL=${BACKEND_URL} NEXT_PUBLIC_WS_URL=${WS_URL} PORT=${frontendPort}`;

export default defineConfig({
  testDir: './',
  testMatch: '*.spec.ts',
  globalSetup: './global-setup.ts',

  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // SQLite (workspace + central DB) doesn't love concurrent writers.
  workers: 1,

  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],
    ['json', { outputFile: 'playwright-report/results.json' }],
  ],

  timeout: process.env.CI ? 60000 : 30000,
  expect: { timeout: process.env.CI ? 15000 : 10000 },

  use: {
    baseURL: FRONTEND_URL,
    storageState: STORAGE_STATE_PATH,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],

  // Start backend + frontend for local runs; in CI the workflow can reuse an
  // already-running pair (reuseExistingServer is true off-CI only).
  webServer: [
    {
      command: `AUTH_SECRET=${AUTH_SECRET} DATABASE_PATH=${CENTRAL_DB_PATH} uv run uvicorn codeframe.ui.server:app --port ${BACKEND_PORT}`,
      cwd: '../..',
      url: `${BACKEND_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      command: `${FRONTEND_BUILD_ENV} npm run build && ${FRONTEND_BUILD_ENV} npm start`,
      cwd: '../../web-ui',
      url: FRONTEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 300000,
    },
  ],
});
