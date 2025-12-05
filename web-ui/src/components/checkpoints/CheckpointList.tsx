/**
 * CheckpointList Component for Sprint 10 Phase 4
 * Displays list of checkpoints with create/delete functionality
 */

import React, { useState, useEffect } from 'react';
import type { Checkpoint } from '../../types/checkpoints';
import { listCheckpoints, createCheckpoint, deleteCheckpoint } from '../../api/checkpoints';
import { CheckpointRestore } from './CheckpointRestore';

interface CheckpointListProps {
  projectId: number;
  refreshInterval?: number; // Auto-refresh interval in ms (optional)
}

export const CheckpointList: React.FC<CheckpointListProps> = ({
  projectId,
  refreshInterval,
}) => {
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<boolean>(false);
  const [showCreateDialog, setShowCreateDialog] = useState<boolean>(false);
  const [newCheckpointName, setNewCheckpointName] = useState<string>('');
  const [newCheckpointDescription, setNewCheckpointDescription] = useState<string>('');
  const [nameError, setNameError] = useState<string | null>(null);
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<Checkpoint | null>(null);
  const [showRestoreDialog, setShowRestoreDialog] = useState<boolean>(false);

  // Load checkpoints
  const loadCheckpoints = async () => {
    try {
      setError(null);
      const data = await listCheckpoints(projectId);
      // Sort by date (newest first)
      const sorted = data.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setCheckpoints(sorted);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load checkpoints');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCheckpoints();

    // Set up auto-refresh if interval provided
    if (refreshInterval && refreshInterval > 0) {
      const intervalId = setInterval(loadCheckpoints, refreshInterval);
      return () => clearInterval(intervalId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, refreshInterval]);

  // Handle create checkpoint
  const handleCreateCheckpoint = async () => {
    if (!newCheckpointName.trim()) {
      setNameError('Checkpoint name is required');
      return;
    }

    setCreating(true);
    setError(null);
    setNameError(null);

    try {
      await createCheckpoint(projectId, {
        name: newCheckpointName,
        description: newCheckpointDescription || undefined,
        trigger: 'manual',
      });

      // Reset form and reload
      setNewCheckpointName('');
      setNewCheckpointDescription('');
      setNameError(null);
      setShowCreateDialog(false);
      await loadCheckpoints();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create checkpoint');
    } finally {
      setCreating(false);
    }
  };

  // Handle delete checkpoint
  const handleDeleteCheckpoint = async (checkpointId: number, checkpointName: string) => {
    if (!window.confirm(`Are you sure you want to delete checkpoint "${checkpointName}"?`)) {
      return;
    }

    try {
      setError(null);
      await deleteCheckpoint(projectId, checkpointId);
      await loadCheckpoints();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete checkpoint');
    }
  };

  // Handle restore click
  const handleRestoreClick = (checkpoint: Checkpoint) => {
    setSelectedCheckpoint(checkpoint);
    setShowRestoreDialog(true);
  };

  // Handle restore complete
  const handleRestoreComplete = () => {
    setShowRestoreDialog(false);
    setSelectedCheckpoint(null);
    loadCheckpoints();
  };

  // Format date
  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Format trigger badge
  const getTriggerBadge = (trigger: string): string => {
    switch (trigger) {
      case 'manual':
        return 'bg-blue-100 text-blue-800';
      case 'auto':
        return 'bg-green-100 text-green-800';
      case 'phase_transition':
        return 'bg-purple-100 text-purple-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-600">Loading checkpoints...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="checkpoint-list">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">Checkpoints</h2>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          data-testid="create-checkpoint-button"
        >
          Create Checkpoint
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* Create checkpoint dialog */}
      {showCreateDialog && (
        <div className="bg-white border border-gray-200 rounded-md p-6 shadow-sm" data-testid="create-checkpoint-modal">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Create New Checkpoint</h3>
          <div className="space-y-4">
            <div>
              <label htmlFor="checkpoint-name" className="block text-sm font-medium text-gray-700">
                Name *
              </label>
              <input
                id="checkpoint-name"
                type="text"
                value={newCheckpointName}
                onChange={(e) => {
                  setNewCheckpointName(e.target.value);
                  if (e.target.value.trim()) {
                    setNameError(null);
                  }
                }}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                placeholder="e.g., Sprint 10 Phase 4 Complete"
                disabled={creating}
                data-testid="checkpoint-name-input"
              />
              {nameError && (
                <p className="mt-1 text-sm text-red-600" data-testid="checkpoint-name-error">
                  {nameError}
                </p>
              )}
            </div>
            <div>
              <label
                htmlFor="checkpoint-description"
                className="block text-sm font-medium text-gray-700"
              >
                Description (optional)
              </label>
              <textarea
                id="checkpoint-description"
                value={newCheckpointDescription}
                onChange={(e) => setNewCheckpointDescription(e.target.value)}
                rows={3}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
                placeholder="Brief description of what was completed..."
                disabled={creating}
                data-testid="checkpoint-description-input"
              />
            </div>
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => {
                  setShowCreateDialog(false);
                  setNewCheckpointName('');
                  setNewCheckpointDescription('');
                  setNameError(null);
                }}
                className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                disabled={creating}
                data-testid="checkpoint-cancel-button"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateCheckpoint}
                disabled={creating || !newCheckpointName.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                data-testid="checkpoint-save-button"
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Checkpoints list */}
      {checkpoints.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-md" data-testid="checkpoint-empty-state">
          <p className="text-gray-600">No checkpoints yet. Create your first checkpoint!</p>
        </div>
      ) : (
        <div className="space-y-4">
          {checkpoints.map((checkpoint) => (
            <div
              key={checkpoint.id}
              className="bg-white border border-gray-200 rounded-md p-6 hover:shadow-md transition-shadow"
              data-testid={`checkpoint-item-${checkpoint.id}`}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900" data-testid="checkpoint-name">{checkpoint.name}</h3>
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${getTriggerBadge(
                        checkpoint.trigger
                      )}`}
                    >
                      {checkpoint.trigger}
                    </span>
                  </div>
                  {checkpoint.description && (
                    <p className="text-sm text-gray-600 mb-3">{checkpoint.description}</p>
                  )}
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-500">Created:</span>{' '}
                      <span className="text-gray-900" data-testid="checkpoint-timestamp">{formatDate(checkpoint.created_at)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Git Commit:</span>{' '}
                      <span className="font-mono text-gray-900 text-xs" data-testid="checkpoint-git-sha">
                        {checkpoint.git_commit.substring(0, 7)}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Tasks:</span>{' '}
                      <span className="text-gray-900">
                        {checkpoint.metadata.tasks_completed}/{checkpoint.metadata.tasks_total}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Active Agents:</span>{' '}
                      <span className="text-gray-900">
                        {checkpoint.metadata.agents_active.length}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Context Items:</span>{' '}
                      <span className="text-gray-900">
                        {checkpoint.metadata.context_items_count}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-500">Total Cost:</span>{' '}
                      <span className="text-gray-900">
                        ${checkpoint.metadata.total_cost_usd.toFixed(2)}
                      </span>
                    </div>
                  </div>
                  {checkpoint.metadata.last_task_completed && (
                    <div className="mt-3 text-sm">
                      <span className="text-gray-500">Last Task:</span>{' '}
                      <span className="text-gray-900">
                        {checkpoint.metadata.last_task_completed}
                      </span>
                    </div>
                  )}
                </div>
                <div className="flex flex-col space-y-2 ml-4">
                  <button
                    onClick={() => handleRestoreClick(checkpoint)}
                    className="px-3 py-1 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
                    data-testid="checkpoint-restore-button"
                  >
                    Restore
                  </button>
                  <button
                    onClick={() => handleDeleteCheckpoint(checkpoint.id, checkpoint.name)}
                    className="px-3 py-1 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
                    data-testid="checkpoint-delete-button"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Restore dialog */}
      {showRestoreDialog && selectedCheckpoint && (
        <CheckpointRestore
          projectId={projectId}
          checkpoint={selectedCheckpoint}
          onClose={() => {
            setShowRestoreDialog(false);
            setSelectedCheckpoint(null);
          }}
          onRestoreComplete={handleRestoreComplete}
        />
      )}
    </div>
  );
};

export default React.memo(CheckpointList);
