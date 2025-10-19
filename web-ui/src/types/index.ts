/**
 * TypeScript type definitions for CodeFRAME UI
 */

export type ProjectStatus = 'init' | 'planning' | 'active' | 'paused' | 'completed';

export type TaskStatus = 'pending' | 'assigned' | 'in_progress' | 'blocked' | 'completed' | 'failed';

export type AgentType = 'lead' | 'backend' | 'frontend' | 'test' | 'review';

export type AgentMaturity = 'directive' | 'coaching' | 'supporting' | 'delegating';

export type AgentStatus = 'idle' | 'working' | 'blocked' | 'offline';

export type BlockerSeverity = 'sync' | 'async';

export interface Project {
  id: number;
  name: string;
  status: ProjectStatus;
  phase?: string;
  workflow_step?: number;
  created_at?: string;
  progress: {
    completed_tasks: number;
    total_tasks: number;
    percentage: number;
  };
  time_tracking?: {
    started_at: string;
    elapsed_hours: number;
    estimated_remaining_hours: number;
  };
  cost_tracking?: {
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
  };
}

export interface Agent {
  id: string;
  type: AgentType;
  provider: string;
  maturity: AgentMaturity;
  status: AgentStatus;
  current_task?: {
    id: number;
    title: string;
  };
  progress?: number;
  tests_passing?: number;
  tests_total?: number;
  context_tokens?: number;
  last_action?: string;
  blocker?: string;
  tasks_completed?: number; // Sprint 4: Multi-Agent Coordination
}

export interface Task {
  id: number;
  title: string;
  description: string;
  status: TaskStatus;
  assigned_to?: string;
  priority: number;
  workflow_step: number;
  progress?: number;
  depends_on?: number[];
}

export interface Blocker {
  id: number;
  task_id: number;
  severity: BlockerSeverity;
  question: string;
  reason: string;
  created_at: string;
  blocking_agents?: string[];
}

export interface ActivityItem {
  timestamp: string;
  type: string;
  agent: string;
  message: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

/**
 * WebSocket message types for real-time dashboard updates (cf-45)
 * Sprint 4: Multi-Agent Coordination message types added
 */
export type WebSocketMessageType =
  | 'task_status_changed'
  | 'agent_status_changed'
  | 'test_result'
  | 'commit_created'
  | 'activity_update'
  | 'progress_update'
  | 'correction_attempt'
  | 'agent_started'
  | 'status_update'
  | 'chat_message'
  | 'blocker_resolved'
  | 'ping'
  | 'pong'
  | 'subscribe'
  | 'subscribed'
  | 'agent_created'      // Sprint 4
  | 'agent_retired'      // Sprint 4
  | 'task_assigned'      // Sprint 4
  | 'task_blocked'       // Sprint 4
  | 'task_unblocked';    // Sprint 4

export interface WebSocketMessage {
  type: WebSocketMessageType;
  timestamp: string;
  project_id?: number;
  data?: any;

  // Legacy fields (for backward compatibility)
  blocker_id?: number;
  answer?: string;

  // task_status_changed fields
  task_id?: number;
  status?: string;
  agent_id?: string;
  progress?: number;

  // agent_status_changed fields
  current_task?: {
    id: number;
    title: string;
  };

  // test_result fields
  passed?: number;
  failed?: number;
  errors?: number;
  total?: number;
  duration?: number;

  // commit_created fields
  commit_hash?: string;
  commit_message?: string;
  files_changed?: string[];

  // activity_update fields
  activity_type?: string;
  agent?: string;
  message?: string;

  // progress_update fields
  completed_tasks?: number;
  total_tasks?: number;
  percentage?: number;

  // correction_attempt fields
  attempt_number?: number;
  max_attempts?: number;
  error_summary?: string;

  // chat_message fields
  role?: 'user' | 'assistant';
  content?: string;

  // Sprint 4: Multi-Agent Coordination fields
  agent_type?: string;           // agent_created
  tasks_completed?: number;      // agent_created, agent_retired
  task_title?: string;           // task_assigned, task_blocked, task_unblocked
  blocked_by?: number[];         // task_blocked
  blocked_count?: number;        // task_blocked
  unblocked_by?: number;         // task_unblocked
}

/**
 * Response from creating a new project
 */
export interface ProjectResponse {
  id: number;
  name: string;
  status: ProjectStatus;
  phase?: string;
  created_at: string;
  config?: Record<string, any>;
}

/**
 * Response from starting a project
 */
export interface StartProjectResponse {
  message: string;
  status: string;
}

/**
 * Task dependency relationship (Sprint 4: Multi-Agent Coordination)
 */
export interface TaskDependency {
  id: number;
  task_id: number;
  depends_on_task_id: number;
}