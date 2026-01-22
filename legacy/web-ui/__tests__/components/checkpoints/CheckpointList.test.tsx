/**
 * Unit tests for CheckpointList component (T102)
 *
 * Tests:
 * - Renders checkpoint list display
 * - Create checkpoint action
 * - Delete checkpoint action
 * - Loading and error states
 *
 * Part of Sprint 10 Phase 4 - Checkpoint System (Frontend)
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CheckpointList } from '../../../src/components/checkpoints/CheckpointList';
import * as checkpointsApi from '../../../src/api/checkpoints';
import type { Checkpoint } from '../../../src/types/checkpoints';

// Mock the API module
jest.mock('../../../src/api/checkpoints');
jest.mock('../../../src/components/checkpoints/CheckpointRestore', () => ({
  CheckpointRestore: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="checkpoint-restore">
      <button onClick={onClose}>Close Restore</button>
    </div>
  ),
}));
jest.mock('../../../src/components/checkpoints/DeleteConfirmationDialog', () => ({
  DeleteConfirmationDialog: ({ isOpen, checkpointName, onConfirm, onCancel, isDeleting }: any) => (
    isOpen ? (
      <div data-testid="delete-confirmation-dialog">
        <p>Are you sure you want to delete checkpoint "{checkpointName}"?</p>
        <button onClick={onConfirm} disabled={isDeleting}>{isDeleting ? 'Deleting...' : 'Confirm'}</button>
        <button onClick={onCancel} disabled={isDeleting}>Cancel</button>
      </div>
    ) : null
  ),
}));

const mockListCheckpoints = checkpointsApi.listCheckpoints as jest.MockedFunction<
  typeof checkpointsApi.listCheckpoints
>;
const mockCreateCheckpoint = checkpointsApi.createCheckpoint as jest.MockedFunction<
  typeof checkpointsApi.createCheckpoint
>;
const mockDeleteCheckpoint = checkpointsApi.deleteCheckpoint as jest.MockedFunction<
  typeof checkpointsApi.deleteCheckpoint
>;

describe('CheckpointList', () => {
  const mockCheckpoints: Checkpoint[] = [
    {
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
    },
    {
      id: 2,
      project_id: 123,
      name: 'Auto Checkpoint - Phase 2',
      trigger: 'auto',
      git_commit: 'def789ghi012',
      database_backup_path: '/backups/checkpoint_2.db',
      context_snapshot_path: '/backups/checkpoint_2_context.json',
      metadata: {
        project_id: 123,
        phase: 'Phase 2',
        tasks_completed: 30,
        tasks_total: 60,
        agents_active: ['backend-001'],
        context_items_count: 100,
        total_cost_usd: 8.75,
      },
      created_at: '2025-11-22T14:15:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('test_renders_checkpoint_list', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce(mockCheckpoints);

    // ACT
    render(<CheckpointList projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Verify checkpoint names are displayed
    expect(screen.getByText('Sprint 10 Phase 3 Complete')).toBeInTheDocument();
    expect(screen.getByText('Auto Checkpoint - Phase 2')).toBeInTheDocument();

    // Verify checkpoint descriptions
    expect(screen.getByText('All backend tests passing')).toBeInTheDocument();

    // Verify metadata is shown
    expect(screen.getByText('45/60')).toBeInTheDocument(); // tasks
    expect(screen.getByText('$12.50')).toBeInTheDocument(); // cost
  });

  it('test_shows_loading_state', () => {
    // ARRANGE
    mockListCheckpoints.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    // ACT
    render(<CheckpointList projectId={123} />);

    // ASSERT: Loading state is shown
    expect(screen.getByText('Loading checkpoints...')).toBeInTheDocument();
  });

  it('test_shows_error_state', async () => {
    // ARRANGE
    const errorMessage = 'Failed to list checkpoints: 500 Internal Server Error';
    mockListCheckpoints.mockRejectedValueOnce(new Error(errorMessage));

    // ACT
    render(<CheckpointList projectId={123} />);

    // ASSERT: Wait for error to appear
    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });
  });

  it('test_shows_empty_state', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce([]);

    // ACT
    render(<CheckpointList projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    expect(screen.getByText('No checkpoints yet. Create your first checkpoint!')).toBeInTheDocument();
  });

  it('test_create_checkpoint_dialog_opens', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce(mockCheckpoints);
    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Click create button
    const createButton = screen.getByText('Create Checkpoint');
    await user.click(createButton);

    // ASSERT: Dialog is shown
    expect(screen.getByText('Create New Checkpoint')).toBeInTheDocument();
    expect(screen.getByLabelText('Name *')).toBeInTheDocument();
    expect(screen.getByLabelText('Description (optional)')).toBeInTheDocument();
  });

  it('test_create_checkpoint_success', async () => {
    // ARRANGE
    mockListCheckpoints
      .mockResolvedValueOnce(mockCheckpoints)
      .mockResolvedValueOnce([...mockCheckpoints, { ...mockCheckpoints[0], id: 3 }]);

    const newCheckpoint: Checkpoint = {
      ...mockCheckpoints[0],
      id: 3,
      name: 'New Checkpoint',
      description: 'Test checkpoint',
    };
    mockCreateCheckpoint.mockResolvedValueOnce(newCheckpoint);

    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Open create dialog
    await user.click(screen.getByText('Create Checkpoint'));

    // Fill form
    const nameInput = screen.getByLabelText('Name *') as HTMLInputElement;
    const descriptionInput = screen.getByLabelText('Description (optional)') as HTMLTextAreaElement;

    await user.type(nameInput, 'New Checkpoint');
    await user.type(descriptionInput, 'Test checkpoint');

    // Submit form (find button by role and name)
    const createSubmitButton = screen.getByRole('button', { name: /^Create$/i });
    await user.click(createSubmitButton);

    // ASSERT: API was called correctly
    await waitFor(() => {
      expect(mockCreateCheckpoint).toHaveBeenCalledWith(123, {
        name: 'New Checkpoint',
        description: 'Test checkpoint',
        trigger: 'manual',
      });
    });

    // List was refreshed
    expect(mockListCheckpoints).toHaveBeenCalledTimes(2);
  });

  it('test_create_checkpoint_validation', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce(mockCheckpoints);
    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Open create dialog
    await user.click(screen.getByText('Create Checkpoint'));

    // Wait for dialog to appear
    await waitFor(() => {
      expect(screen.getByText('Create New Checkpoint')).toBeInTheDocument();
    });

    // Check that submit button is initially disabled (no name)
    const createSubmitButton = screen.getByRole('button', { name: /^Create$/i });
    expect(createSubmitButton).toBeDisabled();

    // API was not called
    expect(mockCreateCheckpoint).not.toHaveBeenCalled();
  });

  it('test_create_checkpoint_cancel', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce(mockCheckpoints);
    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Open create dialog
    await user.click(screen.getByText('Create Checkpoint'));

    // Fill form
    const nameInput = screen.getByLabelText('Name *') as HTMLInputElement;
    await user.type(nameInput, 'Test');

    // Cancel
    await user.click(screen.getByText('Cancel'));

    // ASSERT: Dialog closed
    expect(screen.queryByText('Create New Checkpoint')).not.toBeInTheDocument();
    expect(mockCreateCheckpoint).not.toHaveBeenCalled();
  });

  it('test_delete_checkpoint_success', async () => {
    // ARRANGE
    mockListCheckpoints
      .mockResolvedValueOnce(mockCheckpoints)
      .mockResolvedValueOnce([mockCheckpoints[0]]);
    mockDeleteCheckpoint.mockResolvedValueOnce({
      success: true,
      message: 'Checkpoint deleted',
    });

    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Click delete button for first checkpoint
    const deleteButtons = screen.getAllByText('Delete');
    await user.click(deleteButtons[0]);

    // ASSERT: Confirmation dialog is shown
    await waitFor(() => {
      expect(screen.getByText('Are you sure you want to delete checkpoint "Sprint 10 Phase 3 Complete"?')).toBeInTheDocument();
    });

    // Confirm deletion
    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    await user.click(confirmButton);

    // API was called
    await waitFor(() => {
      expect(mockDeleteCheckpoint).toHaveBeenCalledWith(123, 1);
    });

    // List was refreshed
    expect(mockListCheckpoints).toHaveBeenCalledTimes(2);
  });

  it('test_delete_checkpoint_cancel', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce(mockCheckpoints);
    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Click delete button
    const deleteButtons = screen.getAllByText('Delete');
    await user.click(deleteButtons[0]);

    // ASSERT: Confirmation dialog is shown
    await waitFor(() => {
      expect(screen.getByTestId('delete-confirmation-dialog')).toBeInTheDocument();
    });

    // Cancel deletion
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelButton);

    // ASSERT: API was not called
    expect(mockDeleteCheckpoint).not.toHaveBeenCalled();
  });

  it('test_restore_button_opens_dialog', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValueOnce(mockCheckpoints);
    const user = userEvent.setup();

    // ACT
    render(<CheckpointList projectId={123} />);

    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Click restore button
    const restoreButtons = screen.getAllByText('Restore');
    await user.click(restoreButtons[0]);

    // ASSERT: Restore dialog is shown
    await waitFor(() => {
      expect(screen.getByTestId('checkpoint-restore')).toBeInTheDocument();
    });
  });

  it('test_sorts_checkpoints_by_date', async () => {
    // ARRANGE
    const unsortedCheckpoints = [mockCheckpoints[1], mockCheckpoints[0]]; // Older first
    mockListCheckpoints.mockResolvedValueOnce(unsortedCheckpoints);

    // ACT
    render(<CheckpointList projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading checkpoints...')).not.toBeInTheDocument();
    });

    // Get checkpoint cards (they are sorted)
    const checkpointCards = screen.getAllByText(/Sprint 10 Phase 3 Complete|Auto Checkpoint - Phase 2/);

    // First checkpoint should be the newer one (Sprint 10)
    // Second should be the older one (Auto Checkpoint)
    expect(checkpointCards[0]).toHaveTextContent('Sprint 10 Phase 3 Complete');
  });

  it('test_auto_refresh_enabled', async () => {
    // ARRANGE
    mockListCheckpoints.mockResolvedValue(mockCheckpoints);
    jest.useFakeTimers();

    // ACT
    render(<CheckpointList projectId={123} refreshInterval={5000} />);

    // Wait for initial load
    await waitFor(() => {
      expect(mockListCheckpoints).toHaveBeenCalledTimes(1);
    });

    // Fast-forward time by 5 seconds
    jest.advanceTimersByTime(5000);

    // ASSERT: API called again after interval
    await waitFor(() => {
      expect(mockListCheckpoints).toHaveBeenCalledTimes(2);
    });

    // Cleanup
    jest.useRealTimers();
  });
});
