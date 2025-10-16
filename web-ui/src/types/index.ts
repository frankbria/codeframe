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

export interface WebSocketMessage {
  type: string;
  timestamp: string;
  data?: any;
  blocker_id?: number;
  answer?: string;
  project_id?: number;
}
