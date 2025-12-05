/**
 * Quality Gates Type Definitions for Sprint 10 Phase 3
 * Based on backend models in codeframe/core/models.py
 */

/**
 * Backend naming convention for quality gates
 * (used in API responses and database)
 *
 * Note: This is the canonical backend type. Use GateTypeBackend alias below for clarity.
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

/**
 * E2E test naming convention for quality gates
 * (used in test IDs and frontend display)
 */
export type GateTypeE2E = 'tests' | 'coverage' | 'type-check' | 'lint' | 'review';

/**
 * Backend naming convention for quality gates (alias of QualityGateType)
 * Use this for clarity when working with backend API responses
 */
export type GateTypeBackend = QualityGateType;

/**
 * Map E2E gate type to backend gate type
 * @param gateType - E2E gate type (kebab-case)
 * @returns Backend gate type (snake_case)
 */
export function mapE2EToBackend(gateType: GateTypeE2E): GateTypeBackend {
  const mapping: Record<GateTypeE2E, GateTypeBackend> = {
    'tests': 'tests',
    'coverage': 'coverage',
    'type-check': 'type_check',
    'lint': 'linting',
    'review': 'code_review',
  };
  return mapping[gateType];
}

/**
 * Map backend gate type to E2E gate type
 * @param gateType - Backend gate type (snake_case)
 * @returns E2E gate type (kebab-case)
 */
export function mapBackendToE2E(gateType: GateTypeBackend): GateTypeE2E {
  const mapping: Record<GateTypeBackend, GateTypeE2E> = {
    'tests': 'tests',
    'coverage': 'coverage',
    'type_check': 'type-check',
    'linting': 'lint',
    'code_review': 'review',
  };
  return mapping[gateType];
}

/**
 * All quality gate types in E2E naming convention
 * Centralized constant to ensure consistency across components
 */
export const ALL_GATE_TYPES_E2E: readonly GateTypeE2E[] =
  ['tests', 'coverage', 'type-check', 'lint', 'review'] as const;
