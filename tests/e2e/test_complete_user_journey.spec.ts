/**
 * E2E Tests: Complete User Journey
 *
 * Tests the full end-to-end workflow from authentication to agent execution:
 * 1. Authenticate using FastAPI backend auth (JWT tokens)
 * 2. Create a new project OR use seeded project
 * 3. Verify discovery UI displays correctly
 * 4. Answer discovery questions (conditional on API key)
 * 5. Wait for PRD generation (conditional on API key)
 * 6. Verify agent execution begins
 * 7. Verify dashboard panels are accessible
 *
 * Test Strategy:
 * - UI-only tests use pre-seeded data from seed-test-data.py
 * - Full flow tests requiring Claude API are conditional on ANTHROPIC_API_KEY
 * - Runs locally with API key, skips API-dependent tests in CI
 */

import { test, expect } from '@playwright/test';
import {
  answerDiscoveryQuestion,
  loginUser,
  createTestProject,
  setupErrorMonitoring,
  checkTestErrors,
  ExtendedPage
} from './test-utils';
import { FRONTEND_URL } from './e2e-config';

// Check if API key is available for tests that require Claude API calls
const HAS_API_KEY = !!process.env.ANTHROPIC_API_KEY;
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test.describe('Complete User Journey', () => {
  // Login using real authentication flow
  test.beforeEach(async ({ context, page }) => {
    // Setup error monitoring
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    await context.clearCookies();
    await loginUser(page);
  });

  test.afterEach(async ({ page }) => {
    // STRICT ERROR CHECKING: Only filter navigation cancellation
    // All other errors (WebSocket, API, network) MUST cause test failures
    // This is the "complete user journey" - EVERYTHING must work!
    checkTestErrors(page, 'Complete user journey test', [
      'net::ERR_ABORTED'  // Normal when navigation cancels pending requests
    ]);
  });

  test('should verify authenticated access and discovery UI with seeded data', async ({ page }) => {
    // Step 1: Verify authentication (via session set in beforeEach)
    await page.goto(`${FRONTEND_URL}/`);

    // Should be on projects page, not redirected to login
    await expect(page).toHaveURL(/\/(projects)?$/);

    // Step 2: Navigate to seeded project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);

    // Step 3: Verify discovery question is visible (uses seeded data)
    await expect(page.getByTestId('discovery-question')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('discovery-answer-input')).toBeVisible();

    // Step 4: Verify dashboard header is visible
    await expect(page.getByTestId('dashboard-header')).toBeVisible();

    // Step 5: Verify agent status panel is visible
    await expect(page.getByTestId('agent-status-panel')).toBeVisible({ timeout: 10000 });

    // Step 6: Verify navigation tabs are accessible
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await expect(tasksTab).toBeVisible();
    await tasksTab.click();

    // Verify tasks panel loads
    await expect(page.locator('[data-testid="tasks-panel"]')).toBeVisible({ timeout: 10000 });

    // Navigate to checkpoints tab
    const checkpointTab = page.locator('[data-testid="checkpoint-tab"]');
    const checkpointTabCount = await checkpointTab.count();

    if (checkpointTabCount > 0 && await checkpointTab.isVisible()) {
      await checkpointTab.click();
      await expect(page.locator('[data-testid="checkpoint-panel"]')).toBeAttached({ timeout: 10000 });
    }

    // Return to overview/first tab
    const overviewTab = page.locator('[data-testid="overview-tab"]');
    const overviewTabCount = await overviewTab.count();

    if (overviewTabCount > 0 && await overviewTab.isVisible()) {
      await overviewTab.click();
    }
  });

  test(HAS_API_KEY ? 'should complete full workflow from authentication to agent execution' : 'skip: requires ANTHROPIC_API_KEY',
    async ({ page }) => {
      // This test requires Claude API calls - skip in CI, run locally with API key
      test.skip(!HAS_API_KEY, 'Requires ANTHROPIC_API_KEY for Claude API calls');

      // Step 1: Verify authentication (via session cookie set in beforeEach)
      // Navigate to root to verify we're authenticated
      await page.goto(`${FRONTEND_URL}/`);
      await expect(page.getByTestId('user-menu')).toBeVisible();

      // Step 2: Create a new project using helper (handles UI + start endpoint)
      const projectName = `journey-test-${Date.now()}`;
      await createTestProject(
        page,
        projectName,
        'Journey test project created to test full E2E workflow'
      );

      // Assert on project dashboard
      await expect(page).toHaveURL(/\/projects\/\d+/);
      await expect(page.getByTestId('dashboard-header')).toBeVisible();

      // Step 3: Discovery starts automatically (via start endpoint in createTestProject)
      await expect(page.getByTestId('discovery-question')).toBeVisible({ timeout: 15000 });

      // Step 4: Answer 2-3 discovery questions
      const numberOfQuestions = 3;
      for (let i = 0; i < numberOfQuestions; i++) {
        // Check if we still have questions to answer
        const questionLocator = page.getByTestId('discovery-question');
        const questionCount = await questionLocator.count();

        if (questionCount === 0 || !(await questionLocator.isVisible())) {
          // Discovery complete or no more questions
          break;
        }

        // Answer the current question with meaningful content
        const answer = `This is a detailed answer to question ${i + 1}.
The project aims to provide a comprehensive solution for automated software development.
Key features include AI-driven code generation, intelligent task planning, and continuous integration.
The target users are software development teams looking to accelerate their development cycles.`;

        await answerDiscoveryQuestion(page, answer);

        // Wait for processing and next question
        await page.waitForTimeout(3000);
      }

      // Step 5: Wait for PRD generation (indicated by View PRD button becoming visible)
      await expect(page.getByTestId('prd-generated')).toBeVisible({ timeout: 15000 });

      // Step 6: Verify agents are running (agent status panel should be visible)
      await expect(page.getByTestId('agent-status-panel')).toBeVisible({ timeout: 10000 });

      // Step 7: Verify dashboard panels are accessible

      // Check metrics panel (may be on a different tab now)
      const metricsTab = page.locator('[data-testid="metrics-tab"]');
      const metricsTabCount = await metricsTab.count();
      if (metricsTabCount > 0 && await metricsTab.isVisible()) {
        await metricsTab.click();
        await expect(page.getByTestId('metrics-panel')).toBeVisible({ timeout: 5000 });
      }

      // Navigate to Tasks tab for review findings
      const tasksTab = page.locator('[data-testid="tasks-tab"]');
      await tasksTab.click();
      await expect(page.locator('[data-testid="review-findings-panel"]')).toBeAttached({ timeout: 5000 });

      // Click on Checkpoints tab
      const checkpointTab = page.locator('[data-testid="checkpoint-tab"]');
      const checkpointTabCount = await checkpointTab.count();
      if (checkpointTabCount > 0 && await checkpointTab.isVisible()) {
        await checkpointTab.click();
        await expect(page.getByTestId('checkpoint-panel')).toBeAttached({ timeout: 10000 });
      }

      // Return to overview tab
      const overviewTab = page.locator('[data-testid="overview-tab"]');
      const overviewTabCount = await overviewTab.count();
      if (overviewTabCount > 0 && await overviewTab.isVisible()) {
        await overviewTab.click();
      }

      // Final verification: Project is in a healthy state
      // Check that dashboard header still shows project name
      await expect(page.locator('h1')).toContainText(projectName);

      // Verify connection status indicator
      const headerElement = page.getByTestId('dashboard-header');
      await expect(headerElement).toBeVisible();
    }
  );
});
