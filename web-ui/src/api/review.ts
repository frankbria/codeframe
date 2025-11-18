/**
 * API client for Review operations (T061)
 *
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

import type {
  ReviewReport,
  ReviewStatusResponse,
  ReviewStats,
  ReviewRequest,
} from '../types/review';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * Trigger a code review for a task
 *
 * @param agentId - Agent ID to perform the review
 * @param request - Review request payload
 * @returns Promise resolving to ReviewReport
 * @throws Error if request fails
 */
export async function triggerReview(
  agentId: string,
  request: ReviewRequest
): Promise<ReviewReport> {
  const response = await fetch(
    `${API_BASE_URL}/api/agents/${agentId}/review`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to trigger review: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Get review status for a task
 *
 * @param taskId - Task ID to check review status for
 * @returns Promise resolving to ReviewStatusResponse
 * @throws Error if request fails
 */
export async function fetchReviewStatus(
  taskId: number
): Promise<ReviewStatusResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/tasks/${taskId}/review-status`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch review status: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Get aggregated review statistics for a project
 *
 * @param projectId - Project ID to get stats for
 * @returns Promise resolving to ReviewStats
 * @throws Error if request fails
 */
export async function fetchReviewStats(
  projectId: number
): Promise<ReviewStats> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/review-stats`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch review stats: ${response.status} ${errorText}`
    );
  }

  return response.json();
}
