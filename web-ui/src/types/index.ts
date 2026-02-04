/**
 * TypeScript types for CodeFRAME v2 API responses
 */

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
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  tasks: Task[];
  total: number;
  by_status: TaskStatusCounts;
}

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
