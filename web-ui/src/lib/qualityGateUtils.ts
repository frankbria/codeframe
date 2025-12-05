/**
 * Shared Quality Gate Utilities
 * Centralized helpers for gate icons, names, status classes, etc.
 */

import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';

/**
 * Get icon for gate type (E2E naming)
 */
export function getGateIcon(gateType: GateTypeE2E | string): string {
  switch (gateType) {
    case 'tests':
      return '🧪';
    case 'coverage':
      return '📊';
    case 'type-check':
    case 'type_check':
      return '📝';
    case 'lint':
    case 'linting':
      return '✨';
    case 'review':
    case 'code_review':
      return '🔍';
    default:
      return '⚙️';
  }
}

/**
 * Get display name for gate type (E2E naming)
 */
export function getGateName(gateType: GateTypeE2E | string): string {
  switch (gateType) {
    case 'tests':
      return 'Tests';
    case 'coverage':
      return 'Coverage';
    case 'type-check':
    case 'type_check':
      return 'Type Check';
    case 'lint':
    case 'linting':
      return 'Linting';
    case 'review':
    case 'code_review':
      return 'Code Review';
    default:
      return gateType;
  }
}

/**
 * Get status badge classes based on status value
 */
export function getStatusClasses(status: QualityGateStatusValue): string {
  switch (status) {
    case 'passed':
      return 'bg-green-100 text-green-800 border-green-300';
    case 'failed':
      return 'bg-red-100 text-red-800 border-red-300';
    case 'running':
      return 'bg-yellow-100 text-yellow-800 border-yellow-300';
    case 'pending':
      return 'bg-gray-100 text-gray-800 border-gray-300';
    default:
      return 'bg-gray-100 text-gray-500 border-gray-200';
  }
}

/**
 * Get status icon based on status value
 */
export function getStatusIcon(status: QualityGateStatusValue): string {
  switch (status) {
    case 'passed':
      return '✅';
    case 'failed':
      return '❌';
    case 'running':
      return '⏳';
    case 'pending':
      return '⏸️';
    default:
      return '❓';
  }
}

/**
 * Get severity badge classes
 */
export function getSeverityClasses(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-900 border-red-300';
    case 'high':
      return 'bg-orange-100 text-orange-900 border-orange-300';
    case 'medium':
      return 'bg-yellow-100 text-yellow-900 border-yellow-300';
    case 'low':
      return 'bg-blue-100 text-blue-900 border-blue-300';
    default:
      return 'bg-gray-100 text-gray-900 border-gray-300';
  }
}
