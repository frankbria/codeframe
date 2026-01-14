/**
 * GitSection Component
 *
 * Container component that combines Git visualization components:
 * - GitBranchIndicator (current branch)
 * - CommitHistory (recent commits)
 * - BranchList (all branches)
 *
 * Uses SWR for data fetching with automatic refresh.
 *
 * Ticket: #272 - Git Visualization
 */

'use client';

import { memo } from 'react';
import useSWR from 'swr';
import { GitCommitIcon, Loading03Icon, Alert02Icon } from '@hugeicons/react';
import GitBranchIndicator from './GitBranchIndicator';
import CommitHistory from './CommitHistory';
import BranchList from './BranchList';
import { getGitStatus, getCommits, getBranches } from '@/api/git';
import type { GitStatus, GitCommit, GitBranch } from '@/types/git';

export interface GitSectionProps {
  /** Project ID to fetch Git data for */
  projectId: number;
  /** Maximum number of commits to show (default: 5) */
  maxCommits?: number;
  /** SWR refresh interval in ms (default: 30000) */
  refreshInterval?: number;
}

/**
 * GitSection - Dashboard section for Git visualization
 */
const GitSection = memo(function GitSection({
  projectId,
  maxCommits = 5,
  refreshInterval = 30000,
}: GitSectionProps) {
  // Fetch git status
  const {
    data: status,
    error: statusError,
    isLoading: statusLoading,
  } = useSWR<GitStatus>(
    `git-status-${projectId}`,
    () => getGitStatus(projectId),
    { refreshInterval }
  );

  // Fetch recent commits
  const {
    data: commits,
    error: commitsError,
    isLoading: commitsLoading,
  } = useSWR<GitCommit[]>(
    `git-commits-${projectId}`,
    () => getCommits(projectId, { limit: maxCommits }),
    { refreshInterval }
  );

  // Fetch branches
  const {
    data: branches,
    error: branchesError,
    isLoading: branchesLoading,
  } = useSWR<GitBranch[]>(
    `git-branches-${projectId}`,
    () => getBranches(projectId),
    { refreshInterval }
  );

  // Combined loading state
  const isLoading = statusLoading || commitsLoading || branchesLoading;

  // Combined error state
  const hasError = statusError || commitsError || branchesError;
  const errorMessage = statusError?.message || commitsError?.message || branchesError?.message;

  // Loading state
  if (isLoading && !status && !commits && !branches) {
    return (
      <div
        data-testid="git-section-loading"
        className="bg-card border border-border rounded-lg p-4"
      >
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loading03Icon className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading Git data...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (hasError && !status && !commits && !branches) {
    return (
      <div
        data-testid="git-section-error"
        className="bg-card border border-border rounded-lg p-4"
      >
        <div className="flex items-center gap-2 text-destructive">
          <Alert02Icon className="h-4 w-4" />
          <span className="text-sm">
            {errorMessage || 'Failed to load Git data'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="git-section"
      className="bg-card border border-border rounded-lg overflow-hidden"
    >
      {/* Section Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
        <div className="flex items-center gap-2">
          <GitCommitIcon className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-medium text-foreground">Code & Git</h2>
        </div>
        <GitBranchIndicator
          status={status ?? null}
          isLoading={statusLoading}
          error={statusError?.message}
        />
      </div>

      {/* Content */}
      <div className="p-4 space-y-6">
        {/* Commits Section */}
        <CommitHistory
          commits={commits ?? []}
          maxItems={maxCommits}
          isLoading={commitsLoading}
          error={commitsError?.message}
        />

        {/* Branches Section */}
        <BranchList
          branches={branches ?? []}
          isLoading={branchesLoading}
          error={branchesError?.message}
        />
      </div>
    </div>
  );
});

GitSection.displayName = 'GitSection';

export default GitSection;
