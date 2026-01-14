/**
 * API client for Review operations (T061)
 *
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

import { authFetch } from '@/lib/api-client';
import type {
  ReviewReport,
  ReviewStatusResponse,
  ReviewStats,
  ReviewRequest,
} from '../types/review';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

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
  return authFetch<ReviewReport>(
    `${API_BASE_URL}/api/agents/${agentId}/review`,
    {
      method: 'POST',
      body: request,
    }
  );
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
  return authFetch<ReviewStatusResponse>(
    `${API_BASE_URL}/api/tasks/${taskId}/review-status`
  );
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
  return authFetch<ReviewStats>(
    `${API_BASE_URL}/api/projects/${projectId}/review-stats`
  );
}
