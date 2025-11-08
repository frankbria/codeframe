/**
 * Agent State Management API Contracts
 *
 * TypeScript interfaces for the centralized agent state management system.
 * These contracts define the shape of data flowing through the Context + Reducer architecture.
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
 * Work item that can be assigned to agents
 */
export interface Task {
  id: number;                       // Unique task identifier
  title: string;                    // Task description
  status: TaskStatus;               // Current state
  agent_id?: string;                // Assigned agent (if any)
  blocked_by?: number[];            // Task IDs blocking this task
  progress?: number;                // Completion percentage (0-100)
  timestamp: number;                // Unix ms from backend
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
// Context API
// ============================================================================

/**
 * Context value provided to consuming components
 */
export interface AgentStateContextValue {
  state: AgentState;
  dispatch: React.Dispatch<AgentAction>;
}

/**
 * Props for AgentStateProvider component
 */
export interface AgentStateProviderProps {
  projectId: number;
  children: React.ReactNode;
}

// ============================================================================
// WebSocket Message Types (Backend → Frontend)
// ============================================================================

/**
 * Base structure for all WebSocket messages from backend
 */
export interface WebSocketMessage {
  type: string;
  project_id: number;
  timestamp: string | number;
  [key: string]: any;  // Additional fields per message type
}

/**
 * Agent created message
 */
export interface AgentCreatedMessage extends WebSocketMessage {
  type: 'agent_created';
  agent_id: string;
  agent_type: AgentType;
  provider?: string;
}

/**
 * Agent status changed message
 */
export interface AgentStatusChangedMessage extends WebSocketMessage {
  type: 'agent_status_changed';
  agent_id: string;
  status: AgentStatus;
  current_task?: CurrentTask;
  progress?: number;
}

/**
 * Agent retired message
 */
export interface AgentRetiredMessage extends WebSocketMessage {
  type: 'agent_retired';
  agent_id: string;
}

/**
 * Task assigned message
 */
export interface TaskAssignedMessage extends WebSocketMessage {
  type: 'task_assigned';
  task_id: number;
  agent_id: string;
  task_title?: string;
}

/**
 * Task status changed message
 */
export interface TaskStatusChangedMessage extends WebSocketMessage {
  type: 'task_status_changed';
  task_id: number;
  status: TaskStatus;
  progress?: number;
}

/**
 * Task blocked message
 */
export interface TaskBlockedMessage extends WebSocketMessage {
  type: 'task_blocked';
  task_id: number;
  blocked_by: number[];
}

/**
 * Task unblocked message
 */
export interface TaskUnblockedMessage extends WebSocketMessage {
  type: 'task_unblocked';
  task_id: number;
}

/**
 * Activity update message
 */
export interface ActivityUpdateMessage extends WebSocketMessage {
  type: 'activity_update';
  activity_type?: ActivityType;
  agent?: string;
  message: string;
}

/**
 * Progress update message
 */
export interface ProgressUpdateMessage extends WebSocketMessage {
  type: 'progress_update';
  completed_tasks: number;
  total_tasks: number;
  percentage: number;
}

// ============================================================================
// API Response Types (REST API)
// ============================================================================

/**
 * Response from GET /projects/{id}/agents
 */
export interface AgentsAPIResponse {
  agents: Agent[];
}

/**
 * Response from GET /projects/{id}/tasks
 */
export interface TasksAPIResponse {
  tasks: Task[];
}

/**
 * Response from GET /projects/{id}/activity
 */
export interface ActivityAPIResponse {
  activity: ActivityItem[];
}

/**
 * Payload for full state resync
 */
export interface FullResyncPayload {
  agents: Agent[];
  tasks: Task[];
  activity: ActivityItem[];
  timestamp: number;
}

// ============================================================================
// Hook Return Types
// ============================================================================

/**
 * Return value from useAgentState hook
 */
export interface UseAgentStateReturn {
  // State
  agents: Agent[];
  tasks: Task[];
  activity: ActivityItem[];
  projectProgress: ProjectProgress | null;
  wsConnected: boolean;
  lastSyncTimestamp: number;

  // Derived state (memoized)
  activeAgents: Agent[];        // Agents with status 'working' or 'blocked'
  idleAgents: Agent[];          // Agents with status 'idle'
  activeTasks: Task[];          // Tasks with status 'in_progress'
  blockedTasks: Task[];         // Tasks with status 'blocked'

  // Actions (wrapped dispatch functions)
  loadAgents: (agents: Agent[]) => void;
  createAgent: (agent: Agent) => void;
  updateAgent: (agentId: string, updates: Partial<Agent>, timestamp: number) => void;
  retireAgent: (agentId: string, timestamp: number) => void;
  assignTask: (taskId: number, agentId: string, taskTitle: string | undefined, timestamp: number) => void;
  updateTaskStatus: (taskId: number, status: TaskStatus, progress: number | undefined, timestamp: number) => void;
  blockTask: (taskId: number, blockedBy: number[], timestamp: number) => void;
  unblockTask: (taskId: number, timestamp: number) => void;
  addActivity: (item: ActivityItem) => void;
  updateProgress: (progress: ProjectProgress) => void;
  setWSConnected: (connected: boolean) => void;
  fullResync: (payload: FullResyncPayload) => void;
}

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

/**
 * Parse backend timestamp to Unix milliseconds
 */
export function parseTimestamp(timestamp: string | number): number {
  if (typeof timestamp === 'number') return timestamp;
  return new Date(timestamp).getTime();
}

/**
 * Validate agent count constraint
 */
export function validateAgentCount(agents: Agent[]): void {
  if (agents.length > 10) {
    console.warn(`Agent count (${agents.length}) exceeds maximum of 10`);
  }
}

/**
 * Validate activity feed size constraint
 */
export function validateActivitySize(activity: ActivityItem[]): void {
  if (activity.length > 50) {
    console.error('Activity feed exceeds 50 items - should have been trimmed');
  }
}
