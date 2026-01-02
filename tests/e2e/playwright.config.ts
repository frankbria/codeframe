import { defineConfig, devices } from '@playwright/test';
import { TEST_DB_PATH, FRONTEND_URL } from './e2e-config';

/**
 * Playwright configuration for E2E tests.
 * See https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './',
  testMatch: '*.spec.ts',

  /* Exclude debug tests from CI runs */
  testIgnore: process.env.CI ? ['debug-error.spec.ts'] : [],

  /* Global setup - creates test project */
  globalSetup: './global-setup.ts',

  /* Run tests in files in parallel */
  fullyParallel: true,

  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,

  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,

  /* Opt out of parallel tests on CI */
  workers: process.env.CI ? 1 : undefined,

  /* Reporter to use */
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
    ['json', { outputFile: 'playwright-report/results.json' }]
  ],

  /* Shared settings for all the projects below */
  use: {
    /* Base URL to use in actions like `await page.goto('/')` */
    baseURL: FRONTEND_URL,

    /* Collect trace when retrying the failed test */
    trace: 'on-first-retry',

    /* Screenshot on failure */
    screenshot: 'only-on-failure',

    /* Video on failure */
    video: 'retain-on-failure',

    /* Maximum time each action such as `click()` can take */
    actionTimeout: 10000,
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },

    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },

    /* Test against mobile viewports */
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],

  /* Run local dev server before starting the tests */
  webServer: process.env.CI
    ? undefined // On CI, servers are started separately
    : [
        // Backend FastAPI server
        {
          command: `cd ../.. && DATABASE_PATH=${TEST_DB_PATH} uv run uvicorn codeframe.ui.server:app --port 8080`,
          url: 'http://localhost:8080/ws/health',
          reuseExistingServer: !process.env.CI,
          timeout: 120000,
        },
        // Frontend Next.js production server (on port 3001 to avoid conflicts)
        // Note: reuseExistingServer is false to ensure TEST_DB_PATH is picked up
        // Note: NEXT_PUBLIC_APP_URL is set to match FRONTEND_URL for BetterAuth client
        {
          command: `cd ../../web-ui && rm -rf .next && TEST_DB_PATH=${TEST_DB_PATH} NEXT_PUBLIC_APP_URL=${FRONTEND_URL} PORT=3001 npm run build && TEST_DB_PATH=${TEST_DB_PATH} NEXT_PUBLIC_APP_URL=${FRONTEND_URL} PORT=3001 npm start`,
          url: FRONTEND_URL,
          reuseExistingServer: false,
          timeout: 120000,
        },
      ],

  /* Global timeout for each test - increased for CI */
  timeout: process.env.CI ? 60000 : 30000,

  /* Expect timeout - increased for CI */
  expect: {
    timeout: process.env.CI ? 10000 : 5000,
  },
});
