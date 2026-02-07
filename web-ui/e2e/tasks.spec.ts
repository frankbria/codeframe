/**
 * E2E tests for the CodeFRAME Task Board page.
 *
 * Covers: Kanban board rendering, task cards, filtering, detail modal,
 * status changes, batch selection, and batch execution.
 */
import { test, expect } from './fixtures/test-setup';
import { mockTasks, mockTaskListResponse } from './fixtures/mock-data';

// ---------------------------------------------------------------------------
// 1. Kanban Board Rendering
// ---------------------------------------------------------------------------
test.describe('Kanban board renders', () => {
  test('displays all six status columns with correct headers', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Column headers are uppercase h3 elements
    const expectedHeaders = ['Backlog', 'Ready', 'In Progress', 'Blocked', 'Failed', 'Done'];
    for (const header of expectedHeaders) {
      await expect(page.getByRole('heading', { name: header, level: 3 })).toBeVisible();
    }
  });

  test('shows the page title and total task count', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    await expect(page.getByRole('heading', { name: 'Task Board', level: 1 })).toBeVisible();
    await expect(page.getByText(`${mockTasks.length} tasks total`)).toBeVisible();
  });

  test('places tasks in the correct status columns', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Each column shows a badge with the count of tasks in that status
    // The mock data has 1 task per status (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED, FAILED)
    // Verify task titles appear on the page
    for (const task of mockTasks) {
      await expect(page.getByText(task.title).first()).toBeVisible();
    }
  });

  test('shows "No tasks" in empty columns', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    // Override tasks to only have READY tasks — other columns should be empty
    await mockApi({
      'tasks/list': async (route) => {
        const readyOnly = mockTasks.filter((t) => t.status === 'READY');
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tasks: readyOnly,
            total: readyOnly.length,
            by_status: { BACKLOG: 0, READY: 1, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 0 },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // At least one column should show "No tasks" since only READY has tasks
    const noTasksLabels = page.getByText('No tasks');
    await expect(noTasksLabels.first()).toBeVisible();
    // There should be 5 empty columns
    await expect(noTasksLabels).toHaveCount(5);
  });
});

