/**
 * WebSocket Message Mapper
 *
 * Maps incoming WebSocket messages from backend format to reducer actions.
 * Handles timestamp parsing and provides default values for optional fields.
 *
 * Phase 4: WebSocket Integration (T062-T072)
 */

import type { AgentAction } from '@/types/agentState';
import type { WebSocketMessage } from '@/types';

/**
 * Parse timestamp from WebSocket message to Unix milliseconds
 *
 * @param timestamp - String (ISO 8601) or number (Unix ms) from backend
 * @returns Unix milliseconds timestamp
 */
function parseTimestamp(timestamp: string | number): number {
  if (typeof timestamp === 'number') {
    return timestamp;
  }
  return new Date(timestamp).getTime();
}

/**
 * Map a WebSocket message to a reducer action
 *
 * Handles all message types from the backend and transforms them into
 * typed reducer actions. Returns null for unknown message types.
 *
 * @param message - WebSocket message from backend
 * @returns Typed reducer action or null if message type is unknown
 */
export function mapWebSocketMessageToAction(
  message: WebSocketMessage | any
): AgentAction | null {
  const timestamp = parseTimestamp(message.timestamp);

  switch (message.type) {
    // ========================================================================
    // Agent Messages (T063-T065)
    // ========================================================================

    case 'agent_created': {
      const msg = message as WebSocketMessage;
      return {
        type: 'AGENT_CREATED',
        payload: {
          id: msg.agent_id!,
          type: msg.agent_type as any,
          status: 'idle',
          provider: 'anthropic',
          maturity: 'directive',
          context_tokens: 0,
          tasks_completed: msg.tasks_completed || 0,
          timestamp,
        },
      };
    }

    case 'agent_status_changed': {
      const msg = message as WebSocketMessage;
      const updates: any = {
        status: msg.status,
      };

      // Add optional fields if present
      if (msg.current_task !== undefined) {
        updates.current_task = msg.current_task;
      }
      if (msg.progress !== undefined) {
        updates.progress = msg.progress;
      }

      return {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: msg.agent_id!,
          updates,
          timestamp,
        },
      };
    }

    case 'agent_retired': {
      const msg = message as WebSocketMessage;
      return {
        type: 'AGENT_RETIRED',
        payload: {
          agentId: msg.agent_id!,
          timestamp,
        },
      };
    }

    // ========================================================================
    // Task Messages (T066-T068)
    // ========================================================================

    case 'task_assigned': {
      const msg = message as WebSocketMessage;
      return {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: msg.task_id!,
          agentId: msg.agent_id!,
          taskTitle: msg.task_title,
          timestamp,
        },
      };
    }

    case 'task_status_changed': {
      const msg = message as WebSocketMessage;
      return {
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId: msg.task_id!,
          status: msg.status as any,
          progress: msg.progress,
          timestamp,
        },
      };
    }

    case 'task_blocked': {
      const msg = message as WebSocketMessage;
      return {
        type: 'TASK_BLOCKED',
        payload: {
          taskId: msg.task_id!,
          blockedBy: msg.blocked_by || [],
          timestamp,
        },
      };
    }

    case 'task_unblocked': {
      const msg = message as WebSocketMessage;
      return {
        type: 'TASK_UNBLOCKED',
        payload: {
          taskId: msg.task_id!,
          timestamp,
        },
      };
    }

    // ========================================================================
    // Activity and Progress Messages (T069-T071)
    // ========================================================================

    case 'activity_update': {
      const msg = message as WebSocketMessage;
      return {
        type: 'ACTIVITY_ADDED',
        payload: {
          timestamp: message.timestamp.toString(),
          type: (msg.activity_type || 'activity_update') as any,
          agent: msg.agent || 'system',
          message: msg.message || '',
        },
      };
    }

    case 'test_result':
    case 'commit_created':
    case 'correction_attempt': {
      // These are special activity message types
      // Map them to activity updates
      const msg = message as WebSocketMessage;
      return {
        type: 'ACTIVITY_ADDED',
        payload: {
          timestamp: message.timestamp.toString(),
          type: message.type as any,
          agent: msg.agent || 'system',
          message: msg.message || `${message.type} event`,
        },
      };
    }

    case 'progress_update': {
      const msg = message as WebSocketMessage;
      return {
        type: 'PROGRESS_UPDATED',
        payload: {
          completed_tasks: msg.completed_tasks || 0,
          total_tasks: msg.total_tasks || 0,
          percentage: msg.percentage || 0,
        },
      };
    }

    // ========================================================================
    // Unknown Message Type
    // ========================================================================

    default:
      if (process.env.NODE_ENV === 'development') {
        console.warn(`Unknown WebSocket message type: ${message.type}`);
      }
      return null;
  }
}

/**
 * Check if a message should be processed for a given project
 *
 * @param message - WebSocket message
 * @param projectId - Current project ID
 * @returns True if message should be processed
 */
export function shouldProcessMessage(
  message: WebSocketMessage,
  projectId: number
): boolean {
  // Filter by project ID if present in message
  if (message.project_id !== undefined && message.project_id !== projectId) {
    return false;
  }
  return true;
}

/**
 * Process a WebSocket message for a specific project
 *
 * Combines filtering and mapping in a single operation.
 *
 * @param message - WebSocket message
 * @param projectId - Current project ID
 * @returns Reducer action or null if message should be ignored
 */
export function processWebSocketMessage(
  message: WebSocketMessage,
  projectId: number
): AgentAction | null {
  if (!shouldProcessMessage(message, projectId)) {
    return null;
  }
  return mapWebSocketMessageToAction(message);
}
