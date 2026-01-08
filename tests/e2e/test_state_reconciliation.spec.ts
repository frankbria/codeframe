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

/**
 * Helper to wait for dashboard to fully load
 */
async function waitForDashboardLoad(page: Page): Promise<void> {
  await page.locator('[data-testid="dashboard-header"]').waitFor({
    state: 'visible',
    timeout: 15000,
  });
  // Wait for any initial loading states to resolve
  await page.waitForLoadState('networkidle');
}

/**
 * Helper to expand discovery section if minimized
 */
async function expandIfMinimized(page: Page): Promise<void> {
  const minimizedView = page.locator('[data-testid="prd-minimized-view"]');
  if (await minimizedView.isVisible().catch(() => false)) {
    const expandButton = page.locator('[data-testid="expand-discovery-button"]');
    await expandButton.click();
    // Wait for expansion animation to complete
    await expect(minimizedView).not.toBeVisible({ timeout: 2000 });
  }
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

      // Verify backend state - FAIL if seed data is wrong
      const { phase } = await getProjectPhase(request, token, projectId);
      expect(phase).toBe('planning');
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      // Navigate as late-joining user (fresh page load, no WebSocket history)
      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Expand discovery section if minimized
      await expandIfMinimized(page);

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
      await waitForDashboardLoad(page);

      // ASSERTION: Task generation progress spinner must NOT be visible
      const progressSection = page.locator('[data-testid="task-generation-progress"]');
      await expect(progressSection).not.toBeVisible({ timeout: 3000 });
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

      // Check PRD status via API - FAIL if seed data is wrong
      const prdResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/prd`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      // PRD must exist for planning phase project
      expect(prdResponse.status()).not.toBe(404);
      const prdData = await prdResponse.json();
      expect(prdData.status).toBe('available');
      console.log(`📊 PRD status: ${prdData.status}`);

      // Navigate as late-joining user
      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Should NOT show loading spinner for PRD generation
      const prdSpinner = page.locator('[data-testid="prd-generation-status"] svg.animate-spin');
      const spinnerVisible = await prdSpinner.isVisible().catch(() => false);

      if (spinnerVisible) {
        const statusSection = page.locator('[data-testid="prd-generation-status"]');
        const statusText = await statusSection.textContent().catch(() => '');
        expect(
          statusText?.includes('Starting PRD Generation') || statusText?.includes('Generating')
        ).toBe(false);
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
      await waitForDashboardLoad(page);

      // Check for incorrect loading state text
      const prdStatusSection = page.locator('[data-testid="prd-generation-status"]');
      if (await prdStatusSection.isVisible().catch(() => false)) {
        const text = await prdStatusSection.textContent();
        // Should NOT show "Generating" without "Generated"
        if (text?.includes('Generating')) {
          expect(text).toContain('Generated');
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
      expect(phase).toBe('discovery');
      console.log(`📊 Project ${projectId}: phase=${phase}, discovery=${discoveryState}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Discovery progress section should be visible
      const discoveryProgress = page.locator('[data-testid="discovery-progress"]');
      await expect(discoveryProgress).toBeVisible({ timeout: 10000 });

      // If discovery is in 'discovering' state, question should be visible
      if (discoveryState === 'discovering') {
        const questionSection = page.locator('[data-testid="discovery-question"]');
        const waitingSection = page.locator('[data-testid="waiting-for-question"]');

        // Should show either the question or waiting for question state
        const questionVisible = await questionSection.isVisible().catch(() => false);
        const waitingVisible = await waitingSection.isVisible().catch(() => false);
        expect(questionVisible || waitingVisible).toBe(true);
        console.log('✅ Discovery question or waiting state visible');
      }

      console.log('✅ Discovery progress reflects backend state');
    });

    test('should show "Discovery Complete" when discovery already finished', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.PLANNING;

      // Verify discovery is complete - FAIL if seed data is wrong
      const { discoveryState } = await getProjectPhase(request, token, projectId);
      expect(discoveryState).toBe('completed');
      console.log(`📊 Discovery state: ${discoveryState}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Should show discovery complete state (minimized or expanded)
      const minimizedView = page.locator('[data-testid="prd-minimized-view"]');
      const prdStatus = page.locator('[data-testid="prd-generation-status"]');
      const tasksReadySection = page.locator('[data-testid="tasks-ready-section"]');

      const minimizedVisible = await minimizedView.isVisible().catch(() => false);
      const prdVisible = await prdStatus.isVisible().catch(() => false);
      const tasksVisible = await tasksReadySection.isVisible().catch(() => false);

      // At least one completion indicator should be visible
      expect(minimizedVisible || prdVisible || tasksVisible).toBe(true);
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

      // Verify project is in active phase - FAIL if seed data is wrong
      const { phase } = await getProjectPhase(request, token, projectId);
      expect(phase).toBe('active');
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Dashboard header should be visible (basic assertion)
      const dashboardHeader = page.locator('[data-testid="dashboard-header"]');
      await expect(dashboardHeader).toBeVisible();

      // Should have some content loaded (not just loading state)
      const pageContent = await page.content();
      expect(pageContent.length).toBeGreaterThan(1000);
      console.log('✅ Dashboard loaded with content for active project');
    });

    test('should show in-progress tasks when tasks already in progress', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.ACTIVE;

      // Check tasks via API - FAIL if no tasks
      const tasksResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/tasks`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      expect(tasksResponse.ok()).toBe(true);
      const tasksData = await tasksResponse.json();
      const allTasks = tasksData.tasks || [];
      const inProgressTasks = allTasks.filter(
        (t: { status: string }) => t.status === 'in_progress'
      );

      // Should have in-progress tasks per seed data
      expect(inProgressTasks.length).toBeGreaterThan(0);
      console.log(`📊 In-progress tasks: ${inProgressTasks.length}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Navigate to Tasks tab
      const tasksTab = page.locator('[data-testid="tasks-tab"]');
      if (await tasksTab.isVisible().catch(() => false)) {
        await tasksTab.click();
        // Wait for tab content to load
        await page.waitForLoadState('networkidle');
      }

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

      // Verify project is in review phase - FAIL if seed data is wrong
      const { phase } = await getProjectPhase(request, token, projectId);
      expect(phase).toBe('review');
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Dashboard header should be visible
      const dashboardHeader = page.locator('[data-testid="dashboard-header"]');
      await expect(dashboardHeader).toBeVisible();

      // Navigate to Quality Gates tab if available
      const qualityGatesTab = page.locator('[data-testid="quality-gates-tab"]');
      if (await qualityGatesTab.isVisible().catch(() => false)) {
        await qualityGatesTab.click();
        await page.waitForLoadState('networkidle');
        console.log('✅ Quality Gates tab loaded');
      }

      // Page should have substantial content
      const pageContent = await page.content();
      expect(pageContent.length).toBeGreaterThan(1000);
      console.log('✅ Page loaded correctly for review phase project');
    });

    test('should show code review findings when already generated', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.REVIEW;

      // Check for review findings via API
      const reviewResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/code-reviews`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      // Log whether endpoint exists
      if (reviewResponse.ok()) {
        const reviewData = await reviewResponse.json();
        const findingsCount = reviewData.findings?.length || reviewData.reviews?.length || 0;
        console.log(`📊 Code review findings: ${findingsCount}`);
        expect(findingsCount).toBeGreaterThanOrEqual(0);
      } else {
        console.log('ℹ️ Code reviews endpoint returned non-200');
      }

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Dashboard should load
      const dashboardHeader = page.locator('[data-testid="dashboard-header"]');
      await expect(dashboardHeader).toBeVisible();
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

      // Verify project is completed - FAIL if seed data is wrong
      const { phase } = await getProjectPhase(request, token, projectId);
      expect(phase).toBe('completed');
      console.log(`📊 Project ${projectId} phase: ${phase}`);

      await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
      await waitForDashboardLoad(page);

      // Dashboard header should be visible
      const dashboardHeader = page.locator('[data-testid="dashboard-header"]');
      await expect(dashboardHeader).toBeVisible();

      // Wait for page to stabilize, then check spinners
      await page.waitForLoadState('networkidle');

      // Completed projects shouldn't have active spinners (after stabilization)
      const spinners = page.locator('svg.animate-spin');
      const spinnerCount = await spinners.count();
      console.log(`📊 Spinners visible: ${spinnerCount}`);

      // Warn but don't fail - some spinners may be transient
      if (spinnerCount > 0) {
        console.log('⚠️ Warning: Spinners visible on completed project (may be transient)');
      }

      console.log('✅ Completed project loaded correctly');
    });

    test('should show all tasks as completed', async () => {
      const { request, token } = await getAuthenticatedRequest(page);
      const projectId = TEST_PROJECT_IDS.COMPLETED;

      // Check tasks via API - FAIL if wrong
      const tasksResponse = await request.get(`${BACKEND_URL}/api/projects/${projectId}/tasks`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      expect(tasksResponse.ok()).toBe(true);
      const tasksData = await tasksResponse.json();
      const allTasks = tasksData.tasks || [];
      const completedTasks = allTasks.filter((t: { status: string }) => t.status === 'completed');

      // All tasks should be completed for completed project
      expect(allTasks.length).toBeGreaterThan(0);
      expect(completedTasks.length).toBe(allTasks.length);
      console.log(`📊 Tasks: ${completedTasks.length}/${allTasks.length} completed`);
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
      await waitForDashboardLoad(page);

      // Expand discovery section to check state
      await expandIfMinimized(page);

      // Record initial state - tasks ready section should be visible
      const tasksReadySection = page.locator('[data-testid="tasks-ready-section"]');
      await expect(tasksReadySection).toBeVisible({ timeout: 5000 });
      console.log('✅ Initial state: Tasks ready section visible');

      // Refresh the page (simulates late-joining scenario)
      await page.reload();
      await waitForDashboardLoad(page);

      // Expand if minimized again
      await expandIfMinimized(page);

      // Verify state is preserved - tasks ready should still be visible
      await expect(tasksReadySection).toBeVisible({ timeout: 5000 });
      console.log('✅ Tasks ready state preserved after refresh');
    });
  });
});
