/**
 * Checkpoint types for Sprint 10 Phase 4
 * TypeScript definitions for checkpoint data structures
 */

export interface CheckpointMetadata {
  project_id: number;
  phase: string;
  tasks_completed: number;
  tasks_total: number;
  agents_active: string[];
  last_task_completed?: string;
  context_items_count: number;
  total_cost_usd: number;
}

export interface Checkpoint {
  id: number;
  project_id: number;
  name: string;
  description?: string;
  trigger: 'manual' | 'auto' | 'phase_transition';
  git_commit: string;
  database_backup_path: string;
  context_snapshot_path: string;
  metadata: CheckpointMetadata;
  created_at: string;
}

export interface CreateCheckpointRequest {
  name: string;
  description?: string;
  trigger?: 'manual' | 'auto' | 'phase_transition';
}

export interface RestoreCheckpointRequest {
  confirm: boolean;
}

export interface RestoreCheckpointResponse {
  success: boolean;
  git_commit: string;
  restored_at: string;
  message: string;
}

export interface CheckpointDiff {
  files_changed: number;
  insertions: number;
  deletions: number;
  diff: string;
}
