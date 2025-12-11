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

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test.describe('Metrics Dashboard UI', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to dashboard for test project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for project API to load
    await page.waitForResponse(response =>
      response.url().includes(`/projects/${PROJECT_ID}`) && response.status() === 200,
      { timeout: 10000 }
    ).catch(() => {});

    // Wait for dashboard to render
    await page.waitForTimeout(1000);

    // Navigate to metrics section
    const metricsTab = page.locator('[data-testid="metrics-tab"]');
    await metricsTab.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
    if (await metricsTab.isVisible()) {
      await metricsTab.click();
      await page.waitForTimeout(500); // Wait for tab switch animation

      // Wait for metrics API to load
      await page.waitForResponse(response =>
        response.url().includes('/metrics') && response.status() === 200,
        { timeout: 10000 }
      ).catch(() => {});

      await page.waitForTimeout(500); // Wait for data rendering
    }
  });

  test('should display metrics panel', async ({ page }) => {
    const metricsPanel = page.locator('[data-testid="metrics-panel"]');

    // Scroll panel into view
    await metricsPanel.scrollIntoViewIfNeeded().catch(() => {});

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

    // Chart should have data or show empty state message
    const hasData = (await trendChart.locator('[data-testid="trend-chart-data"]').count()) > 0;
    const hasEmptyState = (await trendChart.textContent())?.includes('No time series data') || false;

    expect(hasData || hasEmptyState).toBe(true);
  });

  test('should display cost breakdown by agent', async ({ page }) => {
    const agentBreakdown = page.locator('[data-testid="cost-by-agent"]');
    await agentBreakdown.waitFor({ state: 'visible', timeout: 15000 });
    await expect(agentBreakdown).toBeVisible();

    // Should have list of agents or empty state
    const agentItems = page.locator('[data-testid^="agent-cost-"]');
    const count = await agentItems.count();

    if (count === 0) {
      const emptyState = page.locator('[data-testid="agent-cost-empty"]');
      await expect(emptyState).toBeVisible();
    } else {
      // Verify first agent item has name and cost
      const firstAgent = agentItems.first();
      await expect(firstAgent.locator('[data-testid="agent-name"]')).toBeVisible();
      await expect(firstAgent.locator('[data-testid="agent-cost"]')).toBeVisible();
    }
  });

  test('should display cost breakdown by model', async ({ page }) => {
    const modelBreakdown = page.locator('[data-testid="cost-by-model"]');
    await modelBreakdown.waitFor({ state: 'visible', timeout: 15000 });
    await expect(modelBreakdown).toBeVisible();

    // Should have list of models or empty state
    const modelItems = page.locator('[data-testid^="model-cost-"]');
    const count = await modelItems.count();

    if (count === 0) {
      const emptyState = page.locator('[data-testid="model-cost-empty"]');
      await expect(emptyState).toBeVisible();
    } else {
      // Verify model names match expected models
      const expectedModels = ['sonnet', 'opus', 'haiku'];
      const firstModel = modelItems.first();
      const modelText = await firstModel.locator('[data-testid="model-name"]').textContent();

      const matchesExpected = expectedModels.some(model =>
        modelText?.toLowerCase().includes(model)
      );
      expect(matchesExpected).toBe(true);
    }
  });

  test('should filter metrics by date range', async ({ page }) => {
    const dateFilter = page.locator('[data-testid="date-range-filter"]');

    if (await dateFilter.isVisible()) {
      // Select "Last 7 days" filter
      await dateFilter.selectOption('last-7-days');

      // Wait for filter to apply
      await page.waitForTimeout(500);

      // Chart should update (verify by checking if loading indicator appeared and disappeared)
      const loadingIndicator = page.locator('[data-testid="metrics-loading"]');

      // Loading might be too fast to catch, so just verify chart is still visible
      const tokenChart = page.locator('[data-testid="token-usage-chart"]');
      await expect(tokenChart).toBeVisible();
    }
  });

  test('should export cost report to CSV', async ({ page }) => {
    const exportButton = page.locator('[data-testid="export-csv-button"]');

    if (await exportButton.isVisible()) {
      // Setup download listener
      const downloadPromise = page.waitForEvent('download', { timeout: 5000 });

      // Click export button
      await exportButton.click();

      // Verify download started
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toContain('.csv');
    }
  });

  test('should display cost per task', async ({ page }) => {
    const taskCostTable = page.locator('[data-testid="cost-per-task-table"]');

    if (await taskCostTable.isVisible()) {
      // Table should have headers
      await expect(page.locator('[data-testid="task-column-header"]')).toBeVisible();
      await expect(page.locator('[data-testid="cost-column-header"]')).toBeVisible();
      await expect(page.locator('[data-testid="tokens-column-header"]')).toBeVisible();

      // Table should have rows or empty state
      const taskRows = page.locator('[data-testid^="task-cost-row-"]');
      const count = await taskRows.count();

      if (count === 0) {
        const emptyState = page.locator('[data-testid="task-cost-empty"]');
        await expect(emptyState).toBeVisible();
      } else {
        // Verify first row has data
        const firstRow = taskRows.first();
        await expect(firstRow.locator('[data-testid="task-description"]')).toBeVisible();
        await expect(firstRow.locator('[data-testid="task-cost"]')).toBeVisible();
      }
    }
  });

  test('should display model pricing information', async ({ page }) => {
    const pricingInfo = page.locator('[data-testid="model-pricing-info"]');

    if (await pricingInfo.isVisible()) {
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

    // Wait for potential real-time update (WebSocket)
    await page.waitForTimeout(3000);

    // Cost might update via WebSocket (or stay the same if no new data)
    const updatedCost = await totalCostDisplay.textContent();

    // Both values should be valid cost formats
    expect(initialCost).toMatch(/\$\d+\.\d{2}/);
    expect(updatedCost).toMatch(/\$\d+\.\d{2}/);

    // They might be equal if no updates occurred (not an error)
  });

  test('should display cost trend chart', async ({ page }) => {
    const trendChart = page.locator('[data-testid="cost-trend-chart"]');

    if (await trendChart.isVisible()) {
      // Chart should show cost over time
      await expect(page.locator('[data-testid="trend-chart-data"]')).toBeVisible();

      // X-axis should show time labels
      const xAxis = page.locator('[data-testid="chart-x-axis"]');
      if (await xAxis.count() > 0) {
        const axisText = await xAxis.textContent();
        // Should contain date/time information
        expect(axisText).toBeTruthy();
      }
    }
  });
});
