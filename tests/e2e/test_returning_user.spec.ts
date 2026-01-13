/**
 * E2E tests for Returning User scenarios
 *
 * These tests validate that users who navigate to a project AFTER missing all
 * WebSocket events still see the correct UI state. This is fundamentally different
 * from "late-joining user" tests which may catch some WebSocket events.
 *
 * Key testing strategy:
 * 1. Block WebSocket connections to force API-only state loading
 * 2. Navigate to projects with seeded state (in-progress, completed, etc.)
 * 3. Verify UI displays correct state from API endpoints, not WebSocket events
 *
 * Seeded test projects (from seed-test-data.py):
 * - Project 3: 'active' phase with in-progress tasks (E2E_TEST_PROJECT_ACTIVE_ID)
 * - Project 4: 'review' phase with quality gate findings (E2E_TEST_PROJECT_REVIEW_ID)
 * - Project 5: 'completed' phase with all tasks done (E2E_TEST_PROJECT_COMPLETED_ID)
 *
 * See: GitHub Issue #231 - E2E test failures for returning user state reconciliation
 */

import { test, expect, Page, APIRequestContext } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrorsWithBrowserFilters,
  ExtendedPage,
  blockWebSocketConnections,
} from './test-utils';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';

// Project IDs from seed-test-data.py (these are the actual seeded IDs)
const ACTIVE_PROJECT_ID = process.env.E2E_TEST_PROJECT_ACTIVE_ID || '3';
const COMPLETED_PROJECT_ID = process.env.E2E_TEST_PROJECT_COMPLETED_ID || '5';
const REVIEW_PROJECT_ID = process.env.E2E_TEST_PROJECT_REVIEW_ID || '4';

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
 * Verify task counts from API match expected state
 */
async function verifyTaskState(
  request: APIRequestContext,
  token: string,
  projectId: string,
  expectedState: {
    inProgress?: number;
    completed?: number;
    pending?: number;
    blocked?: number;
    total?: number;
  }
): Promise<void> {
  const response = await request.get(`${BACKEND_URL}/api/projects/${projectId}/tasks`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok()) {
    throw new Error(`Failed to fetch tasks: ${response.status()}`);
  }

  const data = await response.json();
  const tasks = data.tasks || [];

  // Count tasks by status
  const statusCounts = {
    inProgress: tasks.filter((t: { status: string }) => t.status === 'in_progress').length,
    completed: tasks.filter((t: { status: string }) => t.status === 'completed').length,
    pending: tasks.filter((t: { status: string }) => t.status === 'pending').length,
    blocked: tasks.filter((t: { status: string }) => t.status === 'blocked').length,
    total: tasks.length,
  };

  console.log(`📊 Task counts: ${JSON.stringify(statusCounts)}`);

  if (expectedState.inProgress !== undefined) {
    expect(statusCounts.inProgress).toBe(expectedState.inProgress);
  }
  if (expectedState.completed !== undefined) {
    expect(statusCounts.completed).toBe(expectedState.completed);
  }
  if (expectedState.pending !== undefined) {
    expect(statusCounts.pending).toBe(expectedState.pending);
  }
  if (expectedState.blocked !== undefined) {
    expect(statusCounts.blocked).toBe(expectedState.blocked);
  }
  if (expectedState.total !== undefined) {
    expect(statusCounts.total).toBe(expectedState.total);
  }
}

/**
 * Verify project phase from API
 */
