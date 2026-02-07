/**
 * E2E tests for the workspace dashboard.
 *
 * Covers: workspace selection, initialization, stats cards, quick actions,
 * activity feed, sidebar navigation, and workspace context persistence.
 */
import { test, expect } from './fixtures/test-setup';
import { TEST_WORKSPACE_PATH, mockWorkspace, mockTaskListResponse, mockEvents } from './fixtures/mock-data';

// ---------------------------------------------------------------------------
// 1. Workspace Selection
// ---------------------------------------------------------------------------
test.describe('Workspace selection', () => {
  test('shows workspace selector when no workspace is set', async ({ page, mockApi }) => {
    await mockApi();
    // Do NOT call withWorkspace — no localStorage entry
    await page.goto('/');

    // The selector heading and input should be visible
    await expect(page.getByRole('heading', { name: 'CodeFRAME' })).toBeVisible();
    await expect(page.getByText('Select a project to get started')).toBeVisible();
    await expect(page.getByLabel('Repository Path')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open Project' })).toBeVisible();
  });

  test('Open Project button is disabled when input is empty', async ({ page, mockApi }) => {
    await mockApi();
    await page.goto('/');

    await expect(page.getByRole('button', { name: 'Open Project' })).toBeDisabled();
  });

  test('selecting an existing workspace loads the dashboard', async ({ page, mockApi }) => {
    await mockApi();
    await page.goto('/');

    // Enter a path and submit
    await page.getByLabel('Repository Path').fill(TEST_WORKSPACE_PATH);
    await page.getByRole('button', { name: 'Open Project' }).click();

    // After selection, dashboard should render with the workspace header
    // The repo name is the last segment of the path
    const repoName = TEST_WORKSPACE_PATH.split('/').pop()!;
    await expect(page.getByText(repoName)).toBeVisible();

    // Stats cards section should be present (use heading role to avoid sidebar/link matches)
    await expect(page.getByText('Tech Stack')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible();
    await expect(page.getByText('Active Runs')).toBeVisible();
  });

  test('shows error when workspace selection fails', async ({ page, mockApi }) => {
    await mockApi({
      'workspaces/exists': async (route) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Server is unreachable' }),
        });
      },
    });
    await page.goto('/');

    await page.getByLabel('Repository Path').fill('/some/bad/path');
    await page.getByRole('button', { name: 'Open Project' }).click();

    // Error message should appear
    await expect(page.getByText('Server is unreachable')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 2. Workspace Initialization
// ---------------------------------------------------------------------------
test.describe('Workspace initialization', () => {
  test('initializes a new workspace when path does not exist', async ({ page, mockApi }) => {
    let initCalled = false;

    await mockApi({
      'workspaces/exists': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ exists: false, path: TEST_WORKSPACE_PATH }),
        });
      },
      'workspaces/init': async (route) => {
        initCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockWorkspace),
        });
      },
    });
    await page.goto('/');

    await page.getByLabel('Repository Path').fill(TEST_WORKSPACE_PATH);
    await page.getByRole('button', { name: 'Open Project' }).click();

    // Dashboard should eventually load (workspace header with repo name)
    const repoName = TEST_WORKSPACE_PATH.split('/').pop()!;
    await expect(page.getByText(repoName)).toBeVisible();

    // The init endpoint should have been called
    expect(initCalled).toBe(true);
  });

  test('shows Initialize Workspace button when workspace is not found after selection', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'workspaces/current': async (route) => {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Workspace not found', status_code: 404 }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    // Header should show "No workspace initialized" message
    await expect(page.getByText('No workspace initialized')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Initialize Workspace' })
    ).toBeVisible();
  });

  test('clicking Initialize Workspace calls the init API', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let initCalled = false;

    // First load returns 404, after init returns workspace
    let callCount = 0;
    await mockApi({
      'workspaces/current': async (route) => {
        callCount++;
        if (callCount <= 1) {
          await route.fulfill({
            status: 404,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Not found', status_code: 404 }),
          });
        } else {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockWorkspace),
          });
        }
      },
      'workspaces/init': async (route) => {
        initCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockWorkspace),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    await expect(
      page.getByRole('button', { name: 'Initialize Workspace' })
    ).toBeVisible();

    await page.getByRole('button', { name: 'Initialize Workspace' }).click();

    // Should have called the init endpoint
    expect(initCalled).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 3. Stats Cards
