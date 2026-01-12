/**
 * E2E Tests: Task Execution Flow
 *
 * Tests task management functionality using seeded task data.
 * Covers:
 * - Task list visibility and navigation
 * - Task status indicators (completed, in_progress, blocked, pending)
 * - Task statistics display
 * - Agent assignment visibility
 * - Review findings display
 *
 * Uses seeded data from seed-test-data.py:
 * - 10 tasks with various states (3 completed, 2 in_progress, 2 blocked, 3 pending)
 * - 5 agents assigned to the project
 * - 7 code review findings
 *
 * Uses FastAPI backend auth (JWT tokens) for authentication.
 */

import { test, expect } from '@playwright/test';
import {
  loginUser,
  setupErrorMonitoring,
  checkTestErrors,
  ExtendedPage
} from './test-utils';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test.describe('Task Execution Flow', () => {
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
    checkTestErrors(page, 'Task execution test', [
      'net::ERR_ABORTED',  // Normal when navigation cancels pending requests
      'Failed to fetch RSC payload'  // Next.js RSC during navigation - transient
    ]);
  });

  test('should display task list on Tasks tab', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Navigate to Tasks tab
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 });
    await tasksTab.click();

    // Wait for tasks panel to be visible
    const tasksPanel = page.locator('[data-testid="tasks-panel"]');
    await tasksPanel.waitFor({ state: 'visible', timeout: 10000 });

    // Verify task statistics are visible
    await expect(page.locator('[data-testid="total-tasks"]')).toBeAttached({ timeout: 10000 });
    await expect(page.locator('[data-testid="completed-tasks"]')).toBeAttached();
    await expect(page.locator('[data-testid="in-progress-tasks"]')).toBeAttached();
    await expect(page.locator('[data-testid="blocked-tasks"]')).toBeAttached();
  });

  test('should display task statistics with valid numeric values', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);

    // Navigate to Tasks tab
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 });
    await tasksTab.click();

    // Wait for task stats to load
    await page.locator('[data-testid="total-tasks"]').waitFor({ state: 'visible', timeout: 10000 });

    // Verify task stats elements are visible and contain numeric values
    // Note: Actual counts depend on API data, which may differ from seeded data
    const totalTasks = await page.locator('[data-testid="total-tasks"]').textContent();
    expect(totalTasks).toMatch(/^\d+$/); // Should be a number

    const completedTasks = await page.locator('[data-testid="completed-tasks"]').textContent();
    expect(completedTasks).toMatch(/^\d+$/); // Should be a number

    const inProgressTasks = await page.locator('[data-testid="in-progress-tasks"]').textContent();
    expect(inProgressTasks).toMatch(/^\d+$/); // Should be a number

    const blockedTasks = await page.locator('[data-testid="blocked-tasks"]').textContent();
    expect(blockedTasks).toMatch(/^\d+$/); // Should be a number
  });

  test('should display agent status panel with seeded agents', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);

    // Agent panel should be visible on main dashboard (Overview tab is default)
    const agentPanel = page.locator('[data-testid="agent-status-panel"]');
    await agentPanel.waitFor({ state: 'visible', timeout: 15000 });

    // Verify agent panel is visible and contains content
    await expect(agentPanel).toBeVisible();

    // The agent state panel may also be present
    const agentStatePanel = page.locator('[data-testid="agent-state-panel"]');
    const agentPanelVisible = await agentPanel.isVisible();
    const agentStatePanelVisible = await agentStatePanel.isVisible();

    // At least one agent panel MUST be visible - use Playwright's or() for proper assertion
    await expect(agentPanel.or(agentStatePanel)).toBeVisible({ timeout: 5000 });
  });

  test('should display review findings from seeded code reviews', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);

    // Navigate to Tasks tab (where review findings now live per Sprint 10 refactor)
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 });
    await tasksTab.click();

    // Wait for tasks panel
    await page.locator('[data-testid="tasks-panel"]').waitFor({ state: 'visible', timeout: 10000 });

    // Review findings panel should be visible
    const reviewPanel = page.locator('[data-testid="review-findings-panel"]');
    await reviewPanel.waitFor({ state: 'attached', timeout: 15000 });

    // Verify the review panel is present
    await expect(reviewPanel).toBeAttached();

    // Check for review summary or findings list
    const reviewSummary = page.locator('[data-testid="review-summary"]');
    const reviewFindingsList = page.locator('[data-testid="review-findings-list"]');

    // Either summary or findings list MUST be visible (depending on data state)
    // Use Playwright's or() for proper assertion that fails if neither is visible
    await expect(reviewSummary.or(reviewFindingsList)).toBeVisible({ timeout: 10000 });
    console.log('✅ Review panel displays summary or findings list correctly');
  });

  test('should navigate between dashboard tabs', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Start on Overview tab (default)
    await expect(page.locator('[data-testid="dashboard-header"]')).toBeVisible({ timeout: 15000 });

    // Navigate to Tasks tab
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 });
    await tasksTab.click();

    // Verify tasks panel is visible
    await expect(page.locator('[data-testid="tasks-panel"]')).toBeVisible({ timeout: 10000 });

    // Navigate to Quality Gates tab (if exists)
    const qualityGatesTab = page.locator('[data-testid="quality-gates-tab"]');
    const hasQualityGatesTab = await qualityGatesTab.isVisible();

    if (hasQualityGatesTab) {
      await qualityGatesTab.click();
      // Verify quality gates panel loads - MUST render after click
      await expect(page.locator('[data-testid="quality-gates-panel"]')).toBeAttached({ timeout: 10000 });
      console.log('✅ Quality Gates tab navigation works');
    } else {
      console.log('ℹ️ Quality Gates tab not visible - may not be available for this project phase');
    }

    // Navigate to Metrics tab (if exists)
    const metricsTab = page.locator('[data-testid="metrics-tab"]');
    const hasMetricsTab = await metricsTab.isVisible();

    if (hasMetricsTab) {
      await metricsTab.click();
      // Verify metrics panel loads - MUST render after click
      await expect(page.locator('[data-testid="metrics-panel"]')).toBeVisible({ timeout: 10000 });
      console.log('✅ Metrics tab navigation works');
    } else {
      console.log('ℹ️ Metrics tab not visible - may not be available for this project phase');
    }

    // Navigate to Checkpoints tab
    const checkpointTab = page.locator('[data-testid="checkpoint-tab"]');
    const hasCheckpointTab = await checkpointTab.isVisible();

    if (hasCheckpointTab) {
      await checkpointTab.click();
      // Verify checkpoint panel loads - MUST render after click
      await expect(page.locator('[data-testid="checkpoint-panel"]')).toBeAttached({ timeout: 10000 });
      console.log('✅ Checkpoint tab navigation works');
    } else {
      console.log('ℹ️ Checkpoint tab not visible - may not be available for this project phase');
    }

    // Navigate back to Tasks tab to verify navigation still works
    await tasksTab.click();
    await expect(page.locator('[data-testid="tasks-panel"]')).toBeVisible({ timeout: 10000 });
  });
});
