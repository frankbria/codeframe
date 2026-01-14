/**
 * API client for Review Agent operations (Sprint 10 Phase 2)
 *
 * Tasks: T038
 */

import { authFetch } from '@/lib/api-client';
import type { CodeReview, ReviewResult, Severity } from '../types/reviews';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

/**
 * Get all code reviews for a task
 *
 * @param taskId - Task ID to fetch reviews for
 * @param severity - Optional severity filter
 * @returns Promise resolving to ReviewResult
 * @throws Error if request fails
 */
export async function getTaskReviews(
  taskId: number,
  severity?: Severity
): Promise<ReviewResult> {
  const params = new URLSearchParams();
  if (severity) {
    params.append('severity', severity);
  }

  const url = `${API_BASE_URL}/api/tasks/${taskId}/reviews${
    params.toString() ? `?${params.toString()}` : ''
  }`;

  return authFetch<ReviewResult>(url);
}

/**
 * Trigger a code review for a task
 *
 * @param taskId - Task ID to review
 * @returns Promise resolving to void (review runs asynchronously)
 * @throws Error if request fails
 */
export async function triggerReview(taskId: number): Promise<void> {
  await authFetch<void>(
    `${API_BASE_URL}/api/agents/review/analyze`,
    {
      method: 'POST',
      body: { task_id: taskId },
    }
  );
}

/**
 * Get a single review finding by ID
 *
 * @param reviewId - Review finding ID
 * @returns Promise resolving to CodeReview
 * @throws Error if request fails
 */
export async function getReview(reviewId: number): Promise<CodeReview> {
  return authFetch<CodeReview>(
    `${API_BASE_URL}/api/reviews/${reviewId}`
  );
}
