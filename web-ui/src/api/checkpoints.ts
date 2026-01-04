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
 * List all checkpoints for a project
 */
export async function listCheckpoints(projectId: number): Promise<Checkpoint[]> {
  const response = await authFetch<{ checkpoints: Checkpoint[] }>(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints`
  );
  return response.checkpoints ?? [];
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
