/**
 * Checkpoints API client for Sprint 10 Phase 4
 * Handles all checkpoint CRUD operations
 */

import type {
  Checkpoint,
  CreateCheckpointRequest,
  RestoreCheckpointRequest,
  RestoreCheckpointResponse,
  CheckpointDiff,
} from '../types/checkpoints';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * List all checkpoints for a project
 */
export async function listCheckpoints(projectId: number): Promise<Checkpoint[]> {
  const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/checkpoints`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to list checkpoints' }));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Create a new checkpoint for a project
 */
export async function createCheckpoint(
  projectId: number,
  request: CreateCheckpointRequest
): Promise<Checkpoint> {
  const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/checkpoints`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to create checkpoint' }));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get a specific checkpoint by ID
 */
export async function getCheckpoint(
  projectId: number,
  checkpointId: number
): Promise<Checkpoint> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to get checkpoint' }));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Delete a checkpoint
 */
export async function deleteCheckpoint(
  projectId: number,
  checkpointId: number
): Promise<{ success: boolean; message: string }> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}`,
    {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to delete checkpoint' }));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Restore a checkpoint (destructive operation)
 */
export async function restoreCheckpoint(
  projectId: number,
  checkpointId: number,
  confirmRestore: boolean
): Promise<RestoreCheckpointResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}/restore`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ confirm_restore: confirmRestore }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to restore checkpoint' }));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get diff preview for a checkpoint (for restore confirmation)
 */
export async function getCheckpointDiff(
  projectId: number,
  checkpointId: number
): Promise<CheckpointDiff> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/checkpoints/${checkpointId}/diff`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to get checkpoint diff' }));
    throw new Error(error.detail || `HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}
