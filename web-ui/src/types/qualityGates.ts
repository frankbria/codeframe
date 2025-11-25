/**
 * Quality Gates Type Definitions for Sprint 10 Phase 3
 * Based on backend models in codeframe/core/models.py
 */

/**
 * Quality gate types that can be evaluated
 */
export type QualityGateType = 'tests' | 'type_check' | 'coverage' | 'code_review' | 'linting';

/**
 * Severity levels for quality gate failures
 */
export type QualityGateSeverity = 'critical' | 'high' | 'medium' | 'low';

/**
 * Quality gate status values
 */
export type QualityGateStatusValue = 'pending' | 'running' | 'passed' | 'failed' | null;

/**
 * Individual quality gate failure
 */
export interface QualityGateFailure {
  gate: QualityGateType;
  reason: string;
  details?: string;
  severity: QualityGateSeverity;
}

/**
 * Quality gate status for a task
 */
export interface QualityGateStatus {
  task_id: number;
  status: QualityGateStatusValue;
  failures: QualityGateFailure[];
  requires_human_approval: boolean;
  timestamp: string;
}

/**
 * Request to trigger quality gates manually
 */
export interface TriggerQualityGatesRequest {
  task_id: number;
  force?: boolean;
}

/**
 * Response from triggering quality gates
 */
export interface TriggerQualityGatesResponse {
  task_id: number;
  status: QualityGateStatusValue;
  message: string;
}
