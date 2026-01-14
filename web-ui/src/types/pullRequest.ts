/**
 * Pull Request Type Definitions for CodeFRAME UI
 *
 * TypeScript interfaces for PR management components.
 * These types match the backend API responses from the PR router.
 *
 * @see codeframe/ui/routers/prs.py for API response models
 */

// ============================================================================
// Status Types
// ============================================================================

/**
 * Valid pull request status values
 */
export type PRStatus = 'open' | 'merged' | 'closed' | 'draft';

/**
 * Valid merge method values
 */
export type MergeMethod = 'squash' | 'merge' | 'rebase';

/**
 * CI/CD pipeline status
 */
export type CIStatus = 'success' | 'failure' | 'pending' | 'unknown';

/**
 * Code review status
 */
export type ReviewStatus = 'approved' | 'changes_requested' | 'pending' | 'dismissed';

// ============================================================================
// Core Types
// ============================================================================

/**
 * Pull request entity matching PR data from backend
 */
export interface PullRequest {
  /** Internal database ID */
  id: number;

  /** GitHub PR number (e.g., #42) */
  pr_number: number;

  /** PR title */
  title: string;

  /** PR description/body */
  body: string;

  /** Current status */
  status: PRStatus;

  /** Source branch with changes */
  head_branch: string;

  /** Target branch to merge into */
  base_branch: string;

  /** GitHub PR URL */
  pr_url: string | null;

  /** Associated issue ID (optional) */
  issue_id: number | null;

  /** Creation timestamp (ISO 8601) */
  created_at: string;

  /** Last update timestamp (ISO 8601) */
  updated_at: string;

  /** Merge timestamp (ISO 8601, null if not merged) */
  merged_at: string | null;

  /** Merge commit SHA (null if not merged) */
  merge_commit_sha: string | null;

  /** Number of files changed (from GitHub) */
  files_changed?: number;

  /** Lines added (from GitHub) */
  additions?: number;

  /** Lines removed (from GitHub) */
  deletions?: number;

  /** CI status (from GitHub checks) */
  ci_status?: CIStatus;

  /** Code review status */
  review_status?: ReviewStatus;

  /** PR author */
  author?: string;
}

// ============================================================================
// API Request Types
// ============================================================================

/**
 * Request to create a new pull request
 */
export interface CreatePRRequest {
  /** Source branch with changes */
  branch: string;

  /** PR title */
  title: string;

  /** PR description/body */
  body: string;

  /** Target branch (defaults to 'main') */
  base: string;
}

/**
 * Request to merge a pull request
 */
export interface MergePRRequest {
  /** Merge method */
  method: MergeMethod;

  /** Whether to delete branch after merge */
  delete_branch?: boolean;
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Response from creating a PR
 */
export interface CreatePRResponse {
  pr_id: number;
  pr_number: number;
  pr_url: string;
  status: PRStatus;
}

/**
 * Response from merging a PR
 */
export interface MergePRResponse {
  merged: boolean;
  merge_commit_sha: string | null;
}

/**
 * Response from closing a PR
 */
export interface ClosePRResponse {
  closed: boolean;
}

/**
 * Response from listing PRs
 */
export interface PRListResponse {
  prs: PullRequest[];
  total: number;
}

// ============================================================================
// State Management Types
// ============================================================================

/**
 * PR state for the Dashboard context
 * Used by PRList and related components
 */
export interface PRState {
  /** List of pull requests */
  prs: PullRequest[];

  /** Total count (for pagination) */
  total: number;

  /** Loading state indicator */
  isLoading: boolean;

  /** Error message (null when no error) */
  error: string | null;

  /** Currently selected status filter */
  statusFilter: PRStatus | 'all';
}

// ============================================================================
// Utility Types and Constants
// ============================================================================

/**
 * Initial/empty PR state for initialization
 */
export const INITIAL_PR_STATE: PRState = {
  prs: [],
  total: 0,
  isLoading: false,
  error: null,
  statusFilter: 'all',
};

/**
 * Status badge color mapping using Nova design system variables
 */
export const PR_STATUS_COLORS: Record<PRStatus, { bg: string; text: string }> = {
  open: { bg: 'bg-success/10', text: 'text-success' },
  merged: { bg: 'bg-primary/10', text: 'text-primary' },
  closed: { bg: 'bg-destructive/10', text: 'text-destructive' },
  draft: { bg: 'bg-muted', text: 'text-muted-foreground' },
};

/**
 * Merge method labels and descriptions
 */
export const MERGE_METHODS: Record<MergeMethod, { label: string; description: string }> = {
  squash: {
    label: 'Squash and merge',
    description: 'Combine all commits into one before merging',
  },
  merge: {
    label: 'Create merge commit',
    description: 'Preserve all commits with a merge commit',
  },
  rebase: {
    label: 'Rebase and merge',
    description: 'Reapply commits on top of base branch',
  },
};

// ============================================================================
// Type Guards
// ============================================================================

/**
 * Type guard to check if PR is open
 */
export function isPROpen(pr: PullRequest): boolean {
  return pr.status === 'open';
}

/**
 * Type guard to check if PR is merged
 */
export function isPRMerged(pr: PullRequest): boolean {
  return pr.status === 'merged';
}

/**
 * Type guard to check if PR can be merged
 */
export function canMergePR(pr: PullRequest): boolean {
  return pr.status === 'open' && pr.ci_status !== 'failure';
}
