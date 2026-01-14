/**
 * Checkpoints API client for Sprint 10 Phase 4
 * Handles all checkpoint CRUD operations
 */

import { authFetch } from '@/lib/api-client';
import type {
  Checkpoint,
  CreateCheckpointRequest,
  RestoreCheckpointResponse,
  CheckpointDiff,
} from '../types/checkpoints';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

/**
 * Error types for checkpoint API operations
 */
export class CheckpointApiError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number,
    public readonly endpoint: string
  ) {
    super(message);
    this.name = 'CheckpointApiError';
  }
}

/**
 * List all checkpoints for a project
 *
 * @throws CheckpointApiError with status code for debugging
 */
export async function listCheckpoints(projectId: number): Promise<Checkpoint[]> {
  const endpoint = `${API_BASE_URL}/api/projects/${projectId}/checkpoints`;

  try {
    const response = await authFetch<{ checkpoints: Checkpoint[] }>(endpoint);
    return response.checkpoints ?? [];
  } catch (error) {
    // Extract status code from error message if available
    const statusMatch = (error as Error)?.message?.match(/Request failed: (\d+)/);
    const statusCode = statusMatch ? parseInt(statusMatch[1], 10) : 0;

    // Log specific error types for debugging
    if (statusCode === 401) {
      console.warn('[Checkpoints API] Authentication required - token may be missing or expired');
    } else if (statusCode === 403) {
      console.warn('[Checkpoints API] Access denied - user may not have project access');
    } else if (statusCode === 404) {
      console.warn(`[Checkpoints API] Project ${projectId} not found`);
    } else if (statusCode >= 500) {
      console.error(`[Checkpoints API] Server error (${statusCode}) fetching checkpoints`);
    }

    // Re-throw with more context
    throw new CheckpointApiError(
      (error as Error)?.message || 'Failed to load checkpoints',
      statusCode,
      endpoint
    );
  }
}

/**
 * Create a new checkpoint for a project
 */
export async function createCheckpoint(
  projectId: number,
  request: CreateCheckpointRequest
): Promise<Checkpoint> {
  return authFetch<Checkpoint>(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints`,
    {
      method: 'POST',
      body: request,
    }
  );
}

/**
 * Get a specific checkpoint by ID
 */
export async function getCheckpoint(
  projectId: number,
  checkpointId: number
): Promise<Checkpoint> {
  return authFetch<Checkpoint>(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}`
  );
}

/**
 * Delete a checkpoint
 */
export async function deleteCheckpoint(
  projectId: number,
  checkpointId: number
): Promise<{ success: boolean; message: string }> {
  return authFetch<{ success: boolean; message: string }>(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}`,
    { method: 'DELETE' }
  );
}

/**
 * Restore a checkpoint (destructive operation)
 */
export async function restoreCheckpoint(
  projectId: number,
  checkpointId: number,
  confirmRestore: boolean
): Promise<RestoreCheckpointResponse> {
  return authFetch<RestoreCheckpointResponse>(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}/restore`,
    {
      method: 'POST',
      body: { confirm_restore: confirmRestore },
    }
  );
}

/**
 * Get diff preview for a checkpoint (for restore confirmation)
 */
export async function getCheckpointDiff(
  projectId: number,
  checkpointId: number,
  signal?: AbortSignal
): Promise<CheckpointDiff> {
  return authFetch<CheckpointDiff>(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}/diff`,
    { signal }
  );
}
