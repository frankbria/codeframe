/**
 * E2E tests for the Execution Monitor — the most critical test area.
 *
 * Covers:
 * - Single task execution page rendering
 * - SSE event stream rendering (planning, execution, verification, completion)
 * - File change, shell command, and verification events
 * - Progress indicator phase transitions
 * - Blocker interrupt pattern (inline answer form)
 * - Completion and failure banners
 * - Stop execution confirmation dialog
 * - Batch execution monitor
 * - Error/failure state rendering
 */
import { test, expect } from './fixtures/test-setup';
import { Route } from '@playwright/test';

// ── Helpers ──────────────────────────────────────────────────────────────

/**
 * Build an SSE response body from an array of typed execution events.
 * Uses unnamed events (no `event:` line) so the browser EventSource
 * fires `onmessage`, which is what useEventSource listens on.
 */
function buildSSEBody(events: Record<string, unknown>[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
}

/** ISO timestamp for deterministic test data. */
const TS = '2026-02-03T12:00:00Z';

/** Standard planning → execution → verification → completion event sequence. */
const fullEventSequence: Record<string, unknown>[] = [
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'planning', step: 1, total_steps: 3, message: 'Analyzing task context...' },
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'planning', step: 2, total_steps: 3, message: 'Generating implementation plan...' },
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'planning', step: 3, total_steps: 3, message: 'Plan complete' },
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 2, message: 'Creating auth module...' },
  { event_type: 'output', task_id: 'task-001', timestamp: TS, stream: 'stdout', line: 'Created file: src/auth.ts' },
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 2, total_steps: 2, message: 'Running shell commands...' },
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'verification', step: 1, total_steps: 2, message: 'Running ruff...' },
  { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'verification', step: 2, total_steps: 2, message: 'Running pytest...' },
  { event_type: 'completion', task_id: 'task-001', timestamp: TS, status: 'completed', duration_seconds: 45, files_modified: ['src/auth.ts'] },
];

/** Override for the tasks/stream route that sends well-formed SSE events. */
function streamOverride(events: Record<string, unknown>[]) {
  return {
    'tasks/stream': async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        headers: {
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
        body: buildSSEBody(events),
      });
    },
  };
}

// ── Tests ────────────────────────────────────────────────────────────────

test.describe('Single Task Execution Page', () => {
  test('renders header with task title and description', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // The header shows the task title from the mock data
    await expect(page.getByRole('heading', { name: 'Set up authentication' })).toBeVisible();
    // Description is shown below the title
    await expect(page.getByText('Implement JWT auth with refresh tokens')).toBeVisible();
  });

  test('shows "Loading task..." before task data arrives', async ({ page, mockApi, withWorkspace }) => {
    // Override task GET to delay indefinitely
    await mockApi({
      ...streamOverride([]),
      'tasks/get': async (route: Route) => {
        // Never fulfill — simulates loading state
        await new Promise(() => {});
      },
    });
    await withWorkspace();
    await page.goto('/execution/task-001');

    await expect(page.getByText('Loading task...')).toBeVisible();
  });

  test('shows stop button that is enabled during execution', async ({ page, mockApi, withWorkspace }) => {
    // Only send progress events (no completion) so execution is still "active"
    const activeEvents = fullEventSequence.filter((e) => e.event_type !== 'completion');
    await mockApi(streamOverride(activeEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const stopButton = page.getByRole('button', { name: /stop/i });
    await expect(stopButton).toBeVisible();
    await expect(stopButton).toBeEnabled();
  });
});

test.describe('SSE Event Stream Rendering', () => {
  test('renders event stream container with log role', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const eventLog = page.getByRole('log', { name: 'Execution event stream' });
    await expect(eventLog).toBeVisible();
  });

  test('displays planning events with plan icon', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Planning events should show messages
    await expect(page.getByText('Analyzing task context...')).toBeVisible();
    await expect(page.getByText('Generating implementation plan...')).toBeVisible();
    await expect(page.getByText('Plan complete')).toBeVisible();
  });

  test('displays execution step events with step counters', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Execution step messages
    await expect(page.getByText('Creating auth module...')).toBeVisible();
    await expect(page.getByText('Running shell commands...')).toBeVisible();
  });

  test('shows "Waiting for events..." when stream is empty', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride([]));
    await withWorkspace();
    await page.goto('/execution/task-001');

    await expect(page.getByText('Waiting for events...')).toBeVisible();
  });
});

