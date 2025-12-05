/**
 * API client for Quality Gates operations (T066-T068)
 *
 * Part of Sprint 10 Phase 3 (Quality Gates Frontend)
 */

import type {
  QualityGateStatus,
  TriggerQualityGatesRequest,
  TriggerQualityGatesResponse,
} from '../types/qualityGates';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch quality gate status for a task
 *
 * @param taskId - Task ID to get quality gate status for
 * @param projectId - Optional project ID for multi-project scoping
 * @returns Promise resolving to QualityGateStatus or null if not found
 * @throws Error if request fails
 */
export async function fetchQualityGateStatus(
  taskId: number,
  projectId?: number
): Promise<QualityGateStatus | null> {
  // Build URL with optional project_id query parameter
  const url = new URL(`${API_BASE_URL}/api/tasks/${taskId}/quality-gates`);
  if (projectId !== undefined) {
    url.searchParams.append('project_id', projectId.toString());
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (response.status === 404) {
    return null; // No quality gate status exists yet
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch quality gate status: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Trigger quality gates for a task
 *
 * @param request - Trigger request with task_id and optional force flag
 * @returns Promise resolving to TriggerQualityGatesResponse
 * @throws Error if request fails
 */
export async function triggerQualityGates(
  request: TriggerQualityGatesRequest
): Promise<TriggerQualityGatesResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/tasks/${request.task_id}/quality-gates`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ force: request.force || false }),
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to trigger quality gates: ${response.status} ${errorText}`
    );
  }

  return response.json();
}
