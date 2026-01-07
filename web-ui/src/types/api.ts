/**
 * API Type Definitions for Sprint 2 Foundation
 * Based on API_CONTRACT_ROADMAP.md
 */

// RFC 3339 ISO Date format
export type ISODate = string;

// Work status for tasks and issues
export type WorkStatus = 'pending' | 'assigned' | 'in_progress' | 'blocked' | 'completed' | 'failed';

// Provenance indicator
export type ProposedBy = 'agent' | 'human';

/**
 * Task represents a single unit of work within an issue (API Contract)
 *
 * This is the API response type for tasks from the issues/tasks endpoints.
 * Used primarily for issue/task tree display and Sprint 2 Foundation features.
 * For agent state management and real-time coordination, use Task from @/types/agentState instead.
 *
 * Key differences from AgentState Task:
 * - id is a string (not number) to support issue-task hierarchies
 * - Has task_number for human-readable references
 * - No project_id or timestamp (API contract scoped to endpoint)
 *
 * @see {@link file:web-ui/src/types/agentState.ts} for agent state management Task type
 * @see {@link file:docs/architecture/task-identifiers.md} for identifier semantics
 */
export interface Task {
  /**
   * Unique, stable database identifier. Preferred for `depends_on` references.
   * - Permanent: never changes once assigned
   * - Globally unique across all tasks
   * - String in API responses (integer in backend)
   */
  id: string;

  /**
   * Human-readable hierarchical identifier (e.g., "1.5.3").
   * - Format: {issue_number}.{task_sequence}
   * - May change if tasks are renumbered or reorganized
   * - Project-scoped (not globally unique)
   * - Use for display and debugging, prefer `id` for references
   */
  task_number: string;

  title: string;
  description: string;
  status: WorkStatus;

  /**
   * Task dependency references. Can contain either task IDs or task numbers.
   *
   * The frontend uses dual-lookup matching (see TaskTreeView.tsx) to support both:
   * - `["42", "43"]` - References by stable ID (recommended)
   * - `["1.5.2", "1.5.3"]` - References by task_number (human-readable but less stable)
   *
   * Backend stores as string: empty `""`, single value `"1.5.2"`, or JSON array `"[1, 2]"`.
   * API layer transforms to string array for frontend consumption.
   *
   * @example ["task-123", "task-456"] // IDs - stable, recommended
   * @example ["1.5.2", "1.5.3"] // task_numbers - readable but may change
   * @see docs/architecture/task-identifiers.md for full documentation
   */
  depends_on: string[];

  proposed_by: ProposedBy;
  created_at: ISODate;
  updated_at: ISODate;
  completed_at: ISODate | null;
}

/**
 * Issue represents a feature or problem, containing multiple tasks
 */
export interface Issue {
  id: string;
  issue_number: string;
  title: string;
  description: string;
  status: WorkStatus;
  priority: number;
  depends_on: string[];
  proposed_by: ProposedBy;
  created_at: ISODate;
  updated_at: ISODate;
  completed_at: ISODate | null;
  tasks?: Task[];
}

/**
 * PRD (Product Requirements Document) response
 */
export interface PRDResponse {
  project_id: string;
  prd_content: string;
  generated_at: ISODate;
  updated_at: ISODate;
  status: 'available' | 'generating' | 'not_found';
}

/**
 * Issues list response with pagination
 */
export interface IssuesResponse {
  issues: Issue[];
  total_issues: number;
  total_tasks: number;
  next_cursor?: string;
  prev_cursor?: string;
}

/**
 * Discovery progress response (cf-17.2)
 */
export type ProjectPhase = 'discovery' | 'planning' | 'active' | 'review' | 'complete';
export type DiscoveryState = 'idle' | 'discovering' | 'completed';

export interface CurrentQuestion {
  id: string;
  question: string;
  category: string;
}

export interface DiscoveryInfo {
  state: DiscoveryState;
  progress_percentage: number;
  answered_count: number;
  total_required: number;
  remaining_count?: number;
  current_question?: CurrentQuestion;
}

export interface DiscoveryProgressResponse {
  project_id: number;
  phase: ProjectPhase;
  discovery: DiscoveryInfo | null;
}

/**
 * Task approval request payload for planning phase
 */
export interface TaskApprovalRequest {
  task_ids: string[];
}

/**
 * Task approval response from planning phase
 */
export interface TaskApprovalResponse {
  success: boolean;
  message: string;
  approved_count: number;
  project_phase: ProjectPhase;
}
