/**
 * Unit tests for CheckpointRestore component (T103)
 * Updated for emoji-to-Hugeicons migration: icons now use Hugeicons components
 *
 * Tests:
 * - Diff preview display
 * - Confirmation dialog
 * - Restore action
 * - Cancel action
 *
 * Part of Sprint 10 Phase 4 - Checkpoint System (Frontend)
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CheckpointRestore } from '../../../src/components/checkpoints/CheckpointRestore';
import * as checkpointsApi from '../../../src/api/checkpoints';
import type { Checkpoint, CheckpointDiff, RestoreCheckpointResponse } from '../../../src/types/checkpoints';

// Mock Hugeicons
jest.mock('@hugeicons/react', () => {
  const React = require('react');
  return {
    Alert02Icon: ({ className }: { className?: string }) => (
      <svg data-testid="Alert02Icon" className={className} aria-hidden="true" />
    ),
  };
});

// Mock the API module
jest.mock('../../../src/api/checkpoints');

const mockGetCheckpointDiff = checkpointsApi.getCheckpointDiff as jest.MockedFunction<
  typeof checkpointsApi.getCheckpointDiff
>;
const mockRestoreCheckpoint = checkpointsApi.restoreCheckpoint as jest.MockedFunction<
  typeof checkpointsApi.restoreCheckpoint
>;

describe('CheckpointRestore', () => {
  const mockCheckpoint: Checkpoint = {
    id: 1,
    project_id: 123,
    name: 'Sprint 10 Phase 3 Complete',
    description: 'All backend tests passing',
    trigger: 'manual',
    git_commit: 'abc123def456',
    database_backup_path: '/backups/checkpoint_1.db',
    context_snapshot_path: '/backups/checkpoint_1_context.json',
    metadata: {
      project_id: 123,
      phase: 'Phase 3',
      tasks_completed: 45,
      tasks_total: 60,
      agents_active: ['backend-001', 'test-001'],
      last_task_completed: 'T097: Add checkpoint API tests',
      context_items_count: 150,
      total_cost_usd: 12.5,
    },
    created_at: '2025-11-23T10:30:00Z',
  };

  const mockDiff: CheckpointDiff = {
    files_changed: 5,
    insertions: 120,
    deletions: 45,
    diff: `diff --git a/codeframe/agents/worker_agent.py b/codeframe/agents/worker_agent.py
index abc123d..def456e 100644
--- a/codeframe/agents/worker_agent.py
+++ b/codeframe/agents/worker_agent.py
@@ -10,7 +10,7 @@ class WorkerAgent:
-    async def execute_task(self):
+    async def execute_task(self, task_id: int):
         pass`,
  };

  const mockOnClose = jest.fn();
  const mockOnRestoreComplete = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useRealTimers();
  });

  it('test_loads_and_displays_diff', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    // ASSERT: Loading state initially
    expect(screen.getByText('Loading diff preview...')).toBeInTheDocument();

    // Wait for diff to load
    await waitFor(() => {
      expect(screen.queryByText('Loading diff preview...')).not.toBeInTheDocument();
    });

    // Verify diff stats are displayed
    expect(screen.getByText('5')).toBeInTheDocument(); // files_changed
    expect(screen.getByText('+120')).toBeInTheDocument(); // insertions
    expect(screen.getByText('-45')).toBeInTheDocument(); // deletions

    // Verify diff content is shown
    expect(screen.getByText(/diff --git a\/codeframe\/agents\/worker_agent\.py/)).toBeInTheDocument();
  });

  it('test_displays_checkpoint_details', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    // ASSERT: Checkpoint details shown
    expect(screen.getByText('Sprint 10 Phase 3 Complete')).toBeInTheDocument();
    expect(screen.getByText('Phase 3')).toBeInTheDocument();
    expect(screen.getByText('45/60')).toBeInTheDocument(); // tasks
    expect(screen.getByText('abc123d')).toBeInTheDocument(); // git commit (short)
  });

  it('test_shows_warning_message', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    // ASSERT: Warning message is shown (Alert02Icon is decorative, so we check text)
    await waitFor(() => {
      expect(screen.getByText('Warning: Destructive Operation')).toBeInTheDocument();
      expect(screen.getByTestId('restore-warning')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/This will restore your project to the state at checkpoint creation/)
    ).toBeInTheDocument();
  });

  it('test_diff_load_error', async () => {
    // ARRANGE
    const errorMessage = 'Failed to load diff: 404 Not Found';
    mockGetCheckpointDiff.mockRejectedValueOnce(new Error(errorMessage));

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    // ASSERT: Wait for error to appear
    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    // Confirm button should be disabled
    const confirmButton = screen.getByText('Confirm Restore');
    expect(confirmButton).toBeDisabled();
  });

  it('test_cancel_action', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);
    const user = userEvent.setup();

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('Loading diff preview...')).not.toBeInTheDocument();
    });

    // Click cancel
    const cancelButton = screen.getByText('Cancel');
    await user.click(cancelButton);

    // ASSERT: onClose was called
    expect(mockOnClose).toHaveBeenCalled();
    expect(mockOnRestoreComplete).not.toHaveBeenCalled();
  });

  it('test_restore_success', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);
    const mockRestoreResponse: RestoreCheckpointResponse = {
      success: true,
      git_commit: 'abc123def456',
      restored_at: '2025-11-23T12:00:00Z',
      message: 'Checkpoint restored successfully',
    };
    mockRestoreCheckpoint.mockResolvedValueOnce(mockRestoreResponse);

    jest.useFakeTimers();
    const user = userEvent.setup({ delay: null }); // Disable delay for fake timers

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('Loading diff preview...')).not.toBeInTheDocument();
    });

    // Click confirm restore
    const confirmButton = screen.getByText('Confirm Restore');
    await user.click(confirmButton);

    // ASSERT: API was called
    await waitFor(() => {
      expect(mockRestoreCheckpoint).toHaveBeenCalledWith(123, 1, true);
    });

    // Success message shown
    await waitFor(() => {
      expect(screen.getByText('Checkpoint restored successfully!')).toBeInTheDocument();
    });

    // Fast-forward 2 seconds (auto-close delay)
    jest.advanceTimersByTime(2000);

    // onRestoreComplete was called
    await waitFor(() => {
      expect(mockOnRestoreComplete).toHaveBeenCalled();
    });

    jest.useRealTimers();
  });

  it('test_restore_error', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);
    const errorMessage = 'Failed to restore: Git conflict detected';
    mockRestoreCheckpoint.mockRejectedValueOnce(new Error(errorMessage));
    const user = userEvent.setup();

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('Loading diff preview...')).not.toBeInTheDocument();
    });

    // Click confirm restore
    const confirmButton = screen.getByText('Confirm Restore');
    await user.click(confirmButton);

    // ASSERT: Error message shown
    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    // onRestoreComplete was NOT called
    expect(mockOnRestoreComplete).not.toHaveBeenCalled();
  });

  it('test_confirm_button_disabled_while_loading', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    // ASSERT: Confirm button is disabled while loading
    const confirmButton = screen.getByText('Confirm Restore');
    expect(confirmButton).toBeDisabled();
  });

  it('test_confirm_button_disabled_while_restoring', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);
    mockRestoreCheckpoint.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );
    const user = userEvent.setup();

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('Loading diff preview...')).not.toBeInTheDocument();
    });

    // Click confirm restore
    const confirmButton = screen.getByText('Confirm Restore');
    await user.click(confirmButton);

    // ASSERT: Button shows "Restoring..." and is disabled
    await waitFor(() => {
      expect(screen.getByText('Restoring...')).toBeInTheDocument();
    });

    const restoringButton = screen.getByText('Restoring...');
    expect(restoringButton).toBeDisabled();
  });

  it('test_close_button_changes_after_success', async () => {
    // ARRANGE
    mockGetCheckpointDiff.mockResolvedValueOnce(mockDiff);
    const mockRestoreResponse: RestoreCheckpointResponse = {
      success: true,
      git_commit: 'abc123def456',
      restored_at: '2025-11-23T12:00:00Z',
      message: 'Checkpoint restored successfully',
    };
    mockRestoreCheckpoint.mockResolvedValueOnce(mockRestoreResponse);
    const user = userEvent.setup();

    // ACT
    render(
      <CheckpointRestore
        projectId={123}
        checkpoint={mockCheckpoint}
        onClose={mockOnClose}
        onRestoreComplete={mockOnRestoreComplete}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText('Loading diff preview...')).not.toBeInTheDocument();
    });

    // Initially shows "Cancel"
    expect(screen.getByText('Cancel')).toBeInTheDocument();

    // Click confirm restore
    const confirmButton = screen.getByText('Confirm Restore');
    await user.click(confirmButton);

    // Wait for success
    await waitFor(() => {
      expect(screen.getByText('Checkpoint restored successfully!')).toBeInTheDocument();
    });

    // ASSERT: Cancel button now shows "Close"
    expect(screen.getByText('Close')).toBeInTheDocument();
    expect(screen.queryByText('Cancel')).not.toBeInTheDocument();

    // Confirm button is hidden
    expect(screen.queryByText('Confirm Restore')).not.toBeInTheDocument();
  });
});
