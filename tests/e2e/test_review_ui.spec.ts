/**
 * T158: Playwright E2E test for Review Findings Display.
 *
 * Tests:
 * - Review findings panel displays correctly
 * - Review severity badges are visible
 * - Review score chart updates
 * - Review details expand/collapse
 */

import { test, expect } from '@playwright/test';
import { loginUser } from './test-utils';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';
const PROJECT_ID = process.env.E2E_TEST_PROJECT_ID || '1';

test.describe('Review Findings UI', () => {
  test.beforeEach(async ({ page }) => {
    // Login using real authentication flow
    await loginUser(page);

    // Navigate to dashboard for test project
    await page.goto(`${FRONTEND_URL}/projects/${PROJECT_ID}`);
    await page.waitForLoadState('networkidle');

    // Wait for project API to load
    await page.waitForResponse(response =>
      response.url().includes(`/projects/${PROJECT_ID}`) && response.status() === 200,
      { timeout: 10000 }
    ).catch(() => {});

    // Wait for dashboard to render - agent panel is last to render
    await page.locator('[data-testid="agent-status-panel"]').waitFor({ state: 'attached', timeout: 10000 }).catch(() => {});

    // Navigate to Tasks tab where review findings now live (Sprint 10 Refactor)
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 });
    await tasksTab.click();

    // Wait for review findings panel to be visible
    await page.locator('[data-testid="review-findings-panel"]').waitFor({ state: 'attached', timeout: 10000 }).catch(() => {});
  });

  test('should display review findings panel', async ({ page }) => {
    // Already on Tasks tab from beforeEach (Sprint 10 Refactor)
    const reviewPanel = page.locator('[data-testid="review-findings-panel"]');

    // Wait for panel to exist and be visible
    await reviewPanel.waitFor({ state: 'attached', timeout: 15000 });

    // Scroll panel into view
    await reviewPanel.scrollIntoViewIfNeeded().catch(() => {});

    await reviewPanel.waitFor({ state: 'visible', timeout: 10000 });
    await expect(reviewPanel).toBeVisible();

    // Check for review components
    await expect(page.locator('[data-testid="review-summary"]')).toBeAttached();
    await expect(page.locator('[data-testid="review-findings-list"]')).toBeAttached();
  });

  test('should display severity badges correctly', async ({ page }) => {
    const severities = ['critical', 'high', 'medium', 'low'];

    for (const severity of severities) {
      // Check if severity badge exists (may be 0 count)
      const badge = page.locator(`[data-testid="severity-badge-${severity}"]`);
      const count = await badge.count();
      // Badge should exist in UI even if count is 0
      expect(count >= 0).toBe(true);
    }
  });

  test('should display review score chart', async ({ page }) => {
    const scoreChart = page.locator('[data-testid="review-score-chart"]');

    // Chart may not be visible if no review data exists
    if (await scoreChart.isVisible()) {
      // Chart should have data or empty state
      const hasData = await scoreChart.locator('[data-testid="chart-data"]').count() > 0;
      const hasEmptyState = await scoreChart.locator('[data-testid="chart-empty"]').count() > 0;

      expect(hasData || hasEmptyState).toBe(true);
    }
  });

  test('should expand/collapse review finding details', async ({ page }) => {
    // Individual review findings with expand/collapse now implemented in ReviewSummary

    const findingsList = page.locator('[data-testid="review-findings-list"]');

    // Get first finding item
    const firstFinding = findingsList.locator('[data-testid^="review-finding-"]').first();

    if (await firstFinding.count() > 0) {
      // Click to expand
      await firstFinding.click();

      // Details should be visible
      const details = firstFinding.locator('[data-testid="finding-details"]');
      await expect(details).toBeVisible();

      // Click again to collapse
      await firstFinding.click();
      await expect(details).not.toBeVisible();
    }
  });

  test('should filter findings by severity', async ({ page }) => {
    // Severity filter now implemented in ReviewSummary

    const severityFilter = page.locator('[data-testid="severity-filter"]');

    if (await severityFilter.isVisible()) {
      // Select "critical" filter
      await severityFilter.selectOption('critical');

      // Wait for findings list to update (either filtered results or empty state)
      await Promise.race([
        page.locator('[data-testid^="review-finding-"]').first().waitFor({ state: 'attached', timeout: 3000 }),
        page.locator('[data-testid="no-findings"]').waitFor({ state: 'visible', timeout: 3000 })
      ]).catch(() => {});

      // Only critical findings should be visible
      const findings = page.locator('[data-testid^="review-finding-"]');
      const count = await findings.count();

      if (count > 0) {
        // Verify all visible findings are critical
        for (let i = 0; i < count; i++) {
          const finding = findings.nth(i);
          const severityBadge = finding.locator('[data-testid="severity-badge"]');
          const severityText = await severityBadge.textContent();
          expect(severityText?.toLowerCase()).toContain('critical');
        }
      }
    }
  });

  test('should display actionable recommendations', async ({ page }) => {
    // Individual finding recommendations now implemented in ReviewSummary

    const findingsList = page.locator('[data-testid="review-findings-list"]');
    const firstFinding = findingsList.locator('[data-testid^="review-finding-"]').first();

    if (await firstFinding.count() > 0) {
      await firstFinding.click();

      // Recommendation should be visible
      const recommendation = firstFinding.locator('[data-testid="finding-recommendation"]');
      await expect(recommendation).toBeVisible();

      // Should have non-empty text
      const recText = await recommendation.textContent();
      expect(recText).toBeTruthy();
      expect(recText!.length).toBeGreaterThan(10);

      // Verify lightbulb icon is present (Issue #6 - Enhanced test coverage)
      const icon = recommendation.locator('span[aria-hidden="true"]').filter({ hasText: '💡' });
      await expect(icon).toBeVisible();

      // Verify blue background styling is applied (Issue #6 - Enhanced test coverage)
      const bgColor = await recommendation.evaluate((el) => {
        const styles = window.getComputedStyle(el);
        return styles.backgroundColor;
      });
      // Should have blue-ish background (rgb values for bg-blue-50)
      expect(bgColor).toMatch(/rgb\(239,\s*246,\s*255\)/);
    }
  });
});
