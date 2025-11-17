/**
 * TypeScript types for Review functionality (T060)
 *
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

/**
 * Review status values
 */
export type ReviewStatus = 'approved' | 'changes_requested' | 'rejected';

/**
 * Finding severity levels
 */
export type FindingSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

/**
 * Finding categories
 */
export type FindingCategory = 'complexity' | 'security' | 'style' | 'coverage' | 'owasp' | 'other';

/**
 * A single review finding
 */
export interface ReviewFinding {
  /** File path where finding was detected */
  file_path: string;

  /** Line number in the file */
  line_number: number;

  /** Finding category */
  category: FindingCategory;

  /** Finding severity */
  severity: FindingSeverity;

  /** Detailed description of the issue */
  message: string;

  /** Optional suggestion for remediation */
  suggestion?: string;
}

/**
 * Complete review report for a task
 */
export interface ReviewReport {
  /** Task ID that was reviewed */
  task_id: number;

  /** ID of the reviewing agent */
  reviewer_agent_id: string;

  /** Overall quality score (0-100) */
  overall_score: number;

  /** Complexity score (0-100) */
  complexity_score: number;

  /** Security score (0-100) */
  security_score: number;

  /** Style score (0-100) */
  style_score: number;

  /** Review status */
  status: ReviewStatus;

  /** List of all findings */
  findings: ReviewFinding[];

  /** Human-readable summary */
  summary: string;

  /** Timestamp when review was created */
  created_at?: string;
}

/**
 * Review status response from API
 */
export interface ReviewStatusResponse {
  /** Whether a review exists for this task */
  has_review: boolean;

  /** Review status (null if no review exists) */
  status: ReviewStatus | null;

  /** Overall score (null if no review exists) */
  overall_score: number | null;

  /** Number of findings (0 if no review exists) */
  findings_count: number;
}

/**
 * Aggregated review statistics for a project
 */
export interface ReviewStats {
  /** Total number of reviews */
  total_reviews: number;

  /** Number of approved reviews */
  approved_count: number;

  /** Number of reviews requesting changes */
  changes_requested_count: number;

  /** Number of rejected reviews */
  rejected_count: number;

  /** Average score across all reviews */
  average_score: number;
}

/**
 * Request payload for triggering a review
 */
export interface ReviewRequest {
  /** Task ID to review */
  task_id: number;

  /** Project ID */
  project_id: number;

  /** List of file paths that were modified */
  files_modified: string[];
}

/**
 * WebSocket event types for review
 */
export type ReviewEventType =
  | 'review_started'
  | 'review_approved'
  | 'review_changes_requested'
  | 'review_rejected'
  | 'review_failed';

/**
 * WebSocket event payload for review events
 */
export interface ReviewWebSocketEvent {
  /** Event type */
  type: ReviewEventType;

  /** Agent ID that performed the review */
  agent_id: string;

  /** Project ID */
  project_id: number;

  /** Task ID that was reviewed */
  task_id: number;

  /** Review status (for completion events) */
  status?: ReviewStatus;

  /** Overall score (for completion events) */
  overall_score?: number;

  /** Number of findings (for completion events) */
  findings_count?: number;

  /** Error message (for failed events) */
  error?: string;

  /** Timestamp of the event */
  timestamp: string;
}
