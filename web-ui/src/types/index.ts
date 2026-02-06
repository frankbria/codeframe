/**
 * TypeScript types for CodeFRAME v2 API responses
 */

// PRD & Discovery types (mirrors prd_v2.py + discovery_v2.py)
export type {
  PrdResponse,
  PrdSummaryResponse,
  PrdListResponse,
  PrdDiffResponse,
  StartDiscoveryResponse,
  AnswerResponse,
  DiscoveryStatusResponse,
  GeneratePrdResponse,
  GenerateTasksResponse,
  DiscoveryMessage,
  DiscoveryRole,
  DiscoveryState,
} from './prd';

// Workspace types
export interface WorkspaceResponse {
  id: string;
  repo_path: string;
  state_dir: string;
  tech_stack: string | null;
  created_at: string;
}

export interface WorkspaceExistsResponse {
  exists: boolean;
  path: string;
  state_dir: string | null;
}

// Task types
// Must match backend: codeframe/core/state_machine.py:TaskStatus
export type TaskStatus =
  | 'BACKLOG'
  | 'READY'
  | 'IN_PROGRESS'
  | 'DONE'
  | 'BLOCKED'
  | 'FAILED'
  | 'MERGED';

export interface TaskStatusCounts {
  BACKLOG: number;
  READY: number;
  IN_PROGRESS: number;
  DONE: number;
  BLOCKED: number;
  FAILED: number;
  MERGED: number;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: number;
  depends_on: string[];
  estimated_hours?: number;
  created_at?: string;
  updated_at?: string;
}

export interface TaskListResponse {
  tasks: Task[];
  total: number;
  by_status: TaskStatusCounts;
}

// Batch execution types
// Must match backend: codeframe/ui/routers/tasks_v2.py
export type BatchStrategy = 'serial' | 'parallel' | 'auto';

export interface BatchExecutionRequest {
  task_ids?: string[];
  strategy: BatchStrategy;
  max_parallel?: number;
  retry_count?: number;
}

export interface StartExecutionResponse {
  success: boolean;
  batch_id: string;
  task_count: number;
  strategy: string;
  message: string;
}

export interface TaskStartResponse {
  success: boolean;
  run_id: string;
  task_id: string;
  status: string;
  message: string;
}

// Blocker types
// Must match backend: codeframe/ui/routers/blockers_v2.py
export type BlockerStatus = 'OPEN' | 'ANSWERED' | 'RESOLVED';

export interface Blocker {
  id: string;
  workspace_id: string;
  task_id: string | null;
  question: string;
  answer: string | null;
  status: BlockerStatus;
  created_at: string;
  answered_at: string | null;
}

export interface BlockerListResponse {
  blockers: Blocker[];
  total: number;
  by_status: Record<string, number>;
}

// Batch detail types
// Must match backend: codeframe/ui/routers/batches_v2.py
export interface BatchResponse {
  id: string;
  workspace_id: string;
  task_ids: string[];
  status: string;
  strategy: string;
  max_parallel: number;
  on_failure: string;
  started_at: string | null;
  completed_at: string | null;
  results: Record<string, string>; // task_id → RunStatus
}

// UI-derived agent state for execution monitor display
export type UIAgentState =
  | 'CONNECTING'
  | 'PLANNING'
  | 'EXECUTING'
  | 'VERIFICATION'
  | 'SELF_CORRECTING'
  | 'BLOCKED'
  | 'COMPLETED'
  | 'FAILED'
  | 'DISCONNECTED';

// Activity types (for UI display)
export type ActivityType =
  | 'task_completed'
  | 'run_started'
  | 'blocker_raised'
  | 'workspace_initialized'
  | 'prd_added';

export interface ActivityItem {
  id: string;
  type: ActivityType;
  timestamp: string;
  description: string;
  metadata?: Record<string, unknown>;
}

// Event types (from API)
export interface EventResponse {
  id: number;
  workspace_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface EventListResponse {
  events: EventResponse[];
  total: number;
}

// API Error type
// Note: FastAPI returns detail as string OR array (for validation errors).
// The API client normalizes arrays to strings by joining error messages.
export interface ApiError {
  detail: string;
  status_code?: number;
}
