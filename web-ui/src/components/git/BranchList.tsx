/**
 * BranchList Component
 *
 * Displays a list of git branches with status badges.
 * Supports filtering by status and shows merge info for merged branches.
 *
 * Ticket: #272 - Git Visualization
 */

'use client';

import { memo, useMemo } from 'react';
import { GitCommitIcon, Loading03Icon, Alert02Icon } from '@hugeicons/react';
import type { GitBranch, BranchStatus } from '@/types/git';

export interface BranchListProps {
  /** Array of branches to display */
  branches: GitBranch[];
  /** Filter to specific status (optional) */
  filterStatus?: BranchStatus;
  /** Loading state */
  isLoading?: boolean;
  /** Error message */
  error?: string | null;
  /** Optional callback for branch click */
  onBranchClick?: (branch: GitBranch) => void;
}

/**
 * Get badge styling based on branch status
 */
function getStatusStyles(status: BranchStatus): { bgClass: string; textClass: string } {
  switch (status) {
    case 'active':
      return { bgClass: 'bg-primary/10', textClass: 'text-primary' };
    case 'merged':
      return { bgClass: 'bg-secondary/10', textClass: 'text-secondary-foreground' };
    case 'abandoned':
      return { bgClass: 'bg-muted', textClass: 'text-muted-foreground' };
  }
}

/**
 * Individual branch item
 */
interface BranchItemProps {
  branch: GitBranch;
  onClick?: () => void;
}

const BranchItem = memo(function BranchItem({ branch, onClick }: BranchItemProps) {
  const statusStyles = getStatusStyles(branch.status);

  return (
    <div
      data-testid="branch-item"
      className="flex items-center justify-between py-2 px-3 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-center gap-2 min-w-0">
        <GitCommitIcon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <span className="font-mono text-sm text-foreground truncate">
          {branch.branch_name}
        </span>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {branch.merge_commit && (
          <span className="text-xs text-muted-foreground font-mono">
            → {branch.merge_commit.slice(0, 7)}
          </span>
        )}
        <span
          className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusStyles.bgClass} ${statusStyles.textClass}`}
        >
          {branch.status}
        </span>
      </div>
    </div>
  );
});

BranchItem.displayName = 'BranchItem';

/**
 * BranchList - Shows list of git branches
 */
const BranchList = memo(function BranchList({
  branches,
  filterStatus,
  isLoading = false,
  error = null,
  onBranchClick,
}: BranchListProps) {
  // Filter branches by status if provided
  const displayedBranches = useMemo(() => {
    if (!filterStatus) return branches;
    return branches.filter((b) => b.status === filterStatus);
  }, [branches, filterStatus]);

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <GitCommitIcon className="h-4 w-4" />
          Branches
        </h3>
        <div
          data-testid="branches-loading"
          className="flex items-center justify-center py-8 text-muted-foreground"
        >
          <Loading03Icon className="h-5 w-5 animate-spin mr-2" />
          <span>Loading branches...</span>
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
          Branches
        </h3>
        <div
          data-testid="branches-error"
          className="flex items-center gap-2 py-4 px-3 bg-destructive/10 rounded-md text-destructive text-sm"
        >
          <Alert02Icon className="h-4 w-4" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  // Empty state
  if (displayedBranches.length === 0) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <GitCommitIcon className="h-4 w-4" />
          Branches
        </h3>
        <div className="text-center py-6 text-muted-foreground text-sm">
          <p>No branches created yet</p>
          <p className="text-xs mt-1">Branches will appear here as issues are worked on</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
        <GitCommitIcon className="h-4 w-4" />
        Branches
        <span className="text-xs text-muted-foreground font-normal">
          ({displayedBranches.length})
        </span>
      </h3>
      <div className="space-y-0.5 bg-card border border-border rounded-md overflow-hidden">
        {displayedBranches.map((branch) => (
          <BranchItem
            key={branch.id}
            branch={branch}
            onClick={onBranchClick ? () => onBranchClick(branch) : undefined}
          />
        ))}
      </div>
    </div>
  );
});

BranchList.displayName = 'BranchList';

export default BranchList;