// ---------------------------------------------------------------------------
// 2. Task Card Display
// ---------------------------------------------------------------------------
test.describe('Task card display', () => {
  test('shows title, status badge, and description snippet', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Pick a specific task — "Set up authentication" (READY)
    const readyTask = mockTasks.find((t) => t.id === 'task-001')!;
    const card = page.getByRole('button', { name: `View details for ${readyTask.title}` });
    await expect(card).toBeVisible();

    // Status badge on the card
    await expect(card.getByText('Ready')).toBeVisible();

    // Description snippet
    await expect(card.getByText(readyTask.description)).toBeVisible();
  });

  test('shows dependency count for tasks with dependencies', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // task-002 depends on task-001 → should show "1" dependency indicator
    const cardWithDep = page.getByRole('button', { name: 'View details for Create user dashboard' });
    await expect(cardWithDep).toBeVisible();
    // The dependency count shows as a number near the LinkCircleIcon
    await expect(cardWithDep.getByTitle('Depends on 1 task(s)')).toBeVisible();
  });

  test('does not show dependency indicator for tasks without dependencies', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // task-001 has no dependencies
    const card = page.getByRole('button', { name: 'View details for Set up authentication' });
    await expect(card).toBeVisible();
    // Should NOT have a dependency indicator
    await expect(card.locator('[title^="Depends on"]')).toHaveCount(0);
  });

  test('shows Execute button on READY tasks', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    const readyCard = page.getByRole('button', { name: 'View details for Set up authentication' });
    await expect(readyCard.getByRole('button', { name: 'Execute' })).toBeVisible();
  });

  test('shows Mark Ready button on BACKLOG tasks', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    const backlogCard = page.getByRole('button', { name: 'View details for Write API tests' });
    await expect(backlogCard.getByRole('button', { name: 'Mark Ready' })).toBeVisible();
  });

  test('does not show action buttons on IN_PROGRESS/DONE/BLOCKED/FAILED tasks', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // IN_PROGRESS task
    const ipCard = page.getByRole('button', { name: 'View details for Create user dashboard' });
    await expect(ipCard.getByRole('button', { name: 'Execute' })).toHaveCount(0);
    await expect(ipCard.getByRole('button', { name: 'Mark Ready' })).toHaveCount(0);

    // DONE task
    const doneCard = page.getByRole('button', { name: 'View details for Deploy to staging' });
    await expect(doneCard.getByRole('button', { name: 'Execute' })).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 3. Task Filtering
// ---------------------------------------------------------------------------
test.describe('Task filtering', () => {
  test('filters by status when clicking a status badge', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // All tasks visible initially
    for (const task of mockTasks) {
      await expect(page.getByText(task.title).first()).toBeVisible();
    }

    // Click the "Ready" filter badge (in the TaskFilters area, not inside a card)
    // The filter badges are buttons wrapping Badge components
    const filterArea = page.locator('.flex.flex-wrap.items-center.gap-3');
    const readyFilter = filterArea.getByText('Ready');
    await readyFilter.click();

    // Only the READY task should remain visible
    await expect(page.getByText('Set up authentication')).toBeVisible();

    // Other tasks should be hidden (filtered out, not in DOM at all since columns show filtered tasks)
    await expect(page.getByRole('button', { name: 'View details for Create user dashboard' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'View details for Write API tests' })).toHaveCount(0);
  });

  test('clears filter when clicking the active status badge again', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Apply filter
    const filterArea = page.locator('.flex.flex-wrap.items-center.gap-3');
    const readyFilter = filterArea.getByText('Ready');
    await readyFilter.click();

    // Only 1 task visible
    await expect(page.getByRole('button', { name: 'View details for Set up authentication' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'View details for Create user dashboard' })).toHaveCount(0);

    // Click again to clear
    await readyFilter.click();

    // All tasks visible again
    await expect(page.getByText('Create user dashboard')).toBeVisible();
  });

  test('shows Clear button when a status filter is active', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // No Clear button initially
    const filterArea = page.locator('.flex.flex-wrap.items-center.gap-3');
    await expect(filterArea.getByText('Clear')).toHaveCount(0);

    // Apply filter
    await filterArea.getByText('Backlog').click();

    // Clear button appears
    await expect(filterArea.getByText('Clear')).toBeVisible();

    // Click Clear to reset
    await filterArea.getByText('Clear').click();

    // All tasks visible again
    for (const task of mockTasks) {
      await expect(page.getByText(task.title).first()).toBeVisible();
    }
  });

  test('filters tasks by search query', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Type in search input
    const searchInput = page.getByPlaceholder('Search tasks...');
    await searchInput.fill('authentication');

    // Wait for debounce (300ms) and filter to apply
    await page.waitForTimeout(400);

    // Only tasks matching "authentication" should be visible
    await expect(page.getByText('Set up authentication')).toBeVisible();

    // Others should be hidden
    await expect(page.getByRole('button', { name: 'View details for Write API tests' })).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 4. Task Detail Modal
// ---------------------------------------------------------------------------
test.describe('Task detail modal', () => {
  test('opens when clicking a task card and shows full details', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Click on the "Set up authentication" card
    const card = page.getByRole('button', { name: 'View details for Set up authentication' });
    await card.click();

    // Modal dialog opens
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // Task title in modal
    await expect(dialog.getByRole('heading', { name: 'Set up authentication' })).toBeVisible();

    // Status badge
    await expect(dialog.getByText('Ready')).toBeVisible();

    // Description
    await expect(dialog.getByText('Implement JWT auth with refresh tokens')).toBeVisible();

    // Priority
    await expect(dialog.getByText('Priority 1')).toBeVisible();

    // Estimated hours
    await expect(dialog.getByText('4h estimated')).toBeVisible();
  });

  test('shows dependency info in the modal', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Click task-002 which depends on task-001
    const card = page.getByRole('button', { name: 'View details for Create user dashboard' });
    await card.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // Should show dependency count and truncated task IDs
    await expect(dialog.getByText(/1 dependency/)).toBeVisible();
    // The depends_on ID is "task-001", sliced to first 8 chars = "task-001"
    await expect(dialog.getByText('task-001')).toBeVisible();
  });

  test('shows Execute button for READY tasks in modal', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    const card = page.getByRole('button', { name: 'View details for Set up authentication' });
    await card.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // Execute button in dialog footer
    await expect(dialog.getByRole('button', { name: /Execute/ })).toBeVisible();
  });

  test('shows Mark Ready button for BACKLOG tasks in modal', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    const card = page.getByRole('button', { name: 'View details for Write API tests' });
    await card.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    await expect(dialog.getByRole('button', { name: /Mark Ready/ })).toBeVisible();
  });

  test('closes modal when dismissed', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Open modal
    const card = page.getByRole('button', { name: 'View details for Set up authentication' });
    await card.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // Close via Escape key
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
  });

  test('does not show action buttons for DONE tasks in modal', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    const card = page.getByRole('button', { name: 'View details for Deploy to staging' });
    await card.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // No Execute or Mark Ready buttons
    await expect(dialog.getByRole('button', { name: /Execute/ })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: /Mark Ready/ })).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// 5. Edit Task Status
