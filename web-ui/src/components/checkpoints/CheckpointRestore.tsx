/**
 * CheckpointRestore Component for Sprint 10 Phase 4
 * Displays restore confirmation dialog with git diff preview
 */

import React, { useState, useEffect } from 'react';
import type { Checkpoint, CheckpointDiff, RestoreCheckpointResponse } from '../../types/checkpoints';
import { getCheckpointDiff, restoreCheckpoint } from '../../api/checkpoints';

interface CheckpointRestoreProps {
  projectId: number;
  checkpoint: Checkpoint;
  onClose: () => void;
  onRestoreComplete: () => void;
}

export const CheckpointRestore: React.FC<CheckpointRestoreProps> = ({
  projectId,
  checkpoint,
  onClose,
  onRestoreComplete,
}) => {
  const [diff, setDiff] = useState<CheckpointDiff | null>(null);
  const [loadingDiff, setLoadingDiff] = useState<boolean>(true);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<boolean>(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreSuccess, setRestoreSuccess] = useState<RestoreCheckpointResponse | null>(null);

  // Load diff preview
  useEffect(() => {
    const loadDiff = async () => {
      try {
        setDiffError(null);
        const diffData = await getCheckpointDiff(projectId, checkpoint.id);
        setDiff(diffData);
      } catch (err) {
        setDiffError(err instanceof Error ? err.message : 'Failed to load diff preview');
      } finally {
        setLoadingDiff(false);
      }
    };

    loadDiff();
  }, [projectId, checkpoint.id]);

  // Handle restore confirmation
  const handleRestore = async () => {
    setRestoring(true);
    setRestoreError(null);

    try {
      const response = await restoreCheckpoint(projectId, checkpoint.id, true);
      setRestoreSuccess(response);

      // Wait 2 seconds then notify parent
      setTimeout(() => {
        onRestoreComplete();
      }, 2000);
    } catch (err) {
      setRestoreError(err instanceof Error ? err.message : 'Failed to restore checkpoint');
      setRestoring(false);
    }
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

  return (
    <div className="fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">Restore Checkpoint</h2>
          <p className="text-sm text-gray-600 mt-1">{checkpoint.name}</p>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
          {/* Success message */}
          {restoreSuccess && (
            <div className="bg-green-50 border border-green-200 rounded-md p-4 mb-6">
              <div className="flex items-center">
                <svg
                  className="h-5 w-5 text-green-600 mr-2"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path d="M5 13l4 4L19 7"></path>
                </svg>
                <p className="text-sm font-medium text-green-800">
                  Checkpoint restored successfully!
                </p>
              </div>
              <p className="text-sm text-green-700 mt-2">{restoreSuccess.message}</p>
            </div>
          )}

          {/* Warning message */}
          {!restoreSuccess && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-6">
              <div className="flex items-start">
                <svg
                  className="h-5 w-5 text-yellow-600 mr-2 mt-0.5"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                <div>
                  <p className="text-sm font-medium text-yellow-800">
                    ⚠️ Warning: Destructive Operation
                  </p>
                  <p className="text-sm text-yellow-700 mt-1">
                    This will restore your project to the state at checkpoint creation. All
                    uncommitted changes will be lost. This action cannot be undone.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Checkpoint info */}
          <div className="bg-gray-50 rounded-md p-4 mb-6">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Checkpoint Details</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-gray-500">Created:</span>{' '}
                <span className="text-gray-900">{formatDate(checkpoint.created_at)}</span>
              </div>
              <div>
                <span className="text-gray-500">Git Commit:</span>{' '}
                <span className="font-mono text-gray-900 text-xs">
                  {checkpoint.git_commit.substring(0, 7)}
                </span>
              </div>
              <div>
                <span className="text-gray-500">Phase:</span>{' '}
                <span className="text-gray-900">{checkpoint.metadata.phase}</span>
              </div>
              <div>
                <span className="text-gray-500">Tasks Completed:</span>{' '}
                <span className="text-gray-900">
                  {checkpoint.metadata.tasks_completed}/{checkpoint.metadata.tasks_total}
                </span>
              </div>
            </div>
          </div>

          {/* Diff preview */}
          {loadingDiff && (
            <div className="flex justify-center items-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
              <span className="ml-3 text-gray-600">Loading diff preview...</span>
            </div>
          )}

          {diffError && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4 mb-6">
              <p className="text-sm text-red-800">{diffError}</p>
            </div>
          )}

          {diff && !loadingDiff && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Changes Preview</h3>
              <div className="bg-gray-50 rounded-md p-3 mb-3">
                <div className="flex space-x-6 text-sm">
                  <div>
                    <span className="text-gray-500">Files changed:</span>{' '}
                    <span className="font-medium text-gray-900">{diff.files_changed}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Insertions:</span>{' '}
                    <span className="font-medium text-green-600">+{diff.insertions}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Deletions:</span>{' '}
                    <span className="font-medium text-red-600">-{diff.deletions}</span>
                  </div>
                </div>
              </div>
              <div className="bg-gray-900 rounded-md p-4 overflow-x-auto">
                <pre className="text-xs font-mono text-gray-100 whitespace-pre-wrap">
                  {diff.diff}
                </pre>
              </div>
            </div>
          )}

          {/* Restore error */}
          {restoreError && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4 mb-6">
              <p className="text-sm text-red-800">{restoreError}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end space-x-3">
          <button
            onClick={onClose}
            disabled={restoring}
            className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {restoreSuccess ? 'Close' : 'Cancel'}
          </button>
          {!restoreSuccess && (
            <button
              onClick={handleRestore}
              disabled={restoring || loadingDiff || !!diffError}
              className="px-4 py-2 bg-green-600 text-white rounded-md text-sm font-medium hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {restoring ? 'Restoring...' : 'Confirm Restore'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
