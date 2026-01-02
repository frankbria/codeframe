/**
 * E2E Tests: Start Agent Flow
 *
 * Tests the agent execution flow including:
 * - Starting Socratic discovery from dashboard
 * - Answering discovery questions and generating PRD
 * - Executing tasks after discovery completion
 *
 * Note: Discovery appears to start automatically when a project is created,
 * so these tests focus on the discovery question interaction and PRD generation.
 *
 * Uses unified BetterAuth authentication system aligned with CodeFRAME's
 * existing `users` and `sessions` tables (plural naming).
 */

import { test, expect } from '@playwright/test';
import { createTestProject, answerDiscoveryQuestion, loginUser } from './test-utils';

test.describe('Start Agent Flow', () => {
  // Login using real authentication flow
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await loginUser(page);
  });

  test('should start Socratic discovery from dashboard', async ({ page }) => {
    // Create a project (already authenticated via beforeEach)
    const projectId = await createTestProject(page);

    // Navigate to project dashboard (should already be there after creation)
    await page.goto(`/projects/${projectId}`);

    // Assert discovery question is visible (discovery starts automatically)
    await expect(page.getByTestId('discovery-question')).toBeVisible({ timeout: 10000 });

    // Assert discovery answer input is visible
    await expect(page.getByTestId('discovery-answer-input')).toBeVisible();

    // Assert submit button is visible
    await expect(page.getByTestId('submit-answer-button')).toBeVisible();
  });

  test('should answer discovery questions and generate PRD', async ({ page }) => {
    // Create a project (already authenticated via beforeEach)
    const projectId = await createTestProject(page);

    // Navigate to project dashboard
    await page.goto(`/projects/${projectId}`);

    // Wait for first discovery question
    await page.getByTestId('discovery-question').waitFor({ state: 'visible', timeout: 10000 });

    // Answer 3 discovery questions
    for (let i = 0; i < 3; i++) {
      // Check if discovery question is still visible
      const questionVisible = await page.getByTestId('discovery-question').isVisible().catch(() => false);

      if (!questionVisible) {
        // Discovery might be complete
        break;
      }

      // Answer the question
      await answerDiscoveryQuestion(
        page,
        `Test answer ${i + 1} - This is a comprehensive response to help generate the PRD.`
      );

      // Wait for next question or completion
      await page.waitForTimeout(3000);
    }

    // Check if PRD has been generated (View PRD button should be visible)
    // Note: PRD generation may take longer, so we use a generous timeout
    await expect(page.getByTestId('prd-generated')).toBeVisible({ timeout: 15000 });
  });

  test('should show agent status panel after project creation', async ({ page }) => {
    // Create a project (already authenticated via beforeEach)
    const projectId = await createTestProject(page);

    // Navigate to project dashboard
    await page.goto(`/projects/${projectId}`);

    // Assert agent status panel is visible
    await expect(page.getByTestId('agent-status-panel')).toBeVisible({ timeout: 10000 });

    // Note: Agent execution appears to be triggered automatically by the backend
    // based on project phase progression. We verify the agent status panel exists
    // rather than clicking a "start execution" button which doesn't exist in the current UI.
  });
});
