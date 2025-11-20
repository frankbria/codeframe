/**
 * Agent State Synchronization
 *
 * Handles full state resynchronization after WebSocket reconnection.
 * Fetches all agents, tasks, and activity in parallel to rebuild state.
 *
 * Phase 5: Reconnection & Resync (T085-T087)
 */

import { agentsApi, tasksApi, activityApi } from '@/lib/api';
import type { Agent, Task, ActivityItem } from '@/types/agentState';

/**
 * Payload returned from full state resync
 */
export interface FullResyncPayload {
  agents: Agent[];
  tasks: Task[];
  activity: ActivityItem[];
  timestamp: number;
}

/**
 * Perform a full state resynchronization by fetching all data from APIs
 *
 * This function is called after WebSocket reconnection to ensure the frontend
 * has the latest state from the backend. It fetches agents, tasks, and activity
 * in parallel for optimal performance.
 *
 * **Features**:
 * - Parallel API fetches using Promise.all (T086)
 * - Error handling with descriptive messages (T087)
 * - Handles empty or missing data gracefully (T087)
 * - Generates timestamp for conflict resolution
 *
 * **Usage**:
 * ```typescript
 * try {
 *   const freshState = await fullStateResync(projectId);
 *   dispatch({ type: 'FULL_RESYNC', payload: freshState });
 * } catch (error) {
 *   console.error('Resync failed:', error);
 *   // Handle error (show notification, retry, etc.)
 * }
 * ```
 *
 * @param projectId - Project ID to fetch data for
 * @returns Promise resolving to complete state with timestamp
 * @throws Error if any API call fails
 */
export async function fullStateResync(
  projectId: number
): Promise<FullResyncPayload> {
  // Generate timestamp for this resync operation
  const timestamp = Date.now();

  try {
    // Fetch all data in parallel for optimal performance (T086)
    const [agentsRes, tasksRes, activityRes] = await Promise.all([
      agentsApi.list(projectId),
      tasksApi.list(projectId, { limit: 100 }),
      activityApi.list(projectId, 50), // Fetch 50 most recent activity items
    ]);

    // Extract data from responses, handling undefined/null gracefully (T087)
    const agents = (agentsRes.data?.agents || []) as unknown as Agent[];
    const tasks = (tasksRes.data?.tasks || []) as unknown as Task[];
    const activity = (activityRes.data?.activity || []) as unknown as ActivityItem[];

    // Return complete state payload
    return {
      agents,
      tasks,
      activity,
      timestamp,
    };
  } catch (error) {
    // Add context to error for better debugging (T087)
    if (error instanceof Error) {
      throw new Error(
        `Full state resync failed for project ${projectId}: ${error.message}`
      );
    }
    throw new Error(`Full state resync failed for project ${projectId}`);
  }
}

/**
 * Retry a function with exponential backoff
 *
 * Useful for retrying failed resync operations due to transient network errors.
 *
 * @param fn - Async function to retry
 * @param maxRetries - Maximum number of retry attempts (default: 3)
 * @param initialDelay - Initial delay in milliseconds (default: 1000)
 * @returns Promise resolving to function result
 * @throws Error if all retries fail
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  initialDelay: number = 1000
): Promise<T> {
  let lastError: Error | unknown;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // Don't retry on last attempt
      if (attempt === maxRetries - 1) {
        break;
      }

      // Calculate exponential backoff delay: 1s, 2s, 4s, 8s, etc.
      const delay = initialDelay * Math.pow(2, attempt);

      if (process.env.NODE_ENV === 'development') {
        console.log(
          `Retry attempt ${attempt + 1}/${maxRetries} after ${delay}ms delay`
        );
      }

      // Wait before retrying
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  // All retries failed
  if (lastError instanceof Error) {
    throw new Error(
      `Operation failed after ${maxRetries} attempts: ${lastError.message}`
    );
  }
  throw new Error(`Operation failed after ${maxRetries} attempts`);
}

/**
 * Perform full state resync with automatic retry on failure
 *
 * Wrapper around fullStateResync that adds retry logic for transient failures.
 *
 * @param projectId - Project ID to fetch data for
 * @param maxRetries - Maximum retry attempts (default: 3)
 * @returns Promise resolving to complete state with timestamp
 * @throws Error if all retries fail
 */
export async function fullStateResyncWithRetry(
  projectId: number,
  maxRetries: number = 3
): Promise<FullResyncPayload> {
  return retryWithBackoff(() => fullStateResync(projectId), maxRetries);
}
