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
 * Task represents a single unit of work within an issue
 */
export interface Task {
  id: string;
  task_number: string;
  title: string;
  description: string;
  status: WorkStatus;
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
