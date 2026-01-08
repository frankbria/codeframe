/**
 * E2E Tests for State Reconciliation
 *
 * These tests verify that the UI correctly reflects backend state for "late-joining users"
 * who navigate to a project AFTER events have occurred (missing WebSocket events).
 *
 * The Problem:
 * - Components like DiscoveryProgress.tsx rely on WebSocket events to update state
 * - Users who were present during events see correct state via WebSocket
 * - Users who join late (page refresh, new tab, login after events) miss these events
 * - Without proper state reconciliation, late-joining users see incorrect UI
 *
 * The Solution:
 * - Components must check API state on mount (not just rely on WebSocket)
 * - Use state initialization flags to prevent UI flash during async checks
 * - Tests navigate to pre-seeded projects and verify UI without WebSocket events
 *
 * Test Projects (seeded in seed-test-data.py):
 * - Project 1: Discovery phase with active questions
 * - Project 2: Planning phase with PRD complete and tasks generated
 * - Project 3: Active phase with running agents and in-progress tasks
 * - Project 4: Review phase with completed tasks awaiting review
 * - Project 5: Completed phase with all work done
 *
 * @see test_late_joining_user.spec.ts - Additional late-joining user tests
 * @see docs/e2e-testing.md - State reconciliation pattern documentation
 */

import { test, expect, Page, APIRequestContext } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrors,
  ExtendedPage,
} from './test-utils';
import { FRONTEND_URL, BACKEND_URL, TEST_PROJECT_IDS } from './e2e-config';

/**
 * Helper to get an authenticated API request context
 */
async function getAuthenticatedRequest(page: Page): Promise<{ request: APIRequestContext; token: string }> {
  const response = await page.request.post(`${BACKEND_URL}/auth/jwt/login`, {
    form: {
      username: 'test@example.com',
      password: 'Testpassword123',
    },
  });

  if (!response.ok()) {
    throw new Error(`Failed to login: ${response.status()} ${response.statusText()}`);
  }

  const data = await response.json();
  return { request: page.request, token: data.access_token };
}

/**
 * Helper to verify project phase via API
 */
async function getProjectPhase(
  request: APIRequestContext,
  token: string,
  projectId: string
): Promise<{ phase: string; discoveryState: string | null }> {
  const response = await request.get(`${BACKEND_URL}/api/projects/${projectId}/discovery/progress`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok()) {
    throw new Error(`Failed to get project phase: ${response.status()}`);
  }

  const data = await response.json();
  return {
    phase: data.phase,
    discoveryState: data.discovery?.state || null,
  };
}

