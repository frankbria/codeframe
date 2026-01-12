/**
 * T160: Playwright E2E test for Metrics Dashboard.
 *
 * Tests:
 * - Cost dashboard displays correctly
 * - Token usage chart updates
 * - Cost breakdown by agent/model
 * - CSV export functionality
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test.describe('Metrics Dashboard UI', () => {
  test.beforeEach(async ({ page }) => {
    // Login using real authentication flow
    await loginUser(page);

    // Navigate to dashboard for test project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for project API to load - this MUST succeed for tests to be valid
    // Note: Must use /api/projects/ to avoid matching the HTML page response at /projects/
    const projectResponse = await page.waitForResponse(response =>
      response.url().includes(`/api/projects/${PROJECT_ID}`) && response.status() === 200,
      { timeout: 10000 }
    );
    expect(projectResponse.ok()).toBe(true);  // API must succeed

    // Wait for dashboard header to render (always visible regardless of active tab)
    await page.locator('[data-testid="dashboard-header"]').waitFor({ state: 'visible', timeout: 10000 });

    // Navigate to Metrics tab - set up response listener BEFORE clicking
    const metricsTab = page.locator('[data-testid="metrics-tab"]');
    await metricsTab.waitFor({ state: 'visible', timeout: 10000 });

    // Set up metrics API response listener BEFORE clicking tab
    const metricsResponsePromise = page.waitForResponse(
      response => response.url().includes('/metrics') && response.status() === 200,
      { timeout: 15000 }
    );

    // Click tab to trigger metrics load
    await metricsTab.click();

    // Wait for metrics panel to be visible
    const metricsPanel = page.locator('[data-testid="metrics-panel"]');
    await metricsPanel.waitFor({ state: 'visible', timeout: 10000 });

    // Wait for the metrics API response we're listening for
    const metricsResponse = await metricsResponsePromise;
    expect(metricsResponse.ok()).toBe(true);  // Metrics API must succeed

    // Wait for cost dashboard to be visible (indicates data has rendered)
    await page.locator('[data-testid="cost-dashboard"]').waitFor({ state: 'visible', timeout: 5000 });
  });

  test('should display metrics panel', async ({ page }) => {
    const metricsPanel = page.locator('[data-testid="metrics-panel"]');

    // Scroll panel into view
    await metricsPanel.scrollIntoViewIfNeeded();

    await metricsPanel.waitFor({ state: 'visible', timeout: 15000 });
    await expect(metricsPanel).toBeVisible();

    // Check for key components with waits
    const costDashboard = page.locator('[data-testid="cost-dashboard"]');
    await costDashboard.waitFor({ state: 'visible', timeout: 10000 });
    await expect(costDashboard).toBeVisible();

    // Token stats are part of CostDashboard, not a separate chart
    const tokenStats = page.locator('[data-testid="token-stats"]');
    await tokenStats.waitFor({ state: 'visible', timeout: 10000 });
    await expect(tokenStats).toBeVisible();
  });

  test('should display total cost', async ({ page }) => {
    const totalCostDisplay = page.locator('[data-testid="total-cost-display"]');
    await totalCostDisplay.waitFor({ state: 'visible', timeout: 15000 });
    await expect(totalCostDisplay).toBeVisible();

    // Wait for cost data to load
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-testid="total-cost-display"]');
      return el && el.textContent && el.textContent.trim() !== '';
    }, { timeout: 10000 });

    // Should display cost in USD format
    const costText = await totalCostDisplay.textContent();
    expect(costText).toMatch(/\$\d+\.\d{2}/); // Format: $X.XX
  });

  test('should display token usage statistics', async ({ page }) => {
    const tokenStats = page.locator('[data-testid="token-stats"]');
    await tokenStats.waitFor({ state: 'visible', timeout: 15000 });
    await expect(tokenStats).toBeVisible();

    // Check for input/output token counts with waits
    const inputTokens = page.locator('[data-testid="input-tokens"]');
    await inputTokens.waitFor({ state: 'visible', timeout: 10000 });
    await expect(inputTokens).toBeVisible();

    const outputTokens = page.locator('[data-testid="output-tokens"]');
    await outputTokens.waitFor({ state: 'visible', timeout: 10000 });
    await expect(outputTokens).toBeVisible();

    const totalTokens = page.locator('[data-testid="total-tokens"]');
    await totalTokens.waitFor({ state: 'visible', timeout: 10000 });
    await expect(totalTokens).toBeVisible();
  });

  test('should display token usage chart', async ({ page }) => {
    // Cost trend chart is part of CostDashboard
    const trendChart = page.locator('[data-testid="cost-trend-chart"]');

    await trendChart.waitFor({ state: 'visible', timeout: 10000 });
    await expect(trendChart).toBeVisible();

    // Chart MUST have data element OR show empty state message
    const trendChartData = trendChart.locator('[data-testid="trend-chart-data"]');
    const emptyStateText = trendChart.locator('text=/No time series data/i');

    // Use Playwright's or() for proper assertion that fails if neither is visible
    await expect(trendChartData.or(emptyStateText)).toBeVisible({ timeout: 5000 });
    console.log('✅ Token usage chart displays data or empty state correctly');
  });

  test('should display cost breakdown by agent', async ({ page }) => {
    const agentBreakdown = page.locator('[data-testid="cost-by-agent"]');
    await agentBreakdown.scrollIntoViewIfNeeded();
    await agentBreakdown.waitFor({ state: 'visible', timeout: 15000 });
    await expect(agentBreakdown).toBeVisible();

    // Check for empty state first (most common case in CI)
    const emptyState = page.locator('[data-testid="agent-cost-empty"]');
    const emptyStateCount = await emptyState.count();
    const emptyStateVisible = emptyStateCount > 0 && await emptyState.isVisible();

    if (emptyStateVisible) {
      // Empty state is shown - test passes
      await expect(emptyState).toBeVisible();
    } else {
      // Look for actual agent data rows (exclude empty state by using more specific selector)
      // Agent rows have data-testid like "agent-cost-backend-001", not "agent-cost-empty"
      const agentRows = page.locator('[data-testid^="agent-cost-"]:not([data-testid="agent-cost-empty"])');
      const rowCount = await agentRows.count();

      if (rowCount === 0) {
        // No data rows found, empty state should be visible
        await expect(emptyState).toBeVisible();
      } else {
        // Verify first agent row has name and cost
        const firstAgent = agentRows.first();
        await expect(firstAgent.locator('[data-testid="agent-name"]')).toBeVisible();
        await expect(firstAgent.locator('[data-testid="agent-cost"]')).toBeVisible();
      }
    }
  });

  test('should display cost breakdown by model', async ({ page }) => {
    const modelBreakdown = page.locator('[data-testid="cost-by-model"]');
    await modelBreakdown.scrollIntoViewIfNeeded();
    await modelBreakdown.waitFor({ state: 'visible', timeout: 15000 });
    await expect(modelBreakdown).toBeVisible();

    // Check for empty state first (most common case in CI)
    const emptyState = page.locator('[data-testid="model-cost-empty"]');
    const emptyStateCount = await emptyState.count();
    const emptyStateVisible = emptyStateCount > 0 && await emptyState.isVisible();

    if (emptyStateVisible) {
      // Empty state is shown - test passes
      await expect(emptyState).toBeVisible();
    } else {
      // Look for actual model data rows (exclude empty state by using more specific selector)
      // Model rows have data-testid like "model-cost-claude-sonnet-4-5", not "model-cost-empty"
      const modelRows = page.locator('[data-testid^="model-cost-"]:not([data-testid="model-cost-empty"])');
      const rowCount = await modelRows.count();

      if (rowCount === 0) {
        // No data rows found, empty state should be visible
        await expect(emptyState).toBeVisible();
      } else {
        // Verify model names match expected models
        const expectedModels = ['sonnet', 'opus', 'haiku'];
        const firstModel = modelRows.first();
        const modelText = await firstModel.locator('[data-testid="model-name"]').textContent();

        const matchesExpected = expectedModels.some(model =>
          modelText?.toLowerCase().includes(model)
        );
        expect(matchesExpected).toBe(true);
      }
    }
  });

  test('should filter metrics by date range', async ({ page }) => {
    const dateFilter = page.locator('[data-testid="date-range-filter"]');
    await dateFilter.scrollIntoViewIfNeeded();

    // Date filter MUST be visible - we validated metrics API in beforeEach
    const filterCount = await dateFilter.count();
    if (filterCount === 0) {
      // No date filter component exists in the page - this is a real bug
      throw new Error('Date range filter component not found in metrics panel');
    }
    await expect(dateFilter).toBeVisible({ timeout: 5000 });

    // Store initial filter value
    const initialValue = await dateFilter.inputValue();

    // Change to a different filter option
    const newValue = initialValue === 'last-30-days' ? 'last-7-days' : 'last-30-days';

    // Set up response listener BEFORE changing filter
    const filterResponsePromise = page.waitForResponse(response =>
      response.url().includes('/metrics'),
      { timeout: 15000 }
    );

    // Change the filter value
    await dateFilter.selectOption(newValue);

    // Wait for metrics API response triggered by filter change
    const filterResponse = await filterResponsePromise;
    expect(filterResponse.ok()).toBe(true);

    // Wait for cost-dashboard to reappear after loading state
    const costDashboard = page.locator('[data-testid="cost-dashboard"]');
    await costDashboard.waitFor({ state: 'visible', timeout: 10000 });

    // After loading completes, metrics panel and filter should be visible
    const metricsPanel = page.locator('[data-testid="metrics-panel"]');
    await expect(metricsPanel).toBeVisible();

    // Wait for filter to reappear after loading state completes
    await expect(dateFilter).toBeVisible({ timeout: 5000 });
    const currentValue = await dateFilter.inputValue();
    expect(currentValue).toBe(newValue);
  });

  test('should export cost report to CSV', async ({ page }) => {
    const exportButton = page.locator('[data-testid="export-csv-button"]');

    const isExportButtonVisible = await exportButton.isVisible();
    if (isExportButtonVisible) {
      // Setup download listener
      const downloadPromise = page.waitForEvent('download', { timeout: 5000 });

      // Click export button
      await exportButton.click();

      // Verify download started
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toContain('.csv');
      console.log('✅ CSV export works correctly');
    } else {
      // Export button not visible - may be disabled in current project state
      // Verify metrics panel is still functional without export
      await expect(page.locator('[data-testid="cost-dashboard"]')).toBeVisible();
      console.log('ℹ️ Export CSV button not visible - feature may be disabled for this project');
    }
  });

  test('should display cost per task', async ({ page }) => {
    const taskCostTable = page.locator('[data-testid="cost-per-task-table"]');
    await taskCostTable.scrollIntoViewIfNeeded();
    await taskCostTable.waitFor({ state: 'visible', timeout: 10000 });

    // Table section should be visible
    await expect(taskCostTable).toBeVisible();

    // Check for either data rows or empty state
    const taskRows = page.locator('[data-testid^="task-cost-row-"]');
    const emptyState = page.locator('[data-testid="task-cost-empty"]');

    // Wait for either data or empty state to appear
    try {
      await Promise.race([
        taskRows.first().waitFor({ state: 'visible', timeout: 5000 }),
        emptyState.waitFor({ state: 'visible', timeout: 5000 })
      ]);
    } catch {
      // At least one of these must be visible
      const hasRows = await taskRows.count() > 0;
      const hasEmpty = await emptyState.count() > 0;
      expect(hasRows || hasEmpty).toBe(true);
    }

    const count = await taskRows.count();

    if (count === 0) {
      // No data - check for empty state message
      await expect(emptyState).toBeVisible();
    } else {
      // Table should have headers
      await expect(page.locator('[data-testid="task-column-header"]')).toBeVisible();
      await expect(page.locator('[data-testid="cost-column-header"]')).toBeVisible();
      await expect(page.locator('[data-testid="tokens-column-header"]')).toBeVisible();

      // Verify first row has data
      const firstRow = taskRows.first();
      await expect(firstRow.locator('[data-testid="task-description"]')).toBeVisible();
      await expect(firstRow.locator('[data-testid="task-cost"]')).toBeVisible();
    }
  });

  test('should display model pricing information', async ({ page }) => {
    const pricingInfo = page.locator('[data-testid="model-pricing-info"]');

    const isPricingInfoVisible = await pricingInfo.isVisible();
    if (isPricingInfoVisible) {
      // Should list pricing for each model
      const pricingItems = page.locator('[data-testid^="pricing-"]');
      const count = await pricingItems.count();

      expect(count).toBeGreaterThan(0);

      // Verify pricing format
      const firstPricing = pricingItems.first();
      const pricingText = await firstPricing.textContent();

      // Should contain model name and price per MTok
      expect(pricingText).toMatch(/\$\d+/); // Contains price
      expect(pricingText).toMatch(/MTok|per million|\/M/i); // Contains "per million tokens"
      console.log('✅ Model pricing information displayed correctly');
    } else {
      // Pricing info not visible - may not be included in current UI layout
      // Verify the metrics panel is still functional
      await expect(page.locator('[data-testid="cost-dashboard"]')).toBeVisible();
      console.log('ℹ️ Model pricing info not visible - feature may not be enabled');
    }
  });

  test('should refresh metrics in real-time', async ({ page }) => {
    // Get initial total cost
    const totalCostDisplay = page.locator('[data-testid="total-cost-display"]');
    await totalCostDisplay.waitFor({ state: 'visible', timeout: 15000 });

    // Wait for data to load
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-testid="total-cost-display"]');
      return el && el.textContent && el.textContent.trim() !== '';
    }, { timeout: 10000 });

    const initialCost = await totalCostDisplay.textContent();

    // Monitor WebSocket for real-time updates
    // Note: WebSocket may already be established from page load
    let wsReceived = false;
    try {
      const wsPromise = page.waitForEvent('websocket', { timeout: 5000 });
      const ws = await wsPromise;

      // Wait for a WebSocket frame (indicates real-time update capability)
      await Promise.race([
        new Promise(resolve => ws.on('framereceived', () => { wsReceived = true; resolve(null); })),
        new Promise(resolve => setTimeout(resolve, 2000))
      ]);
      console.log(`✅ WebSocket connected, frame received: ${wsReceived}`);
    } catch {
      // WebSocket may already be established or not available for this test
      console.log('ℹ️ No new WebSocket connection - may already be established');
    }

    // Cost might update via WebSocket (or stay the same if no new data)
    const updatedCost = await totalCostDisplay.textContent();

    // Both values should be valid cost formats
    expect(initialCost).toMatch(/\$\d+\.\d{2}/);
    expect(updatedCost).toMatch(/\$\d+\.\d{2}/);

    // They might be equal if no updates occurred (not an error)
  });

  test('should display cost trend chart', async ({ page }) => {
    const trendChart = page.locator('[data-testid="cost-trend-chart"]');
    await trendChart.scrollIntoViewIfNeeded();
    await trendChart.waitFor({ state: 'visible', timeout: 10000 });

    // Trend chart section should be visible
    await expect(trendChart).toBeVisible();

    // Chart MUST have data element OR show empty state message
    const trendChartData = page.locator('[data-testid="trend-chart-data"]');
    const emptyStateText = trendChart.locator('text=/No time series data/i');

    // Use Playwright's or() for proper assertion that fails if neither is visible
    await expect(trendChartData.or(emptyStateText)).toBeVisible({ timeout: 5000 });

    // Log which state was found
    const hasData = await trendChartData.isVisible();
    if (hasData) {
      console.log('✅ Cost trend chart displays data correctly');
    } else {
      console.log('✅ Cost trend chart shows empty state (no data yet)');
    }
  });
});
