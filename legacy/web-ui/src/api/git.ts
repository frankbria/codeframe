/**
 * Git API Client
 *
 * API functions for Git visualization features.
 * Communicates with the Git REST API endpoints from ticket #270.
 *
 * @see codeframe/ui/routers/git.py for backend implementation
 */

import { authFetch } from '@/lib/api-client';
import type {
  GitStatus,
  GitCommit,
  GitBranch,
  BranchStatus,
  BranchListResponse,
  CommitListResponse,
} from '@/types/git';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

// ============================================================================
// Status Endpoints
// ============================================================================

/**
 * Fetch git working tree status for a project
 *
 * @param projectId - Project ID
 * @returns Git status including current branch and file states
 * @throws Error if request fails or not authenticated
 */
export async function getGitStatus(projectId: number): Promise<GitStatus> {
  return authFetch<GitStatus>(
    `${API_BASE_URL}/api/projects/${projectId}/git/status`
  );
}

// ============================================================================
// Commit Endpoints
// ============================================================================

/**
 * Options for fetching commits
 */
export interface GetCommitsOptions {
  /** Branch name (default: current branch) */
  branch?: string;
  /** Maximum commits to return (1-100, default 50) */
  limit?: number;
}

/**
 * Fetch git commits for a project
 *
 * @param projectId - Project ID
 * @param options - Optional filters for branch and limit
 * @returns Array of commits
 * @throws Error if request fails or not authenticated
 */
export async function getCommits(
  projectId: number,
  options: GetCommitsOptions = {}
): Promise<GitCommit[]> {
  const params = new URLSearchParams();

  if (options.branch) {
    params.append('branch', options.branch);
  }

  if (options.limit !== undefined) {
    params.append('limit', options.limit.toString());
  }

  const queryString = params.toString();
  const url = `${API_BASE_URL}/api/projects/${projectId}/git/commits${
    queryString ? `?${queryString}` : ''
  }`;

  const response = await authFetch<CommitListResponse>(url);
  return response.commits;
}

// ============================================================================
// Branch Endpoints
// ============================================================================

/**
 * Fetch branches for a project
 *
 * @param projectId - Project ID
 * @param status - Optional status filter (active, merged, abandoned)
 * @returns Array of branches
 * @throws Error if request fails or not authenticated
 */
export async function getBranches(
  projectId: number,
  status?: BranchStatus
): Promise<GitBranch[]> {
  const params = new URLSearchParams();

  if (status) {
    params.append('status', status);
  }

  const queryString = params.toString();
  const url = `${API_BASE_URL}/api/projects/${projectId}/git/branches${
    queryString ? `?${queryString}` : ''
  }`;

  const response = await authFetch<BranchListResponse>(url);
  return response.branches;
}

/**
 * Fetch a specific branch by name
 *
 * @param projectId - Project ID
 * @param branchName - Branch name (should NOT be URL-encoded; encoding is handled internally)
 * @returns Branch details
 * @throws Error if request fails, not found, or not authenticated
 */
export async function getBranch(
  projectId: number,
  branchName: string
): Promise<GitBranch> {
  const encodedName = encodeURIComponent(branchName);
  return authFetch<GitBranch>(
    `${API_BASE_URL}/api/projects/${projectId}/git/branches/${encodedName}`
  );
}

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * Fetch current branch name for a project
 *
 * @param projectId - Project ID
 * @returns Current branch name
 * @throws Error if request fails or not authenticated
 */
export async function getCurrentBranch(projectId: number): Promise<string> {
  const status = await getGitStatus(projectId);
  return status.current_branch;
}

/**
 * Fetch recent commits (last 10) for a project
 *
 * @param projectId - Project ID
 * @returns Array of last 10 commits
 * @throws Error if request fails or not authenticated
 */
export async function getRecentCommits(projectId: number): Promise<GitCommit[]> {
  return getCommits(projectId, { limit: 10 });
}