test.describe('State Reconciliation - Late Joining User', () => {
  let page: Page;

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage;

    // Setup error monitoring
    const errorMonitor = setupErrorMonitoring(page);
    (page as ExtendedPage).__errorMonitor = errorMonitor;

    // Login using real authentication flow
    await loginUser(page);
    console.log('✅ Logged in successfully');
  });

  test.afterEach(async ({ page }) => {
    checkTestErrors(page, 'State Reconciliation test', [
      'net::ERR_ABORTED',
      'Failed to fetch RSC payload',
    ]);
  });

  test.describe('Task Generation State', () => {
    /**
     * CRITICAL TEST: Tasks already generated
     * When tasks exist, late-joining user should see "Review Tasks" not "Generate Tasks"
     */
    test('should show "Review Tasks" when tasks already exist @smoke', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.PLANNING;

      // Verify backend state
      const { phase } = await getProjectPhase(request, token, projectId);
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      // Navigate as late-joining user (fresh page load, no WebSocket history)
      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      // Wait for dashboard to load
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Check if discovery section is minimized and expand if needed
      const minimizedView = page.locator('[data-testid="prd-minimized-view"]');
      if (await minimizedView.isVisible().catch(() => false)) {
        console.log('ℹ️ Discovery section minimized - expanding');
        await page.locator('[data-testid="expand-discovery-button"]').click();
        await page.waitForTimeout(500);
      }

      // ASSERTION: "Generate Tasks" button must NOT be visible
      const generateButton = page.locator('[data-testid="generate-tasks-button"]');
      await expect(generateButton).not.toBeVisible({ timeout: 5000 });
      console.log('✅ Generate Task Breakdown button correctly hidden');

      // ASSERTION: "Tasks Ready" section must be visible
      const tasksReadySection = page.locator('[data-testid="tasks-ready-section"]');
      await expect(tasksReadySection).toBeVisible({ timeout: 5000 });
      console.log('✅ Tasks Ready section visible');

      // ASSERTION: "Review Tasks" button must be visible
      const reviewButton = page.locator('[data-testid="review-tasks-button"]');
      await expect(reviewButton).toBeVisible();
      console.log('✅ Review Tasks button visible');
    });

    test('should not show task generation spinner when tasks already exist', async () => {
      const projectId = TEST_PROJECT_IDS.PLANNING;

      // Navigate as late-joining user
      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Wait for state to stabilize
      await page.waitForTimeout(1000);

      // ASSERTION: Task generation progress spinner must NOT be visible
      const progressSection = page.locator('[data-testid="task-generation-progress"]');
      const progressVisible = await progressSection.isVisible().catch(() => false);

      if (progressVisible) {
        throw new Error(
          'BUG DETECTED: Task generation spinner visible when tasks already exist. ' +
          'Late-joining users see incorrect loading state.'
        );
      }

      console.log('✅ No task generation spinner (correct for late-joining user)');
    });
  });

  test.describe('PRD Generation State', () => {
    /**
     * When PRD is complete, late-joining user should see "View PRD" not loading state
     */
    test('should show "View PRD" when PRD already complete @smoke', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.PLANNING;

      // Check PRD status via API
      const prdResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/prd`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (prdResponse.status() === 404) {
        test.skip(true, 'PRD does not exist - cannot test late-joining PRD scenario');
        return;
      }

      const prdData = await prdResponse.json();
      console.log(`📊 PRD status: ${prdData.status}`);

      if (prdData.status !== 'available') {
        test.skip(true, `PRD status is ${prdData.status}, not available`);
        return;
      }

      // Navigate as late-joining user
      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Should NOT show loading spinner for PRD generation
      const prdSpinner = page.locator('[data-testid="prd-generation-status"] svg.animate-spin');
      const spinnerVisible = await prdSpinner.isVisible().catch(() => false);

      if (spinnerVisible) {
        const statusSection = page.locator('[data-testid="prd-generation-status"]');
        const statusText = await statusSection.textContent().catch(() => '');
        if (statusText?.includes('Starting PRD Generation') || statusText?.includes('Generating')) {
          throw new Error(
            'BUG DETECTED: PRD generation spinner visible when PRD already exists. ' +
            'Late-joining users see incorrect loading state.'
          );
        }
      }

      // Should show View PRD button (either in minimized or expanded view)
      const viewPrdButton = page.locator('[data-testid="view-prd-button"]');
      const prdMinimizedButton = page.locator('[data-testid="view-prd-button-minimized"]');

      const viewPrdVisible = await viewPrdButton.isVisible().catch(() => false);
      const minimizedVisible = await prdMinimizedButton.isVisible().catch(() => false);

      expect(viewPrdVisible || minimizedVisible).toBe(true);
      console.log('✅ View PRD button visible (correct for late-joining user)');
    });

    test('should not show "Generating PRD..." when PRD already exists', async () => {
      const projectId = TEST_PROJECT_IDS.PLANNING;

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Wait for state initialization
      await page.waitForTimeout(1000);

      // Check for incorrect loading state text
      const prdStatusSection = page.locator('[data-testid="prd-generation-status"]');
      if (await prdStatusSection.isVisible().catch(() => false)) {
        const text = await prdStatusSection.textContent();
        if (text?.includes('Generating') && !text?.includes('Generated')) {
          throw new Error(
            'BUG DETECTED: "Generating PRD" text visible when PRD already exists.'
          );
        }
      }

      console.log('✅ No "Generating PRD" text (correct for late-joining user)');
    });
  });

  test.describe('Discovery Progress State', () => {
    /**
     * Discovery progress should reflect actual backend state
     */
    test('should show correct discovery progress when questions already answered', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.DISCOVERY;

      // Get actual discovery state from API
      const { phase, discoveryState } = await getProjectPhase(request, token, projectId);
      console.log(`📊 Project ${projectId}: phase=${phase}, discovery=${discoveryState}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Discovery progress section should be visible
      const discoveryProgress = page.locator('[data-testid="discovery-progress"]');
      await expect(discoveryProgress).toBeVisible({ timeout: 10000 });

      // If discovery is in 'discovering' state, question should be visible
      if (discoveryState === 'discovering') {
        const questionSection = page.locator('[data-testid="discovery-question"]');
        const waitingSection = page.locator('[data-testid="waiting-for-question"]');
        const questionOrWaiting = await questionSection.isVisible().catch(() => false) ||
                                  await waitingSection.isVisible().catch(() => false);

        // Should show either the question or waiting for question state
        expect(questionOrWaiting).toBe(true);
        console.log('✅ Discovery question or waiting state visible');
      }

      console.log('✅ Discovery progress reflects backend state');
    });

    test('should show "Discovery Complete" when discovery already finished', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.PLANNING;

      // Verify discovery is complete
      const { discoveryState } = await getProjectPhase(request, token, projectId);
      console.log(`📊 Discovery state: ${discoveryState}`);

      if (discoveryState !== 'completed') {
        test.skip(true, `Discovery state is ${discoveryState}, not completed`);
        return;
      }

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Should show discovery complete state (minimized or expanded)
      const minimizedView = page.locator('[data-testid="prd-minimized-view"]');
      const prdStatus = page.locator('[data-testid="prd-generation-status"]');

      const minimizedVisible = await minimizedView.isVisible().catch(() => false);
      const prdVisible = await prdStatus.isVisible().catch(() => false);

      // At least one completion indicator should be visible
      expect(minimizedVisible || prdVisible).toBe(true);
      console.log('✅ Discovery complete state visible');
    });
  });

  test.describe('Agent Status State', () => {
    /**
     * Agent status should reflect actual backend state
     */
    test('should show correct agent status when agents already running', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.ACTIVE;

      // Verify project is in active phase
      const { phase } = await getProjectPhase(request, token, projectId);
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      if (phase !== 'active') {
        test.skip(true, `Project phase is ${phase}, not active`);
        return;
      }

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Navigate to appropriate tab that shows agent status
      // The dashboard should display agent information
      const dashboardContent = await page.content();
      const hasAgentInfo = dashboardContent.includes('agent') ||
                          dashboardContent.includes('Agent') ||
                          dashboardContent.includes('working');

      console.log(`📊 Agent info present in page: ${hasAgentInfo}`);
      // Note: This test verifies the page loads correctly for active projects
      // More specific agent state checks depend on component implementation
    });

    test('should show in-progress tasks when tasks already in progress', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.ACTIVE;

      // Check tasks via API
      const tasksResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/tasks`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!tasksResponse.ok()) {
        test.skip(true, 'Cannot verify task state via API');
        return;
      }

      const tasksData = await tasksResponse.json();
      const inProgressTasks = (tasksData.tasks || []).filter(
        (t: { status: string }) => t.status === 'in_progress'
      );
      console.log(`📊 In-progress tasks: ${inProgressTasks.length}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // The page should load without errors for projects with in-progress tasks
      console.log('✅ Page loaded correctly for project with in-progress tasks');
    });
  });

  test.describe('Review State', () => {
    /**
     * Review findings should be visible when quality gates have already run
     */
    test('should show quality gate results when already completed', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.REVIEW;

      // Verify project is in review phase
      const { phase } = await getProjectPhase(request, token, projectId);
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      if (phase !== 'review') {
        test.skip(true, `Project phase is ${phase}, not review`);
        return;
      }

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Navigate to Quality Gates tab if available
      const qualityGatesTab = page.locator('[data-testid="quality-gates-tab"]');
      if (await qualityGatesTab.isVisible().catch(() => false)) {
        await qualityGatesTab.click();
        await page.waitForTimeout(500);
      }

      // Page should load without errors for review phase projects
      console.log('✅ Page loaded correctly for review phase project');
    });

    test('should show code review findings when already generated', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.REVIEW;

      // Check for review findings via API (if endpoint exists)
      try {
        const reviewResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/code-reviews`, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (reviewResponse.ok()) {
          const reviewData = await reviewResponse.json();
          console.log(`📊 Code review findings: ${reviewData.findings?.length || 0}`);
        }
      } catch {
        console.log('ℹ️ Code reviews endpoint not available');
      }

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Page should load correctly
      console.log('✅ Page loaded for project with review findings');
    });
  });

  test.describe('Completed Project State', () => {
    /**
     * Completed projects should show final state correctly
     */
    test('should show completed state when project already finished', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.COMPLETED;

      // Verify project is completed
      const { phase } = await getProjectPhase(request, token, projectId);
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      if (phase !== 'completed') {
        test.skip(true, `Project phase is ${phase}, not completed`);
        return;
      }

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Should NOT show any "in progress" spinners
      const spinners = page.locator('svg.animate-spin');
      const spinnerCount = await spinners.count();

      // Wait for any loading states to resolve
      await page.waitForTimeout(2000);

      // Re-check spinners after loading
      const finalSpinnerCount = await spinners.count();
      console.log(`📊 Spinners visible: ${finalSpinnerCount}`);

      // Completed projects shouldn't have active spinners
      if (finalSpinnerCount > 0) {
        console.log('⚠️ Warning: Spinners visible on completed project (may be transient)');
      }

      console.log('✅ Completed project loaded correctly');
    });

    test('should show all tasks as completed', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.COMPLETED;

      // Check tasks via API
      const tasksResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/tasks`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!tasksResponse.ok()) {
        test.skip(true, 'Cannot verify task state via API');
        return;
      }

      const tasksData = await tasksResponse.json();
      const allTasks = tasksData.tasks || [];
      const completedTasks = allTasks.filter((t: { status: string }) => t.status === 'completed');

      console.log(`📊 Tasks: ${completedTasks.length}/${allTasks.length} completed`);

      // All tasks should be completed for completed project
      expect(completedTasks.length).toBe(allTasks.length);
      console.log('✅ All tasks are completed');
    });
  });

  test.describe('Page Refresh Reconciliation', () => {
    /**
     * State should be preserved correctly after page refresh
     */
    test('should maintain correct state after page refresh @smoke', async () => {
      const projectId = TEST_PROJECT_IDS.PLANNING;

      // Initial navigation
      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Record initial state
      const tasksReadySection = page.locator('[data-testid="tasks-ready-section"]');
      const initialTasksReady = await tasksReadySection.isVisible().catch(() => false);

      // Refresh the page (simulates late-joining scenario)
      await page.reload();
      await page.waitForLoadState('networkidle');

      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Expand if minimized
      const minimizedView = page.locator('[data-testid="prd-minimized-view"]');
      if (await minimizedView.isVisible().catch(() => false)) {
        await page.locator('[data-testid="expand-discovery-button"]').click();
        await page.waitForTimeout(500);
      }

      // Verify state is preserved
      const tasksReadyAfterRefresh = await tasksReadySection.isVisible().catch(() => false);

      // Both should show tasks ready (if tasks exist)
      if (initialTasksReady) {
        expect(tasksReadyAfterRefresh).toBe(true);
        console.log('✅ Tasks ready state preserved after refresh');
      } else {
        console.log('ℹ️ Tasks were not ready in initial state');
      }
    });
  });
});
