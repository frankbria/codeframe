/**
 * Shared Quality Gate Utilities
 * Centralized helpers for gate icons, names, status classes, etc.
 */

import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';
import {
  TestTube01Icon,
  ChartBarLineIcon,
  FileEditIcon,
  SparklesIcon,
  Search01Icon,
  Settings01Icon,
  CheckmarkCircle01Icon,
  Cancel01Icon,
  Loading03Icon,
  PauseIcon,
  HelpCircleIcon,
} from '@hugeicons/react';

/**
 * Get the icon component for a quality gate type
 * @param gateType - The gate type (E2E or backend naming)
 * @returns Icon React component
 * @example
 * getGateIcon('tests') // returns TestTube01Icon element
 * getGateIcon('type_check') // returns FileEditIcon element
 */
export function getGateIcon(gateType: GateTypeE2E | string): JSX.Element {
  const iconProps = { className: 'h-5 w-5', 'aria-hidden': true as const };
  switch (gateType) {
    case 'tests':
      return <TestTube01Icon {...iconProps} />;
    case 'coverage':
      return <ChartBarLineIcon {...iconProps} />;
    case 'type-check':
    case 'type_check':
      return <FileEditIcon {...iconProps} />;
    case 'lint':
    case 'linting':
      return <SparklesIcon {...iconProps} />;
    case 'review':
    case 'code_review':
      return <Search01Icon {...iconProps} />;
    default:
      return <Settings01Icon {...iconProps} />;
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
 * Get the icon component for a quality gate status
 * @param status - The quality gate status value
 * @returns Icon React component representing the status
 * @example
 * getStatusIcon('passed') // returns CheckmarkCircle01Icon element
 * getStatusIcon('failed') // returns Cancel01Icon element
 * getStatusIcon('running') // returns Loading03Icon element
 */
export function getStatusIcon(status: QualityGateStatusValue): JSX.Element {
  const sharedProps = { 'aria-hidden': true as const };
  switch (status) {
    case 'passed':
      return <CheckmarkCircle01Icon {...sharedProps} className="h-5 w-5 text-secondary" />;
    case 'failed':
      return <Cancel01Icon {...sharedProps} className="h-5 w-5 text-destructive" />;
    case 'running':
      return <Loading03Icon {...sharedProps} className="h-5 w-5 text-primary animate-spin" />;
    case 'pending':
      return <PauseIcon {...sharedProps} className="h-5 w-5 text-muted-foreground" />;
    default:
      return <HelpCircleIcon {...sharedProps} className="h-5 w-5 text-muted-foreground" />;
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
