/**
 * Git Type Definitions for CodeFRAME UI
 *
 * TypeScript interfaces for Git visualization components.
 * These types match the backend API responses from the Git router.
 *
 * @see codeframe/ui/routers/git.py for API response models
 */

// ============================================================================
// Branch Types
// ============================================================================

/**
 * Valid branch status values
 */
export type BranchStatus = 'active' | 'merged' | 'abandoned';

/**
 * Git branch entity matching BranchResponse from backend
 */
export interface GitBranch {
  id: number;
  branch_name: string;
  issue_id: number;
  status: BranchStatus;
  created_at: string;
  merged_at?: string;
  merge_commit?: string;
}

// ============================================================================
// Commit Types
// ============================================================================

/**
 * Git commit entity matching CommitListItem from backend
 */
export interface GitCommit {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  timestamp: string;
  files_changed?: number;
}

// ============================================================================
// Status Types
// ============================================================================

/**
 * Git working tree status matching GitStatusResponse from backend
 */
export interface GitStatus {
  current_branch: string;
  is_dirty: boolean;
  modified_files: string[];
  untracked_files: string[];
  staged_files: string[];
}

// ============================================================================
// State Management Types
// ============================================================================

/**
 * Git state for the Dashboard context
 * Used by GitSection and related components
 */
export interface GitState {
  /** Current git status (null when loading or on error) */
  status: GitStatus | null;

  /** Recent commits (limited to last 10) */
  recentCommits: GitCommit[];

  /** All branches for the project */
  branches: GitBranch[];

  /** Loading state indicator */
  isLoading: boolean;

  /** Error message (null when no error) */
  error: string | null;
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Response from GET /api/projects/{id}/git/branches
 */
export interface BranchListResponse {
  branches: GitBranch[];
}

/**
 * Response from GET /api/projects/{id}/git/commits
 */
export interface CommitListResponse {
  commits: GitCommit[];
}

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Initial/empty Git state for initialization
 */
export const INITIAL_GIT_STATE: GitState = {
  status: null,
  recentCommits: [],
  branches: [],
  isLoading: false,
  error: null,
};

/**
 * Type guard to check if branch is active
 */
export function isBranchActive(branch: GitBranch): boolean {
  return branch.status === 'active';
}

/**
 * Type guard to check if branch is merged
 */
export function isBranchMerged(branch: GitBranch): boolean {
  return branch.status === 'merged';
}
