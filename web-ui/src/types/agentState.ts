/**
 * Agent State Management Type Definitions
 *
 * TypeScript interfaces for the centralized agent state management system.
 * These types define the shape of data flowing through the Context + Reducer architecture.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 */

// ============================================================================
// Core Entity Types
// ============================================================================

/**
 * Agent type specializations supported by the system
 */
export type AgentType =
  | 'lead'                  // Orchestrates other agents
  | 'backend-worker'        // Handles backend code
  | 'frontend-specialist'   // Handles frontend code
  | 'test-engineer';        // Writes and runs tests

/**
 * Current activity status of an agent
 */
export type AgentStatus =
  | 'idle'      // Available for work
  | 'working'   // Executing a task
  | 'blocked';  // Waiting on blocker resolution

/**
 * Agent autonomy level (maturity)
 */
export type AgentMaturity =
  | 'directive'       // Requires detailed instructions
  | 'collaborative'   // Can suggest approaches
  | 'autonomous';     // Self-directed

/**
 * Task execution status
 */
export type TaskStatus =
  | 'pending'       // Not started, no blockers
  | 'in_progress'   // Agent actively working
  | 'blocked'       // Waiting on dependencies
  | 'completed';    // Finished

/**
 * Activity feed event categories
 */
export type ActivityType =
  | 'task_assigned'
  | 'task_completed'
  | 'task_blocked'
  | 'task_unblocked'
  | 'agent_created'
  | 'agent_retired'
  | 'test_result'
  | 'commit_created'
  | 'correction_attempt'
  | 'activity_update'
  | 'blocker_created'
  | 'blocker_resolved';

// ============================================================================
// Entity Interfaces
// ============================================================================

/**
 * Reference to the task an agent is currently working on
 */
export interface CurrentTask {
  id: number;       // Task ID
  title: string;    // Task description
}

/**
 * Individual agent entity with conflict resolution timestamp
 */
export interface Agent {
  id: string;                       // Unique identifier (e.g., "backend-worker-1")
  type: AgentType;                  // Agent specialization
  status: AgentStatus;              // Current activity status
  provider: string;                 // LLM provider (e.g., "anthropic")
  maturity: AgentMaturity;          // Autonomy level
  current_task?: CurrentTask;       // Active task (if working)
  blocker?: string;                 // Blocker description (if blocked)
  context_tokens: number;           // Current context window usage
  tasks_completed: number;          // Historical count
  timestamp: number;                // Unix ms from backend (for conflict resolution)
}

/**
 * Work item that can be assigned to agents (Agent State Management)
 *
 * This is the internal state management type for real-time agent coordination.
 * Used by the Context + Reducer architecture for multi-agent state management (Phase 5.2).
 * For API contract types (issue/task endpoints), use Task from @/types/api instead.
 *
 * Key differences from API Contract Task:
 * - id is a number (not string) matching database primary keys
 * - Has project_id for multi-project support
 * - Has timestamp for conflict resolution (last-write-wins)
 * - Has agent_id for task assignment tracking
 *
 * @see {@link file:web-ui/src/types/api.ts} for API contract Task type
 */
export interface Task {
  id: number;                       // Unique task identifier
  project_id: number;               // Project this task belongs to
  title: string;                    // Task description
  status: TaskStatus;               // Current state
  agent_id?: string;                // Assigned agent (if any)
  blocked_by?: number[];            // Task IDs blocking this task
  progress?: number;                // Completion percentage (0-100)
  timestamp: number;                // Unix ms from backend
}

/**
 * Raw task data from API response
 *
 * Used for type-safe parsing of API responses before transforming to Task.
 * Matches the backend's task serialization format.
 */
export interface APITaskResponse {
  id: number;
  project_id: number;
  title: string;
  status: string;                   // Raw status string from API
  assigned_to?: string;             // Backend uses assigned_to, not agent_id
  depends_on?: string;              // Comma-separated task IDs
  progress?: number;
  timestamp?: number;               // May be missing from API
  // Additional fields from backend (optional)
  task_number?: string;
  description?: string;
  priority?: number;
  workflow_step?: number;
  created_at?: string;
  completed_at?: string;
}

/**
 * Validates that a raw API response has required Task fields
 */
export function isValidTaskResponse(task: unknown): task is APITaskResponse {
  if (typeof task !== 'object' || task === null) return false;
  const t = task as Record<string, unknown>;
  return (
    typeof t.id === 'number' &&
    typeof t.project_id === 'number' &&
    typeof t.title === 'string' &&
    typeof t.status === 'string'
  );
}

/**
 * Transforms an API task response to internal Task type
 */
export function transformAPITask(apiTask: APITaskResponse): Task {
  return {
    id: apiTask.id,
    project_id: apiTask.project_id,
    title: apiTask.title,
    status: apiTask.status as TaskStatus,
    agent_id: apiTask.assigned_to,
    progress: apiTask.progress,
    timestamp: apiTask.timestamp || Date.now(),
  };
}

