/**
 * PRList Component
 * Displays pull requests for a project with filtering and actions
 *
 * Features:
 * - List view with status badges and metadata
 * - Status filtering (all, open, merged, closed)
 * - Create PR action
 * - Quick actions (view, merge for open PRs)
 * - CI and review status indicators
 * - Real-time updates via WebSocket
 * - Empty, loading, and error states
 */

'use client';

import { useState, useEffect, useCallback, memo } from 'react';
import useSWR from 'swr';
import { pullRequestsApi } from '@/lib/api';
import { getWebSocketClient } from '@/lib/websocket';
import type {
  PullRequest,
  PRStatus,
  CIStatus,
  ReviewStatus,
} from '@/types/pullRequest';
import {
  GitPullRequestIcon,
  CheckmarkCircle01Icon,
  Cancel01Icon,
  Loading03Icon,
  AlertCircleIcon,
  GitBranchIcon,
  Link01Icon,
  Add01Icon,
  ArrowRight01Icon,
  CheckmarkSquare01Icon,
  Cancel02Icon,
  Time01Icon,
} from '@hugeicons/react';

// ============================================================================
// Types
// ============================================================================

export interface PRListProps {
  projectId: number;
  onCreatePR: () => void;
  onViewPR: (prNumber: number) => void;
  onMergePR: (pr: PullRequest) => void;
}

type FilterOption = 'all' | PRStatus;

interface FilterConfig {
  label: string;
  status: FilterOption;
}

// ============================================================================
// Constants
// ============================================================================

const FILTER_OPTIONS: FilterConfig[] = [
  { label: 'All', status: 'all' },
  { label: 'Open', status: 'open' },
  { label: 'Merged', status: 'merged' },
  { label: 'Closed', status: 'closed' },
];

const STATUS_COLORS: Record<PRStatus, { bg: string; text: string }> = {
  open: { bg: 'bg-success/10', text: 'text-success' },
  merged: { bg: 'bg-primary/10', text: 'text-primary' },
  closed: { bg: 'bg-destructive/10', text: 'text-destructive' },
  draft: { bg: 'bg-muted', text: 'text-muted-foreground' },
};

// ============================================================================
// Helper Components
// ============================================================================

/**
 * CI Status indicator component
 */
const CIStatusIndicator = memo(function CIStatusIndicator({
  status,
}: {
  status?: CIStatus;
}) {
  if (!status) return null;

  const icons: Record<CIStatus, { icon: typeof CheckmarkCircle01Icon; color: string }> = {
    success: { icon: CheckmarkCircle01Icon, color: 'text-green-600' },
    failure: { icon: Cancel01Icon, color: 'text-red-600' },
    pending: { icon: Loading03Icon, color: 'text-yellow-600' },
    unknown: { icon: AlertCircleIcon, color: 'text-gray-400' },
  };

  const config = icons[status] || icons.unknown;
  const Icon = config.icon;

  return (
    <span
      data-testid="ci-status"
      data-status={status}
      className={`inline-flex items-center ${config.color}`}
      title={`CI: ${status}`}
    >
      <Icon className="h-4 w-4" />
    </span>
  );
});

/**
 * Review status indicator component
 */
const ReviewStatusIndicator = memo(function ReviewStatusIndicator({
  status,
}: {
  status?: ReviewStatus;
}) {
  if (!status) return null;

  const configs: Record<ReviewStatus, { icon: typeof CheckmarkSquare01Icon; color: string; label: string }> = {
    approved: { icon: CheckmarkSquare01Icon, color: 'text-green-600', label: 'Approved' },
    changes_requested: { icon: Cancel02Icon, color: 'text-orange-600', label: 'Changes requested' },
    pending: { icon: Time01Icon, color: 'text-yellow-600', label: 'Pending review' },
    dismissed: { icon: Cancel01Icon, color: 'text-gray-400', label: 'Dismissed' },
  };

  const config = configs[status] || configs.pending;
  const Icon = config.icon;

  return (
    <span
      data-testid="review-status"
      data-status={status}
      className={`inline-flex items-center ${config.color}`}
      title={config.label}
    >
      <Icon className="h-4 w-4" />
    </span>
  );
});

/**
 * Individual PR card component
 */
interface PRCardProps {
  pr: PullRequest;
  onView: () => void;
  onMerge: () => void;
}