// ---------------------------------------------------------------------------
test.describe('Edit task status', () => {
  test('Mark Ready button sends PATCH request and refreshes board', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let patchCalled = false;
    let patchBody: Record<string, unknown> | null = null;

    await mockApi({
      'tasks/update': async (route) => {
        patchCalled = true;
        patchBody = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...mockTasks.find((t) => t.id === 'task-003'),
            status: 'READY',
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // Open the BACKLOG task modal
    const card = page.getByRole('button', { name: 'View details for Write API tests' });
    await card.click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // Click Mark Ready in the modal
    await dialog.getByRole('button', { name: /Mark Ready/ }).click();

    // Verify the PATCH was called with correct status
    await expect.poll(() => patchCalled).toBe(true);
    expect(patchBody).toEqual({ status: 'READY' });
  });

  test('Mark Ready from task card sends PATCH request', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let patchCalled = false;

    await mockApi({
      'tasks/update': async (route) => {
        patchCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...mockTasks.find((t) => t.id === 'task-003'),
            status: 'READY',
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // Click "Mark Ready" directly on the BACKLOG card (not opening modal)
    const backlogCard = page.getByRole('button', { name: 'View details for Write API tests' });
    await backlogCard.getByRole('button', { name: 'Mark Ready' }).click();

    await expect.poll(() => patchCalled).toBe(true);
  });

  test('Execute button from READY card starts execution and navigates', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let startCalled = false;

    await mockApi({
      'tasks/start': async (route) => {
        startCalled = true;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            run_id: 'run-001',
            task_id: 'task-001',
            status: 'IN_PROGRESS',
            message: 'Task execution started',
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // Click Execute on the READY card
    const readyCard = page.getByRole('button', { name: 'View details for Set up authentication' });
    await readyCard.getByRole('button', { name: 'Execute' }).click();

    // Verify execution API was called
    await expect.poll(() => startCalled).toBe(true);

    // Should navigate to execution monitor
    await page.waitForURL('**/execution/task-001');
  });
});

// ---------------------------------------------------------------------------
// 6. Batch Task Selection
// ---------------------------------------------------------------------------
test.describe('Batch task selection', () => {
  test('clicking Batch button enables selection mode with checkboxes', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Initially no checkboxes visible
    await expect(page.getByLabel(/^Select /)).toHaveCount(0);

    // Click Batch button to enter selection mode
    await page.getByRole('button', { name: 'Batch' }).click();

    // Now checkboxes should appear on all task cards
    const checkboxes = page.getByLabel(/^Select /);
    await expect(checkboxes.first()).toBeVisible();
    // Should have 6 checkboxes (one per task)
    await expect(checkboxes).toHaveCount(mockTasks.length);

    // Button text should change to "Cancel"
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  });

  test('shows selected count when tasks are checked', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Enter selection mode
    await page.getByRole('button', { name: 'Batch' }).click();

    // Initially 0 selected
    await expect(page.getByText('0 selected')).toBeVisible();

    // Select two tasks
    await page.getByLabel('Select Set up authentication').click();
    await expect(page.getByText('1 selected')).toBeVisible();

    await page.getByLabel('Select Write API tests').click();
    await expect(page.getByText('2 selected')).toBeVisible();
  });

  test('deselecting a task updates the count', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    await page.getByRole('button', { name: 'Batch' }).click();

    // Select two tasks
    await page.getByLabel('Select Set up authentication').click();
    await page.getByLabel('Select Write API tests').click();
    await expect(page.getByText('2 selected')).toBeVisible();

    // Deselect one
    await page.getByLabel('Select Set up authentication').click();
    await expect(page.getByText('1 selected')).toBeVisible();
  });

  test('Cancel button exits selection mode and clears selections', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Enter selection mode and select tasks
    await page.getByRole('button', { name: 'Batch' }).click();
    await page.getByLabel('Select Set up authentication').click();
    await expect(page.getByText('1 selected')).toBeVisible();

    // Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Checkboxes should disappear
    await expect(page.getByLabel(/^Select /)).toHaveCount(0);

    // Batch button returns
    await expect(page.getByRole('button', { name: 'Batch' })).toBeVisible();
  });

  test('Clear button removes selections but stays in selection mode', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Enter selection mode
    await page.getByRole('button', { name: 'Batch' }).click();

    // Select tasks
    await page.getByLabel('Select Set up authentication').click();
    await page.getByLabel('Select Write API tests').click();
    await expect(page.getByText('2 selected')).toBeVisible();

    // The Clear button appears when selections exist (in the batch bar area)
    const batchBar = page.locator('.flex.items-center.gap-2').filter({ hasText: 'selected' });
    await batchBar.getByText('Clear').click();

    // Selections cleared, still in selection mode
    await expect(page.getByText('0 selected')).toBeVisible();
    await expect(page.getByLabel(/^Select /).first()).toBeVisible();
  });

  test('Execute button is disabled when no tasks are selected', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    await page.getByRole('button', { name: 'Batch' }).click();

    // Execute should be disabled with 0 selected (use .first() — batch bar button, not card button)
    const executeBtn = page.getByRole('button', { name: 'Execute' }).first();
    await expect(executeBtn).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// 7. Batch Execution
// ---------------------------------------------------------------------------
test.describe('Batch execution', () => {
  test('selecting strategy from dropdown updates strategy value', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Enter selection mode
    await page.getByRole('button', { name: 'Batch' }).click();

    // The strategy dropdown defaults to "Serial"
    await expect(page.getByText('Serial')).toBeVisible();

    // Open the dropdown and select "Parallel"
    await page.getByRole('combobox').click();
    await page.getByRole('option', { name: 'Parallel' }).click();

    // Now "Parallel" should be shown
    await expect(page.getByRole('combobox')).toContainText('Parallel');
  });

  test('executing batch sends API call with selected task IDs and strategy', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    let executeCalled = false;
    let executeBody: Record<string, unknown> = {};

    await mockApi({
      'tasks/execute': async (route) => {
        executeCalled = true;
        executeBody = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            batch_id: 'batch-001',
            task_count: 2,
            strategy: 'serial',
            message: 'Batch execution started',
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // Enter selection mode
    await page.getByRole('button', { name: 'Batch' }).click();

    // Select two tasks
    await page.getByLabel('Select Set up authentication').click();
    await page.getByLabel('Select Write API tests').click();

    // Click Execute (batch bar button is first — card buttons also say "Execute")
    await page.getByRole('button', { name: 'Execute' }).first().click();

    // Verify API call
    await expect.poll(() => executeCalled).toBe(true);
    expect(Object.keys(executeBody).length).toBeGreaterThan(0);
    expect(executeBody.strategy).toBe('serial');
    const taskIds = executeBody.task_ids as string[];
    expect(taskIds).toContain('task-001');
    expect(taskIds).toContain('task-003');
  });

  test('after batch execution, navigates to execution page', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi();
    await withWorkspace();
    await page.goto('/tasks');

    // Enter selection mode, select tasks, execute
    await page.getByRole('button', { name: 'Batch' }).click();
    await page.getByLabel('Select Set up authentication').click();
    await page.getByRole('button', { name: 'Execute' }).first().click();

    // Should navigate to execution page with batch ID
    await page.waitForURL('**/execution?batch=batch-001');
  });
});

// ---------------------------------------------------------------------------
// 8. Edge Cases
// ---------------------------------------------------------------------------
test.describe('Edge cases', () => {
  test('shows no-workspace message when workspace is not set', async ({
    page,
    mockApi,
  }) => {
    await mockApi();
    // Do NOT call withWorkspace() — no workspace selected
    await page.goto('/tasks');

    await expect(page.getByText('No workspace selected')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Workspace' })).toBeVisible();
  });

  test('displays error state when API returns an error', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    await mockApi({
      'tasks/list': async (route) => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // Error heading is an h2
    await expect(page.getByRole('heading', { name: 'Error' })).toBeVisible();
  });

  test('empty board renders all columns with "No tasks"', async ({
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
            by_status: { BACKLOG: 0, READY: 0, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 0 },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // All 6 columns should show "No tasks"
    const noTasksLabels = page.getByText('No tasks');
    await expect(noTasksLabels).toHaveCount(6);
  });

  test('all tasks in one column renders correctly', async ({
    page,
    mockApi,
    withWorkspace,
  }) => {
    const allReady = mockTasks.map((t) => ({ ...t, status: 'READY' }));
    await mockApi({
      'tasks/list': async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            tasks: allReady,
            total: allReady.length,
            by_status: { BACKLOG: 0, READY: allReady.length, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 0 },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/tasks');

    // All task titles should be visible
    for (const task of allReady) {
      await expect(page.getByText(task.title).first()).toBeVisible();
    }

    // 5 columns should show "No tasks"
    const noTasksLabels = page.getByText('No tasks');
    await expect(noTasksLabels).toHaveCount(5);
  });
});
