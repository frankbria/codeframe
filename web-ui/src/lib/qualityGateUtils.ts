/**
 * Shared Quality Gate Utilities
 * Centralized helpers for gate icons, names, status classes, etc.
 */

import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';

/**
 * Get the icon emoji for a quality gate type
 * @param gateType - The gate type (E2E or backend naming)
 * @returns Icon emoji string
 * @example
 * getGateIcon('tests') // returns '🧪'
 * getGateIcon('type_check') // returns '📝'
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
 * Get the human-readable display name for a quality gate type
 * @param gateType - The gate type (E2E or backend naming)
 * @returns Human-readable gate name
 * @example
 * getGateName('tests') // returns 'Tests'
 * getGateName('type_check') // returns 'Type Check'
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
 * Get Tailwind CSS classes for status badge styling (Nova palette)
 * @param status - The quality gate status value
 * @returns Tailwind CSS class string for background, text, and border colors
 * @example
 * getStatusClasses('passed') // returns 'bg-secondary text-secondary-foreground border-border'
 * getStatusClasses('failed') // returns 'bg-destructive text-destructive-foreground border-destructive'
 */
export function getStatusClasses(status: QualityGateStatusValue): string {
  switch (status) {
    case 'passed':
      return 'bg-secondary text-secondary-foreground border-border';
    case 'failed':
      return 'bg-destructive text-destructive-foreground border-destructive';
    case 'running':
      return 'bg-primary/20 text-foreground border-border';
    case 'pending':
      return 'bg-muted text-muted-foreground border-border';
    default:
      return 'bg-muted text-muted-foreground border-border';
  }
}

/**
 * Get the icon emoji for a quality gate status
 * @param status - The quality gate status value
 * @returns Icon emoji string representing the status
 * @example
 * getStatusIcon('passed') // returns '✅'
 * getStatusIcon('failed') // returns '❌'
 * getStatusIcon('running') // returns '⏳'
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
 * Get Tailwind CSS classes for severity badge styling (Nova palette)
 * @param severity - The failure severity level (critical, high, medium, low)
 * @returns Tailwind CSS class string for background, text, and border colors
 * @example
 * getSeverityClasses('critical') // returns 'bg-destructive text-destructive-foreground border-destructive'
 * getSeverityClasses('high') // returns 'bg-destructive/80 text-destructive-foreground border-destructive'
 */
export function getSeverityClasses(severity: string): string {
  switch (severity) {
    case 'critical':
      return 'bg-destructive text-destructive-foreground border-destructive';
    case 'high':
      return 'bg-destructive/80 text-destructive-foreground border-destructive';
    case 'medium':
      return 'bg-muted text-foreground border-border';
    case 'low':
      return 'bg-secondary text-secondary-foreground border-border';
    default:
      return 'bg-muted text-muted-foreground border-border';
  }
}
