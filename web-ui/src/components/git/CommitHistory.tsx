/**
 * CommitHistory Component
 *
 * Displays a list of recent git commits with message, hash,
 * author, and file change count.
 *
 * Ticket: #272 - Git Visualization
 */

'use client';

import { memo, useMemo } from 'react';
import { GitCommitIcon, Loading03Icon, Alert02Icon } from '@hugeicons/react';
import type { GitCommit } from '@/types/git';

export interface CommitHistoryProps {
  /** Array of commits to display */
  commits: GitCommit[];
  /** Maximum number of commits to show (default: 10) */
  maxItems?: number;
  /** Loading state */
  isLoading?: boolean;
  /** Error message */
  error?: string | null;
  /** Optional callback for commit click */
  onCommitClick?: (commit: GitCommit) => void;
}

/**
 * Format timestamp to relative time (e.g., "2 hours ago")
 */
function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

/**
 * Individual commit item
 */
interface CommitItemProps {
  commit: GitCommit;
  onClick?: () => void;
}

const CommitItem = memo(function CommitItem({ commit, onClick }: CommitItemProps) {
  return (
    <div
      data-testid="commit-item"
      className="flex items-start gap-3 py-2 px-3 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
      onClick={onClick}
    >
      <GitCommitIcon className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <code className="font-mono text-xs text-primary">
            {commit.short_hash}
          </code>
          {commit.files_changed !== undefined && (
            <span className="text-xs text-muted-foreground">
              {commit.files_changed} file{commit.files_changed !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <p className="text-sm text-foreground truncate">
          {commit.message}
        </p>
        <time
          role="time"
          dateTime={commit.timestamp}
          className="text-xs text-muted-foreground"
        >
          {formatRelativeTime(commit.timestamp)}
        </time>
      </div>
    </div>
  );
});

CommitItem.displayName = 'CommitItem';

/**
 * CommitHistory - Shows list of recent commits
 */
const CommitHistory = memo(function CommitHistory({
  commits,
  maxItems = 10,
  isLoading = false,
  error = null,
  onCommitClick,
}: CommitHistoryProps) {
  // Limit commits to maxItems
  const displayedCommits = useMemo(
    () => commits.slice(0, maxItems),
    [commits, maxItems]
  );

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <GitCommitIcon className="h-4 w-4" />
          Recent Commits
        </h3>
        <div
          data-testid="commits-loading"
          className="flex items-center justify-center py-8 text-muted-foreground"
        >
          <Loading03Icon className="h-5 w-5 animate-spin mr-2" />
          <span>Loading commits...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <GitCommitIcon className="h-4 w-4" />
          Recent Commits
        </h3>
        <div
          data-testid="commits-error"
          className="flex items-center gap-2 py-4 px-3 bg-destructive/10 rounded-md text-destructive text-sm"
        >
          <Alert02Icon className="h-4 w-4" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  // Empty state
  if (displayedCommits.length === 0) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <GitCommitIcon className="h-4 w-4" />
          Recent Commits
        </h3>
        <div className="text-center py-6 text-muted-foreground text-sm">
          <p>No commits yet</p>
          <p className="text-xs mt-1">Commits will appear here as work progresses</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
        <GitCommitIcon className="h-4 w-4" />
        Recent Commits
        <span className="text-xs text-muted-foreground font-normal">
          ({displayedCommits.length})
        </span>
      </h3>
      <div className="space-y-0.5 bg-card border border-border rounded-md overflow-hidden">
        {displayedCommits.map((commit) => (
          <CommitItem
            key={commit.hash}
            commit={commit}
            onClick={onCommitClick ? () => onCommitClick(commit) : undefined}
          />
        ))}
      </div>
      {commits.length > maxItems && (
        <p className="text-xs text-muted-foreground text-center">
          Showing {maxItems} of {commits.length} commits
        </p>
      )}
    </div>
  );
});

CommitHistory.displayName = 'CommitHistory';

export default CommitHistory;