// ---------------------------------------------------------------------------
test.describe('Stats cards', () => {
  test('renders task count badges with correct numbers', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // Wait for the dashboard to load
    await expect(page.getByText('Tech Stack')).toBeVisible();

    // Tech stack should display the mock value
    await expect(page.getByText(mockWorkspace.tech_stack)).toBeVisible();

    // Task badges from mock data (by_status): READY=1, IN_PROGRESS=1, DONE=1, BLOCKED=1, FAILED=1
    await expect(page.getByTestId('badge-ready')).toHaveText('1 ready');
    await expect(page.getByTestId('badge-in-progress')).toHaveText('1 in progress');
    await expect(page.getByTestId('badge-done')).toHaveText('1 done');
    await expect(page.getByTestId('badge-blocked')).toHaveText('1 blocked');
    await expect(page.getByTestId('badge-failed')).toHaveText('1 failed');

    // Total tasks count
    const totalTasks = mockTaskListResponse.tasks.length;
    await expect(page.getByText(`${totalTasks} total`)).toBeVisible();
  });

  test('displays active run count from IN_PROGRESS tasks', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // Active run count should be 1 (one IN_PROGRESS task in mock data)
    await expect(page.getByTestId('active-run-count')).toHaveText('1');
  });

  test('shows "View Execution" link when there are active runs', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // The "View Execution" link should be visible because IN_PROGRESS > 0
    await expect(page.getByRole('link', { name: /View Execution/ })).toBeVisible();
  });

  test('hides task badges when all counts are zero', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'tasks/list': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tasks: [],
            total: 0,
            by_status: {
              BACKLOG: 0,
              READY: 0,
              IN_PROGRESS: 0,
              DONE: 0,
              BLOCKED: 0,
              FAILED: 0,
              MERGED: 0,
            },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible();
    await expect(page.getByText('0 total')).toBeVisible();

    // No badges should be rendered
    await expect(page.getByTestId('badge-ready')).not.toBeVisible();
    await expect(page.getByTestId('badge-in-progress')).not.toBeVisible();
    await expect(page.getByTestId('badge-done')).not.toBeVisible();
  });

  test('shows "Not detected" when tech stack is null', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'workspaces/current': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...mockWorkspace, tech_stack: null }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    await expect(page.getByText('Not detected')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 4. Quick Actions
// ---------------------------------------------------------------------------
test.describe('Quick action buttons', () => {
  test('renders all quick action buttons', async ({ page, mockApi, withWorkspace }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    await expect(page.getByText('Quick Actions')).toBeVisible();
    await expect(page.getByRole('link', { name: /View PRD/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Manage Tasks/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Review Changes/ })).toBeVisible();
  });

  test('View PRD button navigates to /prd', async ({ page, mockApi, withWorkspace }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    const prdLink = page.getByRole('link', { name: /View PRD/ });
    await expect(prdLink).toHaveAttribute('href', '/prd');
  });

  test('Manage Tasks button navigates to /tasks', async ({ page, mockApi, withWorkspace }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    const tasksLink = page.getByRole('link', { name: /Manage Tasks/ });
    await expect(tasksLink).toHaveAttribute('href', '/tasks');
  });

  test('Review Changes button navigates to /review', async ({ page, mockApi, withWorkspace }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    const reviewLink = page.getByRole('link', { name: /Review Changes/ });
    await expect(reviewLink).toHaveAttribute('href', '/review');
  });
});

// ---------------------------------------------------------------------------
// 5. Activity Feed
// ---------------------------------------------------------------------------
test.describe('Activity feed', () => {
  test('renders activity events in timeline format', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // "Recent Activity" card should be visible (use heading to avoid matching "No recent activity")
    await expect(page.getByRole('heading', { name: 'Recent Activity' })).toBeVisible();

    // Mock events have 2 items — check their descriptions appear
    // Event 1: task_completed with payload { title: 'Deploy to staging' }
    // Event 2: run_started with payload { title: 'Create user dashboard' }
    // The mapEventToActivity function builds descriptions from payload
    // event_type 'task_completed' and 'run_started' are mapped through EVENT_TYPE_MAP
    // Both lack description/message in payload, so description = event_type.replace(/[._]/g, ' ')
    // But task_title is set from payload.title? No — payload has "title" not "task_title"
    // So description = "task completed" and "run started"
    await expect(page.getByText('task completed')).toBeVisible();
    await expect(page.getByText('run started')).toBeVisible();
  });

  test('shows timestamps for activity items', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // Activity timestamps use data-testid="activity-timestamp"
    const timestamps = page.getByTestId('activity-timestamp');
    await expect(timestamps.first()).toBeVisible();
  });

  test('shows "No recent activity" when there are no events', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      events: async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ events: [], total: 0 }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    await expect(page.getByText('No recent activity')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 6. Sidebar Navigation
// ---------------------------------------------------------------------------
test.describe('Sidebar navigation', () => {
  test('sidebar is visible when a workspace is selected', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // The sidebar renders as <aside> with navigation links
    const sidebar = page.locator('aside');
    await expect(sidebar).toBeVisible();

    // Enabled nav items should be present as links
    await expect(sidebar.getByRole('link', { name: /Workspace/i })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /PRD/i })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /Tasks/i })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: /Execution/i })).toBeVisible();
  });

  test('sidebar is hidden when no workspace is selected', async ({
    page,
    mockApi,
  }) => {
    await mockApi();
    // Do NOT call withWorkspace
    await page.goto('/');

    // Sidebar should not render
    await expect(page.locator('aside')).not.toBeVisible();
  });

  test('sidebar highlights active page', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // The "Workspace" link should have the active styles (bg-accent class)
    const workspaceLink = page.locator('aside').getByRole('link', { name: /Workspace/i });
    await expect(workspaceLink).toHaveClass(/bg-accent/);
  });

  test('disabled sidebar items are not links', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // Blockers and Review are disabled (enabled: false) — rendered as <span> not <a>
    const sidebar = page.locator('aside');
    // They should appear as text but NOT as links
    await expect(sidebar.getByText('Blockers')).toBeVisible();
    await expect(sidebar.getByText('Review')).toBeVisible();
    // Verify they are not rendered as links
    const blockerLinks = sidebar.getByRole('link', { name: /Blockers/i });
    await expect(blockerLinks).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 7. Workspace Context Persistence
// ---------------------------------------------------------------------------
test.describe('Workspace context persistence', () => {
  test('workspace persists after navigating to /tasks and back', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // Verify dashboard loaded
    const repoName = TEST_WORKSPACE_PATH.split('/').pop()!;
    await expect(page.getByText(repoName)).toBeVisible();

    // Navigate to tasks page via sidebar
    await page.locator('aside').getByRole('link', { name: /Tasks/i }).click();
    await page.waitForURL('**/tasks');

    // Navigate back to workspace
    await page.locator('aside').getByRole('link', { name: /Workspace/i }).click();
    await page.waitForURL('/');

    // Dashboard should still show workspace data, not the selector
    await expect(page.getByText(repoName)).toBeVisible();
    await expect(page.getByText('Tech Stack')).toBeVisible();
  });

  test('switching workspace shows the selector again', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/');

    // The dashboard should be loaded
    const repoName = TEST_WORKSPACE_PATH.split('/').pop()!;
    await expect(page.getByText(repoName)).toBeVisible();

    // Click "Switch project" button to go back to selector
    await page.getByRole('button', { name: /Switch project/i }).click();

    // Workspace selector should appear
    await expect(page.getByText('Select a project to get started')).toBeVisible();
    await expect(page.getByLabel('Repository Path')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 8. Loading State
// ---------------------------------------------------------------------------
test.describe('Loading state', () => {
  test('shows loading skeleton while workspace data is being fetched', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    // Delay the workspace API response to observe loading state
    await mockApi({
      'workspaces/current': async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockWorkspace),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    // Loading skeleton should appear
    await expect(page.getByTestId('workspace-loading')).toBeVisible();

    // After loading completes, skeleton disappears and dashboard appears
    await expect(page.getByText('Tech Stack')).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId('workspace-loading')).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 9. Error Handling
// ---------------------------------------------------------------------------
test.describe('Error handling', () => {
  test('shows error state for non-404 API errors', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'workspaces/current': async (route) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error', status_code: 500 }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    // Error state should display
    await expect(page.getByRole('heading', { name: 'Error' })).toBeVisible();
    await expect(page.getByText('Internal server error')).toBeVisible();

    // "Select a different project" link should be available
    await expect(
      page.getByRole('button', { name: /Select a different project/i })
    ).toBeVisible();
  });

  test('clicking "Select a different project" returns to workspace selector', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'workspaces/current': async (route) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error', status_code: 500 }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/');

    await page.getByRole('button', { name: /Select a different project/i }).click();

    // Should return to workspace selector
    await expect(page.getByText('Select a project to get started')).toBeVisible();
  });
});