test.describe('File Change Events', () => {
  test('renders file change with file path when message matches pattern', async ({ page, mockApi, withWorkspace }) => {
    const events: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 1, message: 'Creating file: src/auth/middleware.py' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // The FileChangeEvent extracts the path from the message (shown in both event wrapper and detail)
    await expect(page.getByText('src/auth/middleware.py').first()).toBeVisible();
    // Should have a "View Diff" toggle button
    await expect(page.getByRole('button', { name: 'View Diff' })).toBeVisible();
  });

  test('toggles diff view on click', async ({ page, mockApi, withWorkspace }) => {
    const events: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 1, message: 'Editing file: src/utils.ts' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const viewDiffButton = page.getByRole('button', { name: 'View Diff' });
    await viewDiffButton.click();

    // After expanding, the button text changes to "Hide"
    await expect(page.getByRole('button', { name: 'Hide' })).toBeVisible();
  });
});

test.describe('Shell Command Events', () => {
  test('renders stdout output event with Show toggle', async ({ page, mockApi, withWorkspace }) => {
    const events: Record<string, unknown>[] = [
      { event_type: 'output', task_id: 'task-001', timestamp: TS, stream: 'stdout', line: 'All tests passed (12/12)' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // stdout label
    await expect(page.getByText('stdout')).toBeVisible();
    // Show button for expanding
    await expect(page.getByRole('button', { name: 'Show' })).toBeVisible();
  });

  test('stderr output is expanded by default', async ({ page, mockApi, withWorkspace }) => {
    const events: Record<string, unknown>[] = [
      { event_type: 'output', task_id: 'task-001', timestamp: TS, stream: 'stderr', line: 'Error: module not found' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // stderr is auto-expanded, so the output text should be visible
    await expect(page.getByText('Error: module not found')).toBeVisible();
    // Button should say "Hide" since it is already expanded
    await expect(page.getByRole('button', { name: 'Hide' })).toBeVisible();
  });
});

test.describe('Verification Events', () => {
  test('renders passing verification with checkmark styling', async ({ page, mockApi, withWorkspace }) => {
    const events: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'verification', step: 1, total_steps: 1, message: 'ruff check: passed' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    await expect(page.getByText('ruff check: passed').first()).toBeVisible();
  });

  test('renders failing verification with error styling', async ({ page, mockApi, withWorkspace }) => {
    const events: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'verification', step: 1, total_steps: 1, message: 'pytest: failed (3 errors)' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    await expect(page.getByText('pytest: failed (3 errors)').first()).toBeVisible();
  });
});

test.describe('Progress Indicator', () => {
  test('shows step progress and percentage', async ({ page, mockApi, withWorkspace }) => {
    // Send only partial events so progress is mid-stream
    const partialEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 4, message: 'Step one...' },
    ];
    await mockApi(streamOverride(partialEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // ProgressIndicator shows "Step X of Y"
    await expect(page.getByText(/Step 1 of 4/)).toBeVisible();
    // Percentage is shown
    await expect(page.getByText('25%')).toBeVisible();
  });

  test('updates progress as events arrive', async ({ page, mockApi, withWorkspace }) => {
    // Two progress events: step 1/3 then step 3/3
    const events: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'planning', step: 1, total_steps: 3, message: 'Starting...' },
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'planning', step: 3, total_steps: 3, message: 'Done planning' },
    ];
    await mockApi(streamOverride(events));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Should show final step progress
    await expect(page.getByText(/Step 3 of 3/)).toBeVisible();
    await expect(page.getByText('100%')).toBeVisible();
  });
});

test.describe('Blocker During Execution', () => {
  test('shows blocker interrupt pattern with inline answer form', async ({ page, mockApi, withWorkspace }) => {
    const blockerEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 2, message: 'Working...' },
      { event_type: 'blocker', task_id: 'task-001', timestamp: TS, blocker_id: 1, question: 'Which database should we use?', context: 'The project needs a database for user storage.' },
    ];
    await mockApi(streamOverride(blockerEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Blocker header
    await expect(page.getByText('Agent needs your help')).toBeVisible();
    // Question text
    await expect(page.getByText('Which database should we use?')).toBeVisible();
    // Context text
    await expect(page.getByText('The project needs a database for user storage.')).toBeVisible();
    // Answer textarea
    await expect(page.getByLabel('Your answer to the blocker question')).toBeVisible();
    // Submit button (disabled until text is entered)
    const answerButton = page.getByRole('button', { name: 'Answer Blocker' });
    await expect(answerButton).toBeVisible();
    await expect(answerButton).toBeDisabled();
    // Status text
    await expect(page.getByText(/Execution paused/)).toBeVisible();
  });

  test('enables submit button when answer text is entered', async ({ page, mockApi, withWorkspace }) => {
    const blockerEvents: Record<string, unknown>[] = [
      { event_type: 'blocker', task_id: 'task-001', timestamp: TS, blocker_id: 1, question: 'Which auth provider?' },
    ];
    await mockApi(streamOverride(blockerEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const textarea = page.getByLabel('Your answer to the blocker question');
    const answerButton = page.getByRole('button', { name: 'Answer Blocker' });

    // Initially disabled
    await expect(answerButton).toBeDisabled();

    // Type an answer
    await textarea.fill('Use Google OAuth');
    await expect(answerButton).toBeEnabled();
  });

  test('submits blocker answer and shows confirmation', async ({ page, mockApi, withWorkspace }) => {
    const blockerEvents: Record<string, unknown>[] = [
      { event_type: 'blocker', task_id: 'task-001', timestamp: TS, blocker_id: 1, question: 'Which auth provider?' },
    ];
    await mockApi(streamOverride(blockerEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const textarea = page.getByLabel('Your answer to the blocker question');
    await textarea.fill('Use Google OAuth');

    const answerButton = page.getByRole('button', { name: 'Answer Blocker' });
    await answerButton.click();

    // After successful submission, shows confirmation message
    await expect(page.getByText('Blocker answered. Execution resuming...')).toBeVisible();
  });
});

test.describe('Completion State', () => {
  test('shows success banner with duration and action buttons', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Completion banner (use .first() to skip Next.js route announcer which also has role="alert")
    const banner = page.getByRole('alert').first();
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Execution completed successfully');
    await expect(banner).toContainText('45s');

    // Action buttons
    await expect(page.getByRole('button', { name: 'View Changes' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Back to Tasks' })).toBeVisible();
  });

  test('shows completion event in stream with file count', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Completion event in the stream body
    await expect(page.getByText('Task completed successfully')).toBeVisible();
    await expect(page.getByText('1 file modified')).toBeVisible();
  });

  test('disables stop button after completion', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Wait for completion
    await expect(page.getByText('Task completed successfully')).toBeVisible();

    // Stop button should be disabled
    const stopButton = page.getByRole('button', { name: /stop/i });
    await expect(stopButton).toBeDisabled();
  });

  test('shows changed files in sidebar', async ({ page, mockApi, withWorkspace }) => {
    await mockApi(streamOverride(fullEventSequence));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Wait for completion to populate changedFiles
    await expect(page.getByText('Task completed successfully')).toBeVisible();

    // ChangesSidebar shows file count and file name
    await expect(page.getByText('Changes (1)')).toBeVisible();
    await expect(page.getByTitle('src/auth.ts')).toBeVisible();
  });
});

test.describe('Error / Failure State', () => {
  test('shows failure banner when execution fails', async ({ page, mockApi, withWorkspace }) => {
    const failureEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 2, message: 'Working...' },
      { event_type: 'completion', task_id: 'task-001', timestamp: TS, status: 'failed', duration_seconds: 12, files_modified: [] },
    ];
    await mockApi(streamOverride(failureEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const banner = page.getByRole('alert').first();
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Execution failed');
    await expect(banner).toContainText('12s');
    await expect(page.getByRole('button', { name: 'Back to Tasks' })).toBeVisible();
  });

  test('shows error event with message and traceback', async ({ page, mockApi, withWorkspace }) => {
    const errorEvents: Record<string, unknown>[] = [
      {
        event_type: 'error',
        task_id: 'task-001',
        timestamp: TS,
        error: 'LLM API rate limit exceeded',
        error_type: 'RateLimitError',
        traceback: 'File "agent.py", line 42\n  raise RateLimitError()',
      },
    ];
    await mockApi(streamOverride(errorEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    await expect(page.getByText('LLM API rate limit exceeded')).toBeVisible();
    // Traceback is rendered in a <pre> element
    await expect(page.getByText(/raise RateLimitError/)).toBeVisible();
  });

  test('shows blocked banner when execution is blocked', async ({ page, mockApi, withWorkspace }) => {
    const blockedEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 2, message: 'Working...' },
      { event_type: 'completion', task_id: 'task-001', timestamp: TS, status: 'blocked', duration_seconds: 30, files_modified: [] },
    ];
    await mockApi(streamOverride(blockedEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    const banner = page.getByRole('alert').first();
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Execution blocked');
    await expect(banner).toContainText('blocker was raised');
  });
});

test.describe('Stop Execution', () => {
  test('clicking stop opens confirmation dialog', async ({ page, mockApi, withWorkspace }) => {
    // Keep execution active (no completion event)
    const activeEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 3, message: 'Working...' },
    ];
    await mockApi(streamOverride(activeEvents));
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Click the stop button to open the AlertDialog
    await page.getByRole('button', { name: /stop/i }).click();

    // Confirmation dialog appears
    await expect(page.getByText('Stop Execution?')).toBeVisible();
    await expect(page.getByText(/stop the AI agent/)).toBeVisible();
    // Cancel and confirm buttons
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Stop Execution' })).toBeVisible();
  });

  test('confirming stop calls the stop API', async ({ page, mockApi, withWorkspace }) => {
    const activeEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 3, message: 'Working...' },
    ];

    let stopCalled = false;
    await mockApi({
      ...streamOverride(activeEvents),
      'tasks/stop': async (route: Route) => {
        stopCalled = true;
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      },
    });
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Open dialog
    await page.getByRole('button', { name: /stop/i }).click();
    // Confirm
    await page.getByRole('button', { name: 'Stop Execution' }).click();

    // Verify the stop API was called
    await expect.poll(() => stopCalled).toBe(true);
  });

  test('cancelling the dialog does not call stop API', async ({ page, mockApi, withWorkspace }) => {
    const activeEvents: Record<string, unknown>[] = [
      { event_type: 'progress', task_id: 'task-001', timestamp: TS, phase: 'execution', step: 1, total_steps: 3, message: 'Working...' },
    ];

    let stopCalled = false;
    await mockApi({
      ...streamOverride(activeEvents),
      'tasks/stop': async (route: Route) => {
        stopCalled = true;
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      },
    });
    await withWorkspace();
    await page.goto('/execution/task-001');

    // Open dialog
    await page.getByRole('button', { name: /stop/i }).click();
    // Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Dialog should close
    await expect(page.getByText('Stop Execution?')).not.toBeVisible();
    // Stop should not have been called
    expect(stopCalled).toBe(false);
  });
});

test.describe('Batch Execution Monitor', () => {
  test('renders batch header with task count and strategy', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'batches/get': async (route: Route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'batch-001',
            workspace_id: 'ws-e2e-001',
            task_ids: ['task-001', 'task-003'],
            status: 'running',
            strategy: 'serial',
            max_parallel: 1,
            on_failure: 'stop',
            started_at: '2026-02-03T00:00:00Z',
            completed_at: null,
            results: { 'task-001': 'COMPLETED', 'task-003': 'IN_PROGRESS' },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/execution?batch=batch-001');

    // Batch header
    await expect(page.getByText('Batch Execution (2 tasks)')).toBeVisible();
    await expect(page.getByText(/Strategy: serial/)).toBeVisible();
    await expect(page.getByText(/1\/2 complete/)).toBeVisible();
  });

  test('shows task rows with status indicators', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'batches/get': async (route: Route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'batch-001',
            workspace_id: 'ws-e2e-001',
            task_ids: ['task-001', 'task-003'],
            status: 'running',
            strategy: 'serial',
            max_parallel: 1,
            on_failure: 'stop',
            started_at: '2026-02-03T00:00:00Z',
            completed_at: null,
            results: { 'task-001': 'COMPLETED', 'task-003': 'IN_PROGRESS' },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/execution?batch=batch-001');

    // Task rows with titles from mock data
    await expect(page.getByText('Set up authentication')).toBeVisible();
    await expect(page.getByText('Write API tests')).toBeVisible();

    // Status labels
    await expect(page.getByText('Completed')).toBeVisible();
    await expect(page.getByText('Running')).toBeVisible();
  });

  test('shows Stop Batch and Cancel Batch buttons when active', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'batches/get': async (route: Route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'batch-001',
            workspace_id: 'ws-e2e-001',
            task_ids: ['task-001', 'task-003'],
            status: 'running',
            strategy: 'serial',
            max_parallel: 1,
            on_failure: 'stop',
            started_at: '2026-02-03T00:00:00Z',
            completed_at: null,
            results: { 'task-001': 'COMPLETED', 'task-003': 'IN_PROGRESS' },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/execution?batch=batch-001');

    await expect(page.getByRole('button', { name: 'Stop Batch' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel Batch' })).toBeVisible();
  });

  test('shows Back to Tasks button when batch is completed', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'batches/get': async (route: Route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'batch-001',
            workspace_id: 'ws-e2e-001',
            task_ids: ['task-001', 'task-003'],
            status: 'COMPLETED',
            strategy: 'serial',
            max_parallel: 1,
            on_failure: 'stop',
            started_at: '2026-02-03T00:00:00Z',
            completed_at: '2026-02-03T00:05:00Z',
            results: { 'task-001': 'COMPLETED', 'task-003': 'COMPLETED' },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/execution?batch=batch-001');

    // No Stop/Cancel buttons when completed
    await expect(page.getByRole('button', { name: 'Stop Batch' })).not.toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel Batch' })).not.toBeVisible();
    // Back to Tasks is visible
    await expect(page.getByRole('button', { name: 'Back to Tasks' })).toBeVisible();
  });

  test('expands task row to show event stream or status text', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'batches/get': async (route: Route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'batch-001',
            workspace_id: 'ws-e2e-001',
            task_ids: ['task-001', 'task-003'],
            status: 'COMPLETED',
            strategy: 'serial',
            max_parallel: 1,
            on_failure: 'stop',
            started_at: '2026-02-03T00:00:00Z',
            completed_at: '2026-02-03T00:05:00Z',
            results: { 'task-001': 'COMPLETED', 'task-003': 'FAILED' },
          }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/execution?batch=batch-001');

    // Click on completed task row to expand
    await page.getByText('Set up authentication').click();
    await expect(page.getByText('Task completed successfully.')).toBeVisible();

    // Click on failed task row to expand
    await page.getByText('Write API tests').click();
    await expect(page.getByText('Task failed. Check diagnostics for details.')).toBeVisible();
  });

  test('shows batch load error message', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'batches/get': async (route: Route) => {
        await route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal error"}' });
      },
    });
    await withWorkspace();
    await page.goto('/execution?batch=batch-001');

    await expect(page.getByText('Failed to load batch details')).toBeVisible();
  });
});

test.describe('Execution Landing Page', () => {
  test('shows "No workspace selected" when no workspace is set', async ({ page, mockApi }) => {
    await mockApi(streamOverride([]));
    // Do NOT call withWorkspace — no workspace in localStorage
    await page.goto('/execution');

    await expect(page.getByText('No workspace selected.')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Select a workspace' })).toBeVisible();
  });

  test('shows empty state when no active execution', async ({ page, mockApi, withWorkspace }) => {
    // Override tasks list to return no IN_PROGRESS tasks
    await mockApi({
      ...streamOverride([]),
      'tasks/list': async (route: Route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ tasks: [], total: 0, by_status: {} }),
        });
      },
    });
    await withWorkspace();
    await page.goto('/execution');

    await expect(page.getByText('No active execution')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Task Board' })).toBeVisible();
  });

  test('task error page shows "Task not found" with back link', async ({ page, mockApi, withWorkspace }) => {
    await mockApi({
      ...streamOverride([]),
      'tasks/get': async (route: Route) => {
        await route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Not found"}' });
      },
    });
    await withWorkspace();
    await page.goto('/execution/nonexistent-task');

    await expect(page.getByText('Task not found or failed to load.')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Back to Task Board' })).toBeVisible();
  });
});

test.describe('Disconnection Banner', () => {
  test('shows reconnection banner when SSE connection is lost', async ({ page, mockApi, withWorkspace }) => {
    // SSE stream that returns an error to simulate disconnect
    await mockApi({
      'tasks/stream': async (route: Route) => {
        await route.fulfill({ status: 500, contentType: 'text/plain', body: 'Server error' });
      },
    });
    await withWorkspace();
    await page.goto('/execution/task-001');

    // The disconnection banner appears when agentState is DISCONNECTED
    // (SSE status transitions to error/closed)
    await expect(page.getByText('Connection lost. Events may be missing.')).toBeVisible({ timeout: 15000 });
    await expect(page.getByRole('button', { name: 'Reconnect' })).toBeVisible();
  });
});