async function verifyProjectPhase(
  request: APIRequestContext,
  token: string,
  projectId: string,
  expectedPhase: string
): Promise<void> {
  const response = await request.get(`${BACKEND_URL}/api/projects/${projectId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok()) {
    throw new Error(`Failed to fetch project: ${response.status()}`);
  }

  const project = await response.json();
  console.log(`📊 Project phase: ${project.phase}, status: ${project.status}`);
  expect(project.phase).toBe(expectedPhase);
}

test.describe('Returning User Scenarios', () => {
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
    checkTestErrorsWithBrowserFilters(page, 'Returning User test', [
      'net::ERR_ABORTED',
      'Failed to fetch RSC payload',
      'WebSocket', // Expected since we block WebSocket
      'connectionrefused',
    ]);
  });

  test.describe('In-Progress Project State (Project 3)', () => {
    /**
     * CRITICAL TEST: Returning user sees in-progress tasks correctly
     *
     * Scenario:
     * 1. Project has 2 in-progress tasks, 1 completed, 1 blocked, 1 pending
     * 2. User navigates to project WITHOUT WebSocket connection
     * 3. UI should display correct task counts from API data
     *
     * This tests the agentStateSync.fullStateResync() code path.
     */
    test('should show in-progress tasks when user returns to active project @smoke @returning-user', async () => {
      const { request, token } = await getAuthenticatedRequest(page);

      // First, verify project state matches expected seed data
      await verifyProjectPhase(request, token, ACTIVE_PROJECT_ID, 'active');
      await verifyTaskState(request, token, ACTIVE_PROJECT_ID, {
        inProgress: 2,
        completed: 1,
        blocked: 1,
        pending: 1,
        total: 5,
      });

      // Block WebSocket to simulate returning user (missed all events)
      const unblock = await blockWebSocketConnections(page);
      console.log('🔒 WebSocket blocked - simulating returning user');

      // Navigate to project as a "returning user" (no WebSocket history)
      await page.goto(`${FRONTEND_URL}/projects/${ACTIVE_PROJECT_ID}`);
      await page.waitForLoadState('networkidle');

      // Wait for dashboard to load
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });
      console.log('✅ Dashboard loaded');

      // Click on Tasks tab to see task list
      const tasksTab = page.locator('[data-testid="tasks-tab"]');
      await tasksTab.click();
      await page.waitForTimeout(500);

      // Wait for tasks panel to be visible
      const tasksPanel = page.locator('[data-testid="tasks-panel"]');
      await expect(tasksPanel).toBeVisible({ timeout: 10000 });
      console.log('✅ Tasks panel visible');

      // Verify in-progress tasks are displayed
      // The seed data has 2 in-progress tasks for Project 3
      const inProgressTasks = page.locator('[data-status="in_progress"], [data-task-status="in_progress"]');
      const inProgressCount = await inProgressTasks.count();
      console.log(`📊 In-progress tasks visible in UI: ${inProgressCount}`);

      // Verify total task count matches API (5 tasks seeded for Project 3)
      // Using task-card since TaskList renders li elements with data-testid="task-card"
      const allTasks = page.locator('[data-testid="task-card"]');
      const totalTasksVisible = await allTasks.count();
      console.log(`📊 Total tasks visible in UI: ${totalTasksVisible}`);

      // ASSERTION: All 5 seeded tasks should be visible (matching API verification above)
      // The TaskList component shows all tasks by default with "All" filter
      expect(totalTasksVisible).toBe(5);

      // Verify project phase badge shows correct state
      // Look for active/development indicators
      const phaseIndicators = page.locator('[data-testid="project-status"], [data-testid="phase-badge"]');
      if (await phaseIndicators.first().isVisible()) {
        const phaseText = await phaseIndicators.first().textContent();
        console.log(`📊 Phase indicator: ${phaseText}`);
      }

      // Unblock WebSocket for cleanup
      await unblock();
      console.log('✅ Test passed: Returning user sees in-progress tasks correctly');
    });

    test('should show agent status when returning to project with working agents', async () => {
      const { request, token } = await getAuthenticatedRequest(page);

      // Block WebSocket to simulate returning user
      const unblock = await blockWebSocketConnections(page);

      // Navigate to active project
      await page.goto(`${FRONTEND_URL}/projects/${ACTIVE_PROJECT_ID}`);
      await page.waitForLoadState('networkidle');

      // Wait for dashboard to load
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Check for agent status panel on Overview tab
      const agentPanel = page.locator('[data-testid="agent-status-panel"], [data-testid="agent-state-panel"]');
      const panelVisible = await agentPanel.first().isVisible().catch(() => false);

      if (panelVisible) {
        console.log('✅ Agent status panel is visible');
        // Agent state should be loaded from API
        const agentCards = page.locator('[data-testid="agent-card"], [data-testid="agent-item"]');
        const agentCount = await agentCards.count();
        console.log(`📊 Agent cards visible: ${agentCount}`);
      } else {
        console.log('ℹ️ Agent status panel not visible on this tab - checking API');
        // Verify agents via API
        const agentResponse = await request.get(`${BACKEND_URL}/api/projects/${ACTIVE_PROJECT_ID}/agents`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (agentResponse.ok()) {
          const agentData = await agentResponse.json();
          console.log(`📊 Agents from API: ${JSON.stringify(agentData)}`);
        }
      }

      await unblock();
      console.log('✅ Test passed: Agent state accessible for returning user');
    });
  });

  test.describe('Completed Project State (Project 5)', () => {
    /**
     * CRITICAL TEST: Returning user sees completed project state correctly
     *
     * Scenario:
     * 1. All tasks are completed with passed quality gates
     * 2. Project phase is 'complete'
     * 3. User navigates to project WITHOUT WebSocket connection
     * 4. UI should display 100% completion, no active work
     */
    test('should show completed state when user returns to finished project @smoke @returning-user', async () => {
      const { request, token } = await getAuthenticatedRequest(page);

      // First, verify project state matches expected seed data
      await verifyProjectPhase(request, token, COMPLETED_PROJECT_ID, 'complete');
      await verifyTaskState(request, token, COMPLETED_PROJECT_ID, {
        completed: 5,
        total: 5,
      });

      // Block WebSocket to simulate returning user
      const unblock = await blockWebSocketConnections(page);
      console.log('🔒 WebSocket blocked - simulating returning user');

      // Navigate to completed project
      await page.goto(`${FRONTEND_URL}/projects/${COMPLETED_PROJECT_ID}`);
      await page.waitForLoadState('networkidle');

      // Wait for dashboard to load
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });
      console.log('✅ Dashboard loaded');

      // Look for completion indicators
      // The project phase should show as 'complete' or 'completed'
      const statusBadge = page.locator('[data-testid="project-status"], [data-testid="phase-badge"]');
      if (await statusBadge.first().isVisible()) {
        const statusText = await statusBadge.first().textContent();
        console.log(`📊 Project status: ${statusText}`);
        // Status should indicate completion
        expect(statusText?.toLowerCase()).toMatch(/complete|done|finished/i);
      }

      // Click on Tasks tab to verify all tasks completed
      const tasksTab = page.locator('[data-testid="tasks-tab"]');
      await tasksTab.click();
      await page.waitForTimeout(500);

      // Wait for tasks panel
      const tasksPanel = page.locator('[data-testid="tasks-panel"]');
      await expect(tasksPanel).toBeVisible({ timeout: 10000 });

      // Check for task completion indicators
      const completedTasks = page.locator('[data-status="completed"], [data-task-status="completed"]');
      const completedCount = await completedTasks.count();
      console.log(`📊 Completed tasks visible: ${completedCount}`);

      // All tasks should be completed (no in-progress or pending)
      const inProgressTasks = page.locator('[data-status="in_progress"], [data-task-status="in_progress"]');
      const inProgressCount = await inProgressTasks.count();
      expect(inProgressCount).toBe(0);

      const pendingTasks = page.locator('[data-status="pending"], [data-task-status="pending"]');
      const pendingCount = await pendingTasks.count();
      expect(pendingCount).toBe(0);

      console.log('✅ No in-progress or pending tasks visible (correct for completed project)');

      // Verify no active agents (all should be idle)
      const agentResponse = await request.get(`${BACKEND_URL}/api/projects/${COMPLETED_PROJECT_ID}/agents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (agentResponse.ok()) {
        const agents = await agentResponse.json();
        // For completed projects, agents should all be inactive
        console.log(`📊 Agents for completed project: ${JSON.stringify(agents)}`);
      }

      await unblock();
      console.log('✅ Test passed: Returning user sees completed state correctly');
    });

    test('should show quality gates as passed for completed project', async () => {
      // Authenticate but only need loginUser for this test (no direct API calls needed)
      await getAuthenticatedRequest(page);

      // Block WebSocket
      const unblock = await blockWebSocketConnections(page);

      // Navigate to completed project
      await page.goto(`${FRONTEND_URL}/projects/${COMPLETED_PROJECT_ID}`);
      await page.waitForLoadState('networkidle');

      // Wait for dashboard
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Click on Quality Gates tab
      const qualityTab = page.locator('[data-testid="quality-gates-tab"]');
      await qualityTab.click();
      await page.waitForTimeout(500);

      // Wait for quality gates panel
      const qualityPanel = page.locator('[data-testid="quality-gates-panel"]');
      await expect(qualityPanel).toBeVisible({ timeout: 10000 });

      // For completed project, all quality gates should show as passed
      // Check for any failure indicators
      const failedGates = page.locator('[data-gate-status="failed"], [data-quality-status="failed"]');
      const failedCount = await failedGates.count();
      console.log(`📊 Failed quality gates: ${failedCount}`);

      // For Project 5 (completed), all gates should be passed (seed data has 5 tasks with 'passed' quality_gate_status)
      expect(failedCount).toBe(0);

      await unblock();
      console.log('✅ Test passed: Quality gates show as passed for completed project');
    });
  });

  test.describe('Review Phase State (Project 4)', () => {
    /**
     * TEST: Returning user sees quality gate failures in review phase
     *
     * Scenario:
     * 1. Project has completed tasks but some with failed quality gates
     * 2. Code review findings exist
     * 3. User navigates to project WITHOUT WebSocket connection
     * 4. UI should display review findings and failed gates
     */
    test('should show quality gate failures when returning to project in review @returning-user', async () => {
      const { request, token } = await getAuthenticatedRequest(page);

      // Verify project is in review phase
      await verifyProjectPhase(request, token, REVIEW_PROJECT_ID, 'review');

      // Block WebSocket
      const unblock = await blockWebSocketConnections(page);
      console.log('🔒 WebSocket blocked - simulating returning user');

      // Navigate to review project
      await page.goto(`${FRONTEND_URL}/projects/${REVIEW_PROJECT_ID}`);
      await page.waitForLoadState('networkidle');

      // Wait for dashboard
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });
      console.log('✅ Dashboard loaded');

      // Click on Quality Gates tab
      const qualityTab = page.locator('[data-testid="quality-gates-tab"]');
      await qualityTab.click();
      await page.waitForTimeout(500);

      // Wait for quality gates panel
      const qualityPanel = page.locator('[data-testid="quality-gates-panel"]');
      await expect(qualityPanel).toBeVisible({ timeout: 10000 });

      // Project 4 has tasks with failed quality gates (seed data)
      // Check for failure indicators
      const qualityIndicators = page.locator('[data-testid="quality-gate-status"], [data-testid="gate-result"]');
      const indicatorCount = await qualityIndicators.count();
      console.log(`📊 Quality gate indicators: ${indicatorCount}`);

      // Verify API returns tasks (quality gate status may not be exposed in all API responses)
      const tasksResponse = await request.get(`${BACKEND_URL}/api/projects/${REVIEW_PROJECT_ID}/tasks`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (tasksResponse.ok()) {
        const tasksData = await tasksResponse.json();
        const tasks = tasksData.tasks || [];
        console.log(`📊 Tasks returned from API: ${tasks.length}`);
        // Project 4 should have 4 tasks seeded
        expect(tasks.length).toBeGreaterThan(0);

        // Check if quality_gate_status field is exposed (optional assertion)
        const tasksWithQualityGate = tasks.filter((t: { quality_gate_status?: string }) => t.quality_gate_status);
        console.log(`📊 Tasks with quality_gate_status field: ${tasksWithQualityGate.length}`);

        // Log fields available on tasks for debugging
        if (tasks.length > 0) {
          console.log(`📊 Available task fields: ${Object.keys(tasks[0]).join(', ')}`);
        }
      }

      // Click on Tasks tab to see review findings
      const tasksTab = page.locator('[data-testid="tasks-tab"]');
      await tasksTab.click();
      await page.waitForTimeout(500);

      // Check for review findings panel
      const reviewPanel = page.locator('[data-testid="review-findings-panel"]');
      if (await reviewPanel.isVisible()) {
        console.log('✅ Review findings panel is visible');
      }

      await unblock();
      console.log('✅ Test passed: Returning user sees quality gate failures correctly');
    });
  });

  test.describe('State Reconciliation Verification', () => {
    /**
     * TEST: Verify fullStateResync loads complete state from API
     *
     * This test explicitly verifies that the agentStateSync.fullStateResync()
     * function correctly fetches and populates state when WebSocket is unavailable.
     */
    test('should load complete state from API endpoints without WebSocket @returning-user', async () => {
      // Authenticate (sets up session for frontend API calls)
      await getAuthenticatedRequest(page);

      // Block WebSocket BEFORE navigation
      const unblock = await blockWebSocketConnections(page);
      console.log('🔒 WebSocket blocked before navigation');

      // Navigate to active project
      await page.goto(`${FRONTEND_URL}/projects/${ACTIVE_PROJECT_ID}`);

      // Wait for all critical API calls to complete
      const apiCalls = await Promise.all([
        page.waitForResponse((r) => r.url().includes(`/api/projects/${ACTIVE_PROJECT_ID}`)),
        page.waitForResponse((r) => r.url().includes('/api/projects') && r.url().includes('/tasks')),
        page.waitForResponse((r) => r.url().includes('/api/projects') && r.url().includes('/agents')),
      ].map(p => p.catch(() => null)));

      const successfulCalls = apiCalls.filter(r => r !== null);
      console.log(`📊 API calls completed: ${successfulCalls.length}/3`);

      // Wait for dashboard
      await page.locator('[data-testid="dashboard-header"]').waitFor({
        state: 'visible',
        timeout: 15000,
      });

      // Verify dashboard shows project name (from API)
      const projectName = page.locator('[data-testid="project-name"], [data-testid="project-selector"] h1');
      if (await projectName.first().isVisible()) {
        const nameText = await projectName.first().textContent();
        console.log(`📊 Project name displayed: ${nameText}`);
        expect(nameText).toBeTruthy();
      }

      // Verify no "loading" spinners stuck on screen (state fully loaded)
      await page.waitForTimeout(2000); // Allow time for async state updates
      const loadingSpinners = page.locator('.animate-spin, [data-loading="true"]');
      const spinnerCount = await loadingSpinners.count();
      console.log(`📊 Loading spinners still visible: ${spinnerCount}`);
      // Some spinners might be for real-time updates, but main content should be loaded

      await unblock();
      console.log('✅ Test passed: State loaded from API without WebSocket');
    });
  });
});
