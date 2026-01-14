/**
 * API client for Quality Gates operations (T066-T068)
 *
 * Part of Sprint 10 Phase 3 (Quality Gates Frontend)
 */

import { authFetch } from '@/lib/api-client';
import type {
  QualityGateStatus,
  TriggerQualityGatesRequest,
  TriggerQualityGatesResponse,
} from '../types/qualityGates';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

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
  if (projectId !== undefined && projectId > 0) {
    url.searchParams.append('project_id', projectId.toString());
  }

  try {
    return await authFetch<QualityGateStatus>(url.toString());
  } catch (error) {
    // Return null for 404 (no quality gate status exists yet)
    if (error instanceof Error && error.message.includes('404')) {
      return null;
    }
    throw error;
  }
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
  return authFetch<TriggerQualityGatesResponse>(
    `${API_BASE_URL}/api/tasks/${request.task_id}/quality-gates`,
    {
      method: 'POST',
      body: { force: request.force || false },
    }
  );
}
