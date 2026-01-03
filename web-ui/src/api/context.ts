/**
 * API client for context management operations (T063)
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import { authFetch } from '@/lib/api-client';
import type {
  ContextStats,
  ContextItem,
  FlashSaveResponse,
  CheckpointMetadata,
} from '../types/context';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

/**
 * Fetch context statistics for an agent
 *
 * @param agentId - Agent ID to get stats for
 * @param projectId - Project ID (required)
 * @returns Promise resolving to ContextStats
 * @throws Error if request fails
 */
export async function fetchContextStats(
  agentId: string,
  projectId: number
): Promise<ContextStats> {
  return authFetch<ContextStats>(
    `${API_BASE_URL}/api/agents/${agentId}/context/stats?project_id=${projectId}`
  );
}

/**
 * Fetch context items for an agent, optionally filtered by tier
 *
 * @param agentId - Agent ID to get items for
 * @param projectId - Project ID (required)
 * @param tier - Optional tier filter ('hot', 'warm', 'cold')
 * @param limit - Maximum number of items to return (default 100)
 * @returns Promise resolving to array of ContextItems
 * @throws Error if request fails
 */
export async function fetchContextItems(
  agentId: string,
  projectId: number,
  tier?: string,
  limit: number = 100
): Promise<ContextItem[]> {
  const params = new URLSearchParams({
    project_id: projectId.toString(),
    limit: limit.toString(),
  });

  if (tier) {
    params.append('tier', tier);
  }

  return authFetch<ContextItem[]>(
    `${API_BASE_URL}/api/agents/${agentId}/context/items?${params.toString()}`
  );
}

/**
 * Trigger a flash save operation for an agent
 *
 * @param agentId - Agent ID to flash save
 * @param projectId - Project ID (required)
 * @param force - Force flash save even if below threshold (default false)
 * @returns Promise resolving to FlashSaveResponse
 * @throws Error if request fails or threshold not met
 */
export async function triggerFlashSave(
  agentId: string,
  projectId: number,
  force: boolean = false
): Promise<FlashSaveResponse> {
  const params = new URLSearchParams({
    project_id: projectId.toString(),
  });

  if (force) {
    params.append('force', 'true');
  }

  return authFetch<FlashSaveResponse>(
    `${API_BASE_URL}/api/agents/${agentId}/flash-save?${params.toString()}`,
    { method: 'POST' }
  );
}

/**
 * List checkpoints for an agent
 *
 * @param agentId - Agent ID to get checkpoints for
 * @param limit - Maximum number of checkpoints to return (default 10)
 * @returns Promise resolving to array of CheckpointMetadata
 * @throws Error if request fails
 */
export async function listCheckpoints(
  agentId: string,
  limit: number = 10
): Promise<CheckpointMetadata[]> {
  return authFetch<CheckpointMetadata[]>(
    `${API_BASE_URL}/api/agents/${agentId}/flash-save/checkpoints?limit=${limit}`
  );
}
