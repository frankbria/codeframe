/**
 * Agent State Reducer
 *
 * Core reducer for centralized agent state management.
 * Handles all state transitions with immutability and timestamp-based conflict resolution.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Tasks: T020-T034
 */

import type { AgentState, AgentAction } from '@/types/agentState';
import { INITIAL_GIT_STATE } from '@/types/git';

// ============================================================================
// Initial State
// ============================================================================

/**
 * Get initial agent state
 * Used for both initialization and testing
 */
export function getInitialState(): AgentState {
  return {
    agents: [],
    tasks: [],
    activity: [],
    projectProgress: null,
    wsConnected: false,
    lastSyncTimestamp: 0,
    gitState: null,
  };
}

// ============================================================================
// Validation Helpers
// ============================================================================

/**
 * Warn if agent count exceeds recommended maximum
 * Called after state updates that modify agents array
 */
function validateAgentCount(agentCount: number): void {
  if (agentCount > 10) {
    console.warn(
      `Agent count (${agentCount}) exceeds maximum of 10. ` +
      `Performance may be impacted. Consider retiring unused agents.`
    );
  }
}

/**
 * Warn if activity feed exceeds maximum size
 * This should never happen due to FIFO trimming, but check anyway
 */
function validateActivitySize(activityCount: number): void {
  if (activityCount > 50) {
    console.error(
      `Activity feed size (${activityCount}) exceeds maximum of 50. ` +
      `This indicates a bug in the FIFO trimming logic.`
    );
  }
}

// ============================================================================
// Main Reducer
// ============================================================================

/**
 * Agent state reducer
 *
 * Handles all state transitions with the following guarantees:
 * - Immutability: Never mutates state, always returns new objects
 * - Timestamp conflict resolution: Rejects stale updates
 * - FIFO activity feed: Maintains 50-item sliding window
 * - Atomic updates: Multiple related changes happen together
 */
