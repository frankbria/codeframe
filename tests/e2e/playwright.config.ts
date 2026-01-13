import { defineConfig, devices } from '@playwright/test';
import { TEST_DB_PATH, FRONTEND_URL } from './e2e-config';
import { BROWSER_TIMEOUTS } from './browser-config';

/**
 * Playwright configuration for E2E tests.
 *
 * Cross-Browser Compatibility Notes:
 * - Chromium: Baseline browser, default timeouts
 * - Firefox: +50% timeouts for CSS rendering, filter NS_BINDING_ABORTED errors
 * - WebKit: +40% timeouts for element stabilization, retry on flaky tests
 * - Mobile: Touch events, scroll handling, extended timeouts for network
 *
 * See https://playwright.dev/docs/test-configuration
 */

// Environment variable to filter specific browsers (e.g., E2E_BROWSER_FILTER=chromium,firefox)
const browserFilter = process.env.E2E_BROWSER_FILTER?.split(',').map((b) => b.trim().toLowerCase());

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

  /* Retry on CI only - Firefox and WebKit get extra retries */
  retries: process.env.CI ? 2 : 0,

  /* SQLite doesn't handle concurrent writes well, so always use 1 worker.
   * Multiple workers cause "database is locked" errors during parallel tests. */
  workers: 1,

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
    actionTimeout: BROWSER_TIMEOUTS.chromium.action,

    /* Don't ignore HTTPS errors - catch certificate issues */
    ignoreHTTPSErrors: false,

    /* Enable strict mode in CI to catch selector ambiguity issues */
    ...(process.env.CI && {
      strictSelectors: true,
    }),
  },

  /* Configure projects for major browsers with browser-specific settings */
  projects: [
    // =========================================================================
    // CHROMIUM (Baseline)
    // =========================================================================
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },

    // =========================================================================
    // FIREFOX - Slower CSS rendering, NS_BINDING_ABORTED during navigation
    // =========================================================================
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        // Extended timeouts for Firefox's slower CSS rendering
        actionTimeout: BROWSER_TIMEOUTS.firefox.action,
        // Reduce motion to avoid animation timing issues
        contextOptions: {
          reducedMotion: 'reduce',
        },
      },
      // Firefox gets extra retries due to timing-sensitive failures
      retries: process.env.CI ? 3 : 1,
    },

    // =========================================================================
    // WEBKIT - Delayed element rendering, localStorage timing issues
    // =========================================================================
    {
      name: 'webkit',
      use: {
        ...devices['Desktop Safari'],
        // Extended timeouts for WebKit's delayed rendering
        actionTimeout: BROWSER_TIMEOUTS.webkit.action,
      },
      // WebKit gets extra retries due to element stability issues
      retries: process.env.CI ? 3 : 1,
    },

    // =========================================================================
    // MOBILE CHROME - Touch events, smaller viewports
    // =========================================================================
    {
      name: 'Mobile Chrome',
      use: {
        ...devices['Pixel 5'],
        // Ensure touch mode is enabled
        isMobile: true,
        hasTouch: true,
        // Extended timeouts for mobile network and touch handling
        actionTimeout: BROWSER_TIMEOUTS.mobile.action,
      },
      // Mobile gets extra retries due to viewport/touch issues
      retries: process.env.CI ? 2 : 1,
    },

    // =========================================================================
    // MOBILE SAFARI - Touch events, WebKit quirks on mobile
    // =========================================================================
    {
      name: 'Mobile Safari',
      use: {
        ...devices['iPhone 12'],
        // Ensure touch mode is enabled
        isMobile: true,
        hasTouch: true,
        // Extended timeouts (mobile + WebKit)
        actionTimeout: BROWSER_TIMEOUTS.mobile.action,
      },
      // Mobile Safari gets most retries (mobile + WebKit quirks)
      retries: process.env.CI ? 3 : 1,
    },
  ].filter((project) => {
    // Filter projects if E2E_BROWSER_FILTER is set
    if (!browserFilter) return true;
    const projectName = project.name.toLowerCase();
    return browserFilter.some(
      (filter) => projectName.includes(filter) || filter.includes(projectName)
    );
  }),

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
        // Note: NEXT_PUBLIC_API_URL must be set at BUILD TIME for Next.js to bake it into client code
        {
          command: `cd ../../web-ui && rm -rf .next && TEST_DB_PATH=${TEST_DB_PATH} NEXT_PUBLIC_API_URL=http://localhost:8080 PORT=3001 npm run build && TEST_DB_PATH=${TEST_DB_PATH} NEXT_PUBLIC_API_URL=http://localhost:8080 PORT=3001 npm start`,
          url: FRONTEND_URL,
          reuseExistingServer: !process.env.CI,
          timeout: 120000,
        },
      ],

  /* Global timeout for each test - increased for CI */
  timeout: process.env.CI ? 60000 : 30000,

  /* Expect timeout - increased for CI
   * Note: Browser-specific expect timeouts are handled via getBrowserTimeout() in test-utils.ts
   * This is the base timeout; Firefox and WebKit tests use 1.5x and 1.4x multipliers respectively
   */
  expect: {
    timeout: process.env.CI ? 10000 : BROWSER_TIMEOUTS.chromium.expect,
  },
});
