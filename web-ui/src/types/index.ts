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
  requirement_ids?: string[];
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

// Review & Commit View types
// Must match backend: codeframe/ui/routers/review_v2.py + gates_v2.py + git_v2.py + pr_v2.py
export type FileChangeType = 'modified' | 'added' | 'deleted' | 'renamed';

export interface FileChange {
  path: string;
  change_type: FileChangeType;
  insertions: number;
  deletions: number;
}

export interface DiffStatsResponse {
  diff: string;
  files_changed: number;
  insertions: number;
  deletions: number;
  changed_files: FileChange[];
}

export interface PatchResponse {
  patch: string;
  filename: string;
}

export interface CommitMessageResponse {
  message: string;
}

// Gate types (mirrors gates_v2.py)
export type GateStatus = 'PASSED' | 'FAILED' | 'SKIPPED' | 'ERROR';

export interface GateCheck {
  name: string;
  status: GateStatus;
  exit_code: number | null;
  output: string;
  duration_ms: number;
}

export interface GateResult {
  passed: boolean;
  checks: GateCheck[];
  summary: string;
  started_at: string | null;
  completed_at: string | null;
}

// Git types (mirrors git_v2.py)
export interface GitStatusResponse {
  current_branch: string;
  is_dirty: boolean;
  modified_files: string[];
  untracked_files: string[];
  staged_files: string[];
}

export interface CommitResultResponse {
  commit_hash: string;
  commit_message: string;
  files_changed: number;
}

// PR types (mirrors pr_v2.py)
export interface PRResponse {
  number: number;
  url: string;
  state: string;
  title: string;
  body: string | null;
  created_at: string;
  merged_at: string | null;
  head_branch: string;
  base_branch: string;
}

export interface CreatePRRequest {
  branch: string;
  title: string;
  body?: string;
  base?: string;
}

// PROOF9 types (mirrors proof_v2.py)
export type ProofReqStatus = 'open' | 'satisfied' | 'waived';
export type ProofSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface ProofObligation {
  gate: string;
  status: string;
}

export interface ProofEvidenceRule {
  test_id: string;
  must_pass: boolean;
}

export interface ProofWaiver {
  reason: string;
  expires: string | null;
  manual_checklist: string[];
  approved_by: string;
}

export interface ProofRequirement {
  id: string;
  title: string;
  description: string;
  severity: ProofSeverity;
  source: string;
  status: ProofReqStatus;
  glitch_type: string | null;
  obligations: ProofObligation[];
  evidence_rules: ProofEvidenceRule[];
  waiver: ProofWaiver | null;
  created_at: string | null;
  satisfied_at: string | null;
  created_by: string;
  source_issue: string | null;
  related_reqs: string[];
}

export interface ProofRequirementListResponse {
  requirements: ProofRequirement[];
  total: number;
  by_status: Partial<Record<ProofReqStatus, number>>;
}

export interface ProofEvidence {
  req_id: string;
  gate: string;
  satisfied: boolean;
  artifact_path: string;
  artifact_checksum: string;
  timestamp: string;
  run_id: string;
}

export interface ProofStatusResponse {
  total: number;
  open: number;
  satisfied: number;
  waived: number;
  requirements: ProofRequirement[];
}

export interface WaiveRequest {
  reason: string;
  expires: string | null;
  manual_checklist: string[];
  approved_by: string;
}


// Quick Actions props (dashboard)
export interface QuickActionsProps {
  taskCounts?: TaskStatusCounts;
}

// Completion banner props (execution page)
export interface CompletionBannerProps {
  status: 'completed' | 'failed' | 'blocked' | null;
  duration: number | null;
  onViewProof: () => void;
  onViewChanges: () => void;
  onBackToTasks: () => void;
  onViewBlockers: () => void;
  gateResult?: GateResult | null;
  gateRunning?: boolean;
  gateError?: boolean;
}

// Pipeline progress types
export interface PhaseStatus {
  isComplete: boolean;
  isLoading: boolean;
  isError: boolean;
}

export interface PipelineStatus {
  think: PhaseStatus;
  build: PhaseStatus;
  prove: PhaseStatus;
  ship: PhaseStatus;
}
