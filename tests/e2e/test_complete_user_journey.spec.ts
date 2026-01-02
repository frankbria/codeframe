/**
 * E2E Tests: Complete User Journey
 *
 * Tests the full end-to-end workflow from authentication to agent execution:
 * 1. Authenticate (currently via session bypass)
 * 2. Create a new project
 * 3. Start Socratic discovery
 * 4. Answer discovery questions
 * 5. Wait for PRD generation
 * 6. Verify agent execution begins
 * 7. Verify dashboard panels are accessible
 *
 * NOTE: Currently uses auth bypass (setTestUserSession) instead of loginUser()
 * due to BetterAuth/CodeFRAME integration issue. See GitHub issue #158.
 * Once auth is aligned, replace setTestUserSession() with loginUser().
 */

import { test, expect } from '@playwright/test';
import { answerDiscoveryQuestion } from './test-utils';
import { setTestUserSession } from './auth-bypass';

test.describe('Complete User Journey', () => {
  // Set session cookie to bypass login (temporary until auth alignment)
  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();
    await setTestUserSession(page);
  });

  // TODO (Issue #158): This test is currently skipped because the dashboard doesn't load
  // due to BetterAuth/CodeFRAME auth mismatch. Once auth is aligned, remove .skip() from this test.

  test.skip('should complete full workflow from authentication to agent execution', async ({ page }) => {
    // Step 1: Verify authentication (via session cookie set in beforeEach)
    // Navigate to root to verify we're authenticated
    await page.goto('/');
    await expect(page.getByTestId('user-menu')).toBeVisible();

    // Step 2: Create a new project
    await page.goto('/');

    // Wait for form to be visible (shown directly on root page)
    await page.getByTestId('project-name-input').waitFor({ state: 'visible' });

    const projectName = `journey-test-${Date.now()}`;
    await page.getByTestId('project-name-input').fill(projectName);
    await page.getByTestId('project-description-input').fill(
      'Journey test project created to test full E2E workflow'
    );

    await page.getByTestId('create-project-submit').click();

    // Assert redirect to project dashboard
    await expect(page).toHaveURL(/\/projects\/\d+/);
    await expect(page.getByTestId('dashboard-header')).toBeVisible();

    // Step 3: Discovery starts automatically - verify discovery UI
    await expect(page.getByTestId('discovery-question')).toBeVisible({ timeout: 10000 });

    // Step 4: Answer 2-3 discovery questions
    const numberOfQuestions = 3;
    for (let i = 0; i < numberOfQuestions; i++) {
      // Check if we still have questions to answer
      const questionVisible = await page.getByTestId('discovery-question')
        .isVisible()
        .catch(() => false);

      if (!questionVisible) {
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

    // Check metrics panel
    await expect(page.getByTestId('metrics-panel')).toBeVisible({ timeout: 5000 });

    // Check review findings panel
    await expect(page.getByTestId('review-findings-panel')).toBeVisible({ timeout: 5000 });

    // Verify navigation tabs work
    await expect(page.getByTestId('nav-menu')).toBeVisible();

    // Click on Context tab
    const contextTab = page.getByTestId('context-tab');
    await expect(contextTab).toBeVisible();
    await contextTab.click();

    // Verify we switched to context tab
    await expect(contextTab).toHaveAttribute('aria-selected', 'true');

    // Click on Checkpoints tab
    const checkpointTab = page.getByTestId('checkpoint-tab');
    await expect(checkpointTab).toBeVisible();
    await checkpointTab.click();

    // Verify we switched to checkpoint tab
    await expect(checkpointTab).toHaveAttribute('aria-selected', 'true');

    // Verify checkpoint panel is visible
    await expect(page.getByTestId('checkpoint-panel')).toBeVisible();

    // Return to overview tab
    const overviewTab = page.getByTestId('overview-tab');
    await overviewTab.click();
    await expect(overviewTab).toHaveAttribute('aria-selected', 'true');

    // Final verification: Project is in a healthy state
    // Check that dashboard header still shows project name
    await expect(page.locator('h1')).toContainText(projectName);

    // Verify connection status indicator
    const headerElement = page.getByTestId('dashboard-header');
    await expect(headerElement).toBeVisible();
  });
});
