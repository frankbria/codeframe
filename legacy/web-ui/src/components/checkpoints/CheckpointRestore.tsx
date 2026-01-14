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
    <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50" data-testid="restore-confirmation-dialog">
      <div className="bg-card rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden border border-border">
        {/* Header */}
        <div className="bg-muted px-6 py-4 border-b border-border">
          <h2 className="text-xl font-bold text-foreground">Restore Checkpoint</h2>
          <p className="text-sm text-muted-foreground mt-1">{checkpoint.name}</p>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
          {/* Success message */}
          {restoreSuccess && (
            <div className="bg-secondary/10 border border-secondary/20 rounded-md p-4 mb-6">
              <div className="flex items-center">
                <svg
                  className="h-5 w-5 text-secondary mr-2"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path d="M5 13l4 4L19 7"></path>
                </svg>
                <p className="text-sm font-medium text-foreground">
                  Checkpoint restored successfully!
                </p>
              </div>
              <p className="text-sm text-muted-foreground mt-2">{restoreSuccess.message}</p>
            </div>
          )}

          {/* Warning message */}
          {!restoreSuccess && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 mb-6" data-testid="restore-warning">
              <div className="flex items-start">
                <svg
                  className="h-5 w-5 text-destructive mr-2 mt-0.5"
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
                  <p className="text-sm font-medium text-destructive">
                    ⚠️ Warning: Destructive Operation
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">
                    This will restore your project to the state at checkpoint creation. All
                    uncommitted changes will be lost. This action cannot be undone.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Checkpoint info */}
          <div className="bg-muted rounded-md p-4 mb-6">
            <h3 className="text-sm font-semibold text-foreground mb-3">Checkpoint Details</h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-muted-foreground">Created:</span>{' '}
                <span className="text-foreground">{formatDate(checkpoint.created_at)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Git Commit:</span>{' '}
                <span className="font-mono text-foreground text-xs">
                  {checkpoint.git_commit.substring(0, 7)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Phase:</span>{' '}
                <span className="text-foreground">{checkpoint.metadata.phase}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Tasks Completed:</span>{' '}
                <span className="text-foreground">
                  {checkpoint.metadata.tasks_completed}/{checkpoint.metadata.tasks_total}
                </span>
              </div>
            </div>
          </div>

          {/* Diff preview */}
          {loadingDiff && (
            <div className="flex justify-center items-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              <span className="ml-3 text-muted-foreground">Loading diff preview...</span>
            </div>
          )}

          {diffError && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 mb-6">
              <p className="text-sm text-destructive">{diffError}</p>
            </div>
          )}

          {diff && !loadingDiff && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-foreground mb-3">Changes Preview</h3>
              <div className="bg-muted rounded-md p-3 mb-3">
                <div className="flex space-x-6 text-sm">
                  <div>
                    <span className="text-muted-foreground">Files changed:</span>{' '}
                    <span className="font-medium text-foreground">{diff.files_changed}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Insertions:</span>{' '}
                    <span className="font-medium text-secondary">+{diff.insertions}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Deletions:</span>{' '}
                    <span className="font-medium text-destructive">-{diff.deletions}</span>
                  </div>
                </div>
              </div>
              <div className="bg-popover rounded-md p-4 overflow-x-auto border border-border">
                <pre className="text-xs font-mono text-popover-foreground whitespace-pre-wrap">
                  {diff.diff}
                </pre>
              </div>
            </div>
          )}

          {/* Restore error */}
          {restoreError && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 mb-6">
              <p className="text-sm text-destructive">{restoreError}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-muted px-6 py-4 border-t border-border flex justify-end space-x-3">
          <button
            onClick={onClose}
            disabled={restoring}
            className="px-4 py-2 border border-border rounded-md text-sm font-medium text-foreground hover:bg-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="restore-cancel-button"
          >
            {restoreSuccess ? 'Close' : 'Cancel'}
          </button>
          {!restoreSuccess && (
            <button
              onClick={handleRestore}
              disabled={restoring || loadingDiff || !!diffError}
              className="px-4 py-2 bg-secondary text-secondary-foreground rounded-md text-sm font-medium hover:bg-secondary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="restore-confirm-button"
            >
              {restoring ? 'Restoring...' : 'Confirm Restore'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