/**
 * Single entry in the activity feed
 */
export interface ActivityItem {
  timestamp: string;                // ISO 8601 timestamp from backend
  type: ActivityType;               // Event category
  agent: string;                    // Agent ID or "system"
  message: string;                  // Human-readable description
}

/**
 * High-level project progress metrics
 */
export interface ProjectProgress {
  completed_tasks: number;          // Number of finished tasks
  total_tasks: number;              // Total tasks in project
  percentage: number;               // Completion percentage (0-100)
}

// ============================================================================
// Root State
// ============================================================================

/**
 * Root state container for the agent state management system.
 * Managed by useReducer and provided via Context.
 */
export interface AgentState {
  agents: Agent[];                  // All active agents (max 10)
  tasks: Task[];                    // Current tasks
  activity: ActivityItem[];         // Activity feed (max 50 items, FIFO)
  projectProgress: ProjectProgress | null;  // Overall project progress
  wsConnected: boolean;             // WebSocket connection status
  lastSyncTimestamp: number;        // Unix ms of last full sync
}

// ============================================================================
// Reducer Actions
// ============================================================================

/**
 * Load initial agents from API
 */
export interface AgentsLoadedAction {
  type: 'AGENTS_LOADED';
  payload: Agent[];
}

/**
 * Load initial tasks from API
 * Enables returning users to see tasks without WebSocket events
 */
export interface TasksLoadedAction {
  type: 'TASKS_LOADED';
  payload: Task[];
}

/**
 * New agent created by backend
 */
export interface AgentCreatedAction {
  type: 'AGENT_CREATED';
  payload: Agent;
}

/**
 * Partial update to existing agent with timestamp for conflict resolution
 */
export interface AgentUpdatedAction {
  type: 'AGENT_UPDATED';
  payload: {
    agentId: string;
    updates: Partial<Agent>;
    timestamp: number;
  };
}

/**
 * Agent retired/removed by backend
 */
export interface AgentRetiredAction {
  type: 'AGENT_RETIRED';
  payload: {
    agentId: string;
    timestamp: number;
  };
}

/**
 * Task assigned to agent (updates both task and agent atomically)
 */
export interface TaskAssignedAction {
  type: 'TASK_ASSIGNED';
  payload: {
    taskId: number;
    agentId: string;
    projectId: number;     // Required for multi-agent per project architecture
    taskTitle?: string;
    timestamp: number;
  };
}

/**
 * Task status changed
 */
export interface TaskStatusChangedAction {
  type: 'TASK_STATUS_CHANGED';
  payload: {
    taskId: number;
    status: TaskStatus;
    progress?: number;
    timestamp: number;
  };
}

/**
 * Task blocked by dependencies
 */
export interface TaskBlockedAction {
  type: 'TASK_BLOCKED';
  payload: {
    taskId: number;
    blockedBy: number[];
    timestamp: number;
  };
}

/**
 * Task unblocked (dependencies resolved)
 */
export interface TaskUnblockedAction {
  type: 'TASK_UNBLOCKED';
  payload: {
    taskId: number;
    timestamp: number;
  };
}

/**
 * Add new activity item to feed
 */
export interface ActivityAddedAction {
  type: 'ACTIVITY_ADDED';
  payload: ActivityItem;
}

/**
 * Update project-level progress
 */
export interface ProgressUpdatedAction {
  type: 'PROGRESS_UPDATED';
  payload: ProjectProgress;
}

/**
 * WebSocket connection status changed
 */
export interface WebSocketConnectedAction {
  type: 'WS_CONNECTED';
  payload: boolean;
}

/**
 * Full state resync after WebSocket reconnection
 */
export interface FullResyncAction {
  type: 'FULL_RESYNC';
  payload: {
    agents: Agent[];
    tasks: Task[];
    activity: ActivityItem[];
    timestamp: number;
  };
}

/**
 * Discriminated union of all possible reducer actions
 */
export type AgentAction =
  | AgentsLoadedAction
  | TasksLoadedAction
  | AgentCreatedAction
  | AgentUpdatedAction
  | AgentRetiredAction
  | TaskAssignedAction
  | TaskStatusChangedAction
  | TaskBlockedAction
  | TaskUnblockedAction
  | ActivityAddedAction
  | ProgressUpdatedAction
  | WebSocketConnectedAction
  | FullResyncAction;

// ============================================================================
// Utility Types
// ============================================================================

/**
 * Type guard to check if an agent is working
 */
export function isAgentWorking(agent: Agent): boolean {
  return agent.status === 'working';
}

/**
 * Type guard to check if a task is active
 */
export function isTaskActive(task: Task): boolean {
  return task.status === 'in_progress';
}

/**
 * Type guard to check if an agent is blocked
 */
export function isAgentBlocked(agent: Agent): boolean {
  return agent.status === 'blocked';
}

/**
 * Type guard to check if a task is blocked
 */
export function isTaskBlocked(task: Task): boolean {
  return task.status === 'blocked';
}
