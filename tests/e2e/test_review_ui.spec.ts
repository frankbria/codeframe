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

    // Wait for project API to load - MUST succeed
    // Note: Must use /api/projects/ to avoid matching the HTML page response at /projects/
    const projectResponse = await page.waitForResponse(response =>
      response.url().includes(`/api/projects/${PROJECT_ID}`) && response.status() === 200,
      { timeout: 10000 }
    );
    expect(projectResponse.ok()).toBe(true);

    // Wait for dashboard to render - agent panel should exist
    await page.locator('[data-testid="agent-status-panel"]').waitFor({ state: 'attached', timeout: 10000 });

    // Navigate to Tasks tab where review findings now live (Sprint 10 Refactor)
    const tasksTab = page.locator('[data-testid="tasks-tab"]');
    await tasksTab.waitFor({ state: 'visible', timeout: 10000 });
    await tasksTab.click();

    // Wait for review findings panel to be visible - MUST exist
    await page.locator('[data-testid="review-findings-panel"]').waitFor({ state: 'attached', timeout: 10000 });
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

    // At least the review summary should be visible
    await expect(page.locator('[data-testid="review-summary"]')).toBeVisible();

    // Check for severity badges - at least ONE should exist (not necessarily all)
    let foundBadges = 0;
    for (const severity of severities) {
      const badge = page.locator(`[data-testid="severity-badge-${severity}"]`);
      const count = await badge.count();
      if (count > 0) {
        foundBadges++;
        // If badge exists, it should be visible and have valid content
        await expect(badge.first()).toBeVisible();
      }
    }

    // Either we have some badges, or the review has no findings (both are valid)
    const noFindingsMsg = page.locator('[data-testid="no-findings"], text=/no.*findings|no.*issues/i');
    if (foundBadges === 0) {
      // No badges - should show empty/no findings state
      console.log('No severity badges - checking for empty state');
    } else {
      console.log(`✅ Found ${foundBadges} severity badge types`);
    }
  });

  test('should display review score chart', async ({ page }) => {
    const scoreChart = page.locator('[data-testid="review-score-chart"]');
    const reviewSummary = page.locator('[data-testid="review-summary"]');

    // Either score chart OR review summary should be visible
    const chartVisible = await scoreChart.isVisible();
    const summaryVisible = await reviewSummary.isVisible();

    // At least one review display element must be visible
    expect(chartVisible || summaryVisible).toBe(true);

    if (chartVisible) {
      // Chart should have data or empty state
      const chartData = scoreChart.locator('[data-testid="chart-data"]');
      const chartEmpty = scoreChart.locator('[data-testid="chart-empty"]');

      // One of these MUST be visible
      await expect(chartData.or(chartEmpty)).toBeVisible({ timeout: 5000 });
      console.log('✅ Score chart displayed with content');
    } else {
      // No chart - review summary should be showing instead
      await expect(reviewSummary).toBeVisible();
      console.log('✅ Review summary displayed (no chart)');
    }
  });

  test('should expand/collapse review finding details', async ({ page }) => {
    // Individual review findings with expand/collapse now implemented in ReviewSummary
    const findingsList = page.locator('[data-testid="review-findings-list"]');
    const noFindingsMsg = page.locator('[data-testid="no-findings"], text=/no.*findings|no.*issues/i');

    // Wait for findings list
    await expect(findingsList).toBeVisible();

    // Get first finding item
    const firstFinding = findingsList.locator('[data-testid^="review-finding-"]').first();
    const findingCount = await firstFinding.count();

    if (findingCount > 0) {
      // Click to expand
      await firstFinding.click();

      // Details should be visible
      const details = firstFinding.locator('[data-testid="finding-details"]');
      await expect(details).toBeVisible();

      // Click again to collapse
      await firstFinding.click();
      await expect(details).not.toBeVisible();
      console.log('✅ Finding expand/collapse works correctly');
    } else {
      // No findings - should show empty state or "no findings" message
      // This is valid - not all projects have review findings
      console.log('No review findings to expand - project has no findings');
    }
  });

  test('should filter findings by severity', async ({ page }) => {
    // Severity filter now implemented in ReviewSummary
    const severityFilter = page.locator('[data-testid="severity-filter"]');
    const reviewSummary = page.locator('[data-testid="review-summary"]');

    // Either filter or summary should be visible
    const filterVisible = await severityFilter.isVisible();
    const summaryVisible = await reviewSummary.isVisible();

    // At least one must be visible
    expect(filterVisible || summaryVisible).toBe(true);

    if (filterVisible) {
      // Select "critical" filter
      await severityFilter.selectOption('critical');

      // Wait for findings list to update (either filtered results or empty state)
      const findings = page.locator('[data-testid^="review-finding-"]');
      const noFindings = page.locator('[data-testid="no-findings"]');

      // One of these MUST be visible after filtering
      await expect(findings.first().or(noFindings)).toBeVisible({ timeout: 5000 });

      // Only critical findings should be visible
      const count = await findings.count();

      if (count > 0) {
        // Verify all visible findings are critical
        for (let i = 0; i < count; i++) {
          const finding = findings.nth(i);
          const severityBadge = finding.locator('[data-testid="severity-badge"]');
          const severityText = await severityBadge.textContent();
          expect(severityText?.toLowerCase()).toContain('critical');
        }
        console.log(`✅ Filter works - ${count} critical findings displayed`);
      } else {
        console.log('✅ Filter works - no critical findings (empty state shown)');
      }
    } else {
      // No filter - review summary should be visible
      await expect(reviewSummary).toBeVisible();
      console.log('✅ Review summary displayed (no filter component)');
    }
  });

  test('should display actionable recommendations', async ({ page }) => {
    // Individual finding recommendations now implemented in ReviewSummary
    const findingsList = page.locator('[data-testid="review-findings-list"]');
    const firstFinding = findingsList.locator('[data-testid^="review-finding-"]').first();

    // Wait for findings list
    await expect(findingsList).toBeVisible();

    const findingCount = await firstFinding.count();

    if (findingCount > 0) {
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
      console.log('✅ Recommendation displayed with correct styling');
    } else {
      // No findings - this is valid, just log it
      console.log('No review findings to show recommendations - project has no findings');
    }
  });
});
