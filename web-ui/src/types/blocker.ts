/**
 * Blocker types for human-in-the-loop workflow
 *
 * Corresponds to Python models in codeframe/core/models.py
 */

export type BlockerType = 'SYNC' | 'ASYNC';
export type BlockerStatus = 'PENDING' | 'RESOLVED' | 'EXPIRED';

export interface Blocker {
  id: number;
  agent_id: string;
  task_id: number | null;
  blocker_type: BlockerType;
  question: string;
  answer: string | null;
  status: BlockerStatus;
  created_at: string;  // ISO 8601
  resolved_at: string | null;  // ISO 8601

  // Computed fields (from API joins)
  agent_name?: string;
  task_title?: string;
  time_waiting_ms?: number;
}

export interface BlockerCreateRequest {
  agent_id: string;
  task_id: number | null;
  blocker_type: BlockerType;
  question: string;
}

export interface BlockerResolveRequest {
  answer: string;
}

export interface BlockerListResponse {
  blockers: Blocker[];
  total: number;
  pending_count: number;
  sync_count: number;
  async_count: number;
}

/**
 * WebSocket event types for blocker lifecycle
 */

export interface BlockerCreatedEvent {
  type: 'blocker_created';
  project_id: number;
  blocker: Blocker;
}

export interface BlockerResolvedEvent {
  type: 'blocker_resolved';
  project_id: number;
  blocker_id: number;
  answer: string;
  resolved_at: string;
}

export interface AgentResumedEvent {
  type: 'agent_resumed';
  project_id: number;
  agent_id: string;
  task_id: number;
  blocker_id: number;
  resumed_at: string;
}

export interface BlockerExpiredEvent {
  type: 'blocker_expired';
  project_id: number;
  blocker_id: number;
  task_id: number;
  expired_at: string;
}

export type BlockerWebSocketEvent =
  | BlockerCreatedEvent
  | BlockerResolvedEvent
  | AgentResumedEvent
  | BlockerExpiredEvent;