const PRCard = memo(function PRCard({ pr, onView, onMerge }: PRCardProps) {
  const statusColor = STATUS_COLORS[pr.status] || STATUS_COLORS.draft;
  const canMerge = pr.status === 'open';

  return (
    <div
      data-testid="pr-card"
      data-status={pr.status}
      className="bg-card border border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
    >
      {/* Header: PR number, title, status */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <GitPullRequestIcon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="text-sm font-medium text-muted-foreground">#{pr.pr_number}</span>
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColor.bg} ${statusColor.text}`}>
              {pr.status}
            </span>
          </div>
          <h3 className="font-medium text-foreground truncate" title={pr.title}>
            {pr.title}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <CIStatusIndicator status={pr.ci_status} />
          <ReviewStatusIndicator status={pr.review_status} />
        </div>
      </div>

      {/* Branch info */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
        <GitBranchIcon className="h-4 w-4" />
        <span className="font-mono text-xs">{pr.head_branch}</span>
        <ArrowRight01Icon className="h-3 w-3" />
        <span className="font-mono text-xs">{pr.base_branch}</span>
      </div>

      {/* File changes */}
      {(pr.files_changed !== undefined || pr.additions !== undefined || pr.deletions !== undefined) && (
        <div className="flex items-center gap-4 text-sm mb-3">
          {pr.files_changed !== undefined && (
            <span className="text-muted-foreground">{pr.files_changed} files</span>
          )}
          {pr.additions !== undefined && (
            <span className="text-green-600">+{pr.additions}</span>
          )}
          {pr.deletions !== undefined && (
            <span className="text-red-600">-{pr.deletions}</span>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <div className="flex items-center gap-2">
          <button
            onClick={onView}
            className="px-3 py-1.5 text-sm font-medium text-foreground bg-secondary hover:bg-secondary/80 rounded-md transition-colors"
          >
            View
          </button>
          {canMerge && (
            <button
              onClick={onMerge}
              className="px-3 py-1.5 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-md transition-colors"
            >
              Merge
            </button>
          )}
        </div>
        {pr.pr_url && (
          <a
            href={pr.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View on GitHub"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <Link01Icon className="h-4 w-4" />
            GitHub
          </a>
        )}
      </div>
    </div>
  );
});

/**
 * Loading skeleton component
 */
const LoadingSkeleton = memo(function LoadingSkeleton() {
  return (
    <div data-testid="pr-list-loading" className="space-y-4">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="bg-card border border-border rounded-lg p-4 animate-pulse"
        >
          <div className="flex items-center gap-2 mb-3">
            <div className="h-4 w-4 bg-muted rounded" />
            <div className="h-4 w-12 bg-muted rounded" />
            <div className="h-5 w-16 bg-muted rounded-full" />
          </div>
          <div className="h-5 w-3/4 bg-muted rounded mb-3" />
          <div className="h-4 w-1/2 bg-muted rounded mb-3" />
          <div className="flex gap-2 pt-3 border-t border-border">
            <div className="h-8 w-16 bg-muted rounded" />
            <div className="h-8 w-16 bg-muted rounded" />
          </div>
        </div>
      ))}
    </div>
  );
});

/**
 * Empty state component
 */
const EmptyState = memo(function EmptyState({ onCreatePR }: { onCreatePR: () => void }) {
  return (
    <div className="text-center py-12">
      <GitPullRequestIcon className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
      <h3 className="text-lg font-medium text-foreground mb-2">No pull requests</h3>
      <p className="text-muted-foreground mb-4">
        Create your first pull request to start collaborating
      </p>
      <button
        onClick={onCreatePR}
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-md transition-colors"
      >
        <Add01Icon className="h-4 w-4" />
        Create PR
      </button>
    </div>
  );
});

/**
 * Error state component
 */
const ErrorState = memo(function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="text-center py-12">
      <AlertCircleIcon className="h-12 w-12 text-destructive mx-auto mb-4" />
      <h3 className="text-lg font-medium text-foreground mb-2">Failed to load pull requests</h3>
      <p className="text-muted-foreground mb-4">
        There was an error loading the pull requests. Please try again.
      </p>
      <button
        onClick={onRetry}
        className="px-4 py-2 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-md transition-colors"
      >
        Retry
      </button>
    </div>
  );
});

// ============================================================================
// Main Component
// ============================================================================

/**
 * PRList component for displaying and managing pull requests
 */
export default function PRList({
  projectId,
  onCreatePR,
  onViewPR,
  onMergePR,
}: PRListProps) {
  const [filter, setFilter] = useState<FilterOption>('all');

  // Fetch PRs using SWR - key includes filter for automatic revalidation
  const { data, error, isLoading, mutate } = useSWR(
    [`/api/projects/${projectId}/prs`, projectId, filter],
    () =>
      pullRequestsApi
        .list(projectId, filter === 'all' ? undefined : filter)
        .then((res) => res.data),
    {
      revalidateOnFocus: true,
      refreshInterval: 30000, // Refresh every 30 seconds
    }
  );

  // Filter change handler
  const handleFilterChange = useCallback((newFilter: FilterOption) => {
    setFilter(newFilter);
  }, []);

  // WebSocket subscription for real-time updates
  useEffect(() => {
    const ws = getWebSocketClient();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handleMessage = (message: any) => {
      // Only handle PR events for this project
      if (message.project_id !== projectId) {
        return;
      }

      // Revalidate on PR events
      if (
        message.type === 'pr_created' ||
        message.type === 'pr_merged' ||
        message.type === 'pr_closed'
      ) {
        mutate();
      }
    };

    const unsubscribe = ws.onMessage(handleMessage);

    return () => {
      unsubscribe();
    };
  }, [projectId, mutate]);

  // Filter PRs locally for instant UI response
  const filteredPRs = data?.prs?.filter((pr) =>
    filter === 'all' ? true : pr.status === filter
  );

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex gap-2">
            {FILTER_OPTIONS.map((option) => (
              <div
                key={option.status}
                className="h-8 w-16 bg-muted rounded animate-pulse"
              />
            ))}
          </div>
          <div className="h-9 w-28 bg-muted rounded animate-pulse" />
        </div>
        <LoadingSkeleton />
      </div>
    );
  }

  // Error state
  if (error) {
    return <ErrorState onRetry={() => mutate()} />;
  }

  return (
    <div className="space-y-4">
      {/* Header with filters and create button */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-2" role="tablist" aria-label="PR status filter">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.status}
              role="tab"
              aria-selected={filter === option.status}
              data-active={filter === option.status}
              onClick={() => handleFilterChange(option.status)}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                filter === option.status
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button
          onClick={onCreatePR}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 rounded-md transition-colors"
        >
          <Add01Icon className="h-4 w-4" />
          Create PR
        </button>
      </div>

      {/* PR List or Empty State */}
      {!filteredPRs || filteredPRs.length === 0 ? (
        <EmptyState onCreatePR={onCreatePR} />
      ) : (
        <div className="grid gap-4">
          {filteredPRs.map((pr) => (
            <PRCard
              key={pr.id}
              pr={pr}
              onView={() => onViewPR(pr.pr_number)}
              onMerge={() => onMergePR(pr)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
