/**
 * GitBranchIndicator Component
 *
 * Displays the current git branch name and status in a compact badge format.
 * Shows dirty state indicator when there are uncommitted changes.
 *
 * Ticket: #272 - Git Visualization
 */

'use client';

import { memo } from 'react';
import { GitCommitIcon, Loading03Icon, Alert02Icon } from '@hugeicons/react';
import type { GitStatus } from '@/types/git';

export interface GitBranchIndicatorProps {
  /** Git status data (null when not loaded) */
  status: GitStatus | null;
  /** Loading state */
  isLoading?: boolean;
  /** Error message */
  error?: string | null;
}

/**
 * Calculate total file changes
 */
function getTotalChanges(status: GitStatus): number {
  return (
    status.modified_files.length +
    status.untracked_files.length +
    status.staged_files.length
  );
}

/**
 * GitBranchIndicator - Shows current branch with status
 */
const GitBranchIndicator = memo(function GitBranchIndicator({
  status,
  isLoading = false,
  error = null,
}: GitBranchIndicatorProps) {
  // Loading state
  if (isLoading) {
    return (
      <div
        data-testid="branch-loading"
        className="flex items-center gap-1.5 px-2 py-1 bg-muted rounded-md text-xs text-muted-foreground"
      >
        <Loading03Icon className="h-3 w-3 animate-spin" />
        <span>Loading...</span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        data-testid="branch-error"
        className="flex items-center gap-1.5 px-2 py-1 bg-destructive/10 rounded-md text-xs text-destructive"
        title={error}
      >
        <Alert02Icon className="h-3 w-3" />
        <span>Git error</span>
      </div>
    );
  }

  // No status
  if (!status) {
    return null;
  }

  const totalChanges = getTotalChanges(status);
  const tooltipText = status.is_dirty
    ? `${status.current_branch} (${totalChanges} uncommitted change${totalChanges !== 1 ? 's' : ''})`
    : status.current_branch;

  return (
    <div
      data-testid="branch-indicator"
      className="flex items-center gap-1.5 px-2 py-1 bg-muted rounded-md text-xs max-w-48 truncate"
      title={tooltipText}
    >
      <GitCommitIcon className="h-3 w-3 text-muted-foreground flex-shrink-0" />
      <span className="truncate font-mono text-foreground">
        {status.current_branch}
      </span>
      {status.is_dirty && (
        <span
          data-testid="dirty-indicator"
          className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-amber-500"
          title={`${totalChanges} uncommitted changes`}
        />
      )}
    </div>
  );
});

GitBranchIndicator.displayName = 'GitBranchIndicator';

export default GitBranchIndicator;