export function agentReducer(
  state: AgentState,
  action: AgentAction
): AgentState {
  // Development mode logging
  if (process.env.NODE_ENV === 'development') {
    console.group(`🔄 Action: ${action.type}`);
    console.log('Previous State:', state);
    console.log('Action Payload:', action.payload);
  }

  let newState: AgentState;

  switch (action.type) {
    // ========================================================================
    // T021: AGENTS_LOADED - Load initial agents
    // ========================================================================
    case 'AGENTS_LOADED': {
      newState = {
        ...state,
        agents: action.payload,
      };
      validateAgentCount(newState.agents.length);
      break;
    }

    // ========================================================================
    // TASKS_LOADED - Load initial tasks from API
    // Enables returning users to see tasks without WebSocket events
    // ========================================================================
    case 'TASKS_LOADED': {
      newState = {
        ...state,
        tasks: action.payload,
      };
      break;
    }

    // ========================================================================
    // T022: AGENT_CREATED - Add new agent
    // ========================================================================
    case 'AGENT_CREATED': {
      newState = {
        ...state,
        agents: [...state.agents, action.payload],
      };
      validateAgentCount(newState.agents.length);
      break;
    }

    // ========================================================================
    // T023: AGENT_UPDATED - Update agent with timestamp conflict resolution
    // ========================================================================
    case 'AGENT_UPDATED': {
      const { agentId, updates, timestamp } = action.payload;
      const existingAgent = state.agents.find((a) => a.id === agentId);

      // Agent not found - no change
      if (!existingAgent) {
        if (process.env.NODE_ENV === 'development') {
          console.warn(`Agent ${agentId} not found for update`);
        }
        newState = state;
        break;
      }

      // Timestamp conflict resolution: reject stale updates
      if (existingAgent.timestamp > timestamp) {
        if (process.env.NODE_ENV === 'development') {
          console.warn(
            `Rejected stale update for agent ${agentId}. ` +
            `Current timestamp: ${existingAgent.timestamp}, ` +
            `Update timestamp: ${timestamp}`
          );
        }
        newState = state; // Return same reference for rejected updates
        break;
      }

      // Apply update
      newState = {
        ...state,
        agents: state.agents.map((agent) =>
          agent.id === agentId
            ? { ...agent, ...updates, timestamp }
            : agent
        ),
      };
      break;
    }

    // ========================================================================
    // T024: AGENT_RETIRED - Remove agent
    // ========================================================================
    case 'AGENT_RETIRED': {
      const { agentId } = action.payload;

      newState = {
        ...state,
        agents: state.agents.filter((agent) => agent.id !== agentId),
      };
      break;
    }

    // ========================================================================
    // T025: TASK_ASSIGNED - Atomic agent + task update
    // ========================================================================
    case 'TASK_ASSIGNED': {
      const { taskId, agentId, projectId, taskTitle, timestamp } = action.payload;

      // Validate projectId before creating task
      if (projectId <= 0) {
        console.warn(`Invalid projectId ${projectId} for TASK_ASSIGNED, skipping task creation`);
        // Only update agent status, don't create task with invalid project_id
        newState = {
          ...state,
          agents: state.agents.map((agent) =>
            agent.id === agentId
              ? {
                  ...agent,
                  status: 'working',
                  current_task: { id: taskId, title: taskTitle || `Task #${taskId}` },
                  timestamp,
                }
              : agent
          ),
        };
        break;
      }

      // Check if task already exists, if not create it
      const existingTask = state.tasks.find((t) => t.id === taskId);
      const updatedTasks = existingTask
        ? state.tasks.map((task) =>
            task.id === taskId
              ? {
                  ...task,
                  status: 'in_progress' as const,
                  agent_id: agentId,
                  timestamp,
                }
              : task
          )
        : [
            ...state.tasks,
            {
              id: taskId,
              project_id: projectId,
              title: taskTitle || `Task #${taskId}`,
              status: 'in_progress' as const,
              agent_id: agentId,
              timestamp,
            },
          ];

      // Update agent status and current task
      newState = {
        ...state,
        tasks: updatedTasks,
        agents: state.agents.map((agent) =>
          agent.id === agentId
            ? {
                ...agent,
                status: 'working',
                current_task: {
                  id: taskId,
                  title: taskTitle || `Task #${taskId}`,
                },
                timestamp,
              }
            : agent
        ),
      };
      break;
    }

    // ========================================================================
    // T026: TASK_STATUS_CHANGED - Update task status and progress
    // ========================================================================
    case 'TASK_STATUS_CHANGED': {
      const { taskId, status, progress, timestamp } = action.payload;

      newState = {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === taskId
            ? {
                ...task,
                status,
                progress,
                timestamp,
              }
            : task
        ),
      };
      break;
    }

    // ========================================================================
    // T027: TASK_BLOCKED - Mark task as blocked with dependencies
    // ========================================================================
    case 'TASK_BLOCKED': {
      const { taskId, blockedBy, timestamp } = action.payload;

      newState = {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === taskId
            ? {
                ...task,
                status: 'blocked',
                blocked_by: blockedBy,
                timestamp,
              }
            : task
        ),
      };
      break;
    }

    // ========================================================================
    // T028: TASK_UNBLOCKED - Unblock task and clear dependencies
    // ========================================================================
    case 'TASK_UNBLOCKED': {
      const { taskId, timestamp } = action.payload;

      newState = {
        ...state,
        tasks: state.tasks.map((task) =>
          task.id === taskId
            ? {
                ...task,
                status: 'pending',
                blocked_by: undefined,
                timestamp,
              }
            : task
        ),
      };
      break;
    }

    // ========================================================================
    // T029: ACTIVITY_ADDED - Add activity with FIFO 50-item limit
    // ========================================================================
    case 'ACTIVITY_ADDED': {
      // Add new item at beginning, keep only first 49 old items (total 50)
      const newActivity = [action.payload, ...state.activity.slice(0, 49)];

      newState = {
        ...state,
        activity: newActivity,
      };

      validateActivitySize(newState.activity.length);
      break;
    }

    // ========================================================================
    // T030: PROGRESS_UPDATED - Update project progress
    // ========================================================================
    case 'PROGRESS_UPDATED': {
      newState = {
        ...state,
        projectProgress: action.payload,
      };
      break;
    }

    // ========================================================================
    // T031: WS_CONNECTED - Update WebSocket connection status
    // ========================================================================
    case 'WS_CONNECTED': {
      newState = {
        ...state,
        wsConnected: action.payload,
      };
      break;
    }

    // ========================================================================
    // T032: FULL_RESYNC - Atomic state replacement after reconnection
    // ========================================================================
    case 'FULL_RESYNC': {
      const { agents, tasks, activity, timestamp } = action.payload;

      newState = {
        ...state,
        agents,
        tasks,
        activity,
        wsConnected: true, // Resync implies connection restored
        lastSyncTimestamp: timestamp,
        // Preserve projectProgress (not included in resync payload)
      };

      validateAgentCount(newState.agents.length);
      validateActivitySize(newState.activity.length);
      break;
    }

    // ========================================================================
    // Git Actions (Ticket #272)
    // ========================================================================

    case 'GIT_STATUS_LOADED': {
      const { status } = action.payload;
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          status,
          isLoading: false,
          error: null,
        },
      };
      break;
    }

    case 'GIT_COMMITS_LOADED': {
      const { commits } = action.payload;
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          recentCommits: commits,
          isLoading: false,
          error: null,
        },
      };
      break;
    }

    case 'GIT_BRANCHES_LOADED': {
      const { branches } = action.payload;
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          branches,
          isLoading: false,
          error: null,
        },
      };
      break;
    }

    case 'COMMIT_CREATED': {
      const { commit } = action.payload;
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      // Prepend new commit, keep only last 10 (FIFO)
      const updatedCommits = [commit, ...currentGitState.recentCommits.slice(0, 9)];

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          recentCommits: updatedCommits,
        },
      };
      break;
    }

    case 'BRANCH_CREATED': {
      const { branch } = action.payload;
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          branches: [...currentGitState.branches, branch],
        },
      };
      break;
    }

    case 'GIT_LOADING': {
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          isLoading: action.payload,
        },
      };
      break;
    }

    case 'GIT_ERROR': {
      const currentGitState = state.gitState ?? { ...INITIAL_GIT_STATE };

      newState = {
        ...state,
        gitState: {
          ...currentGitState,
          error: action.payload,
          isLoading: false,
        },
      };
      break;
    }

    // ========================================================================
    // Default case - unknown action type
    // ========================================================================
    default: {
      // TypeScript exhaustiveness check
      const _exhaustiveCheck: never = action;
      console.warn('Unknown action type:', _exhaustiveCheck);
      newState = state;
      break;
    }
  }

  // Development mode logging
  if (process.env.NODE_ENV === 'development') {
    console.log('Next State:', newState);
    console.groupEnd();
  }

  return newState;
}
