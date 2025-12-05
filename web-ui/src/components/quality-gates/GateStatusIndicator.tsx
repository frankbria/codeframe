/**
 * GateStatusIndicator Component
 *
 * Displays status for an individual quality gate with icon, name, and status badge
 * Used in QualityGatesPanel to show overview of all gate types
 */

'use client';

import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';

interface GateStatusIndicatorProps {
  gateType: GateTypeE2E;
  status: QualityGateStatusValue;
  testId?: string;
}

/**
 * Get icon for gate type
 */
function getGateIcon(gateType: GateTypeE2E): string {
  switch (gateType) {
    case 'tests':
      return '🧪';
    case 'coverage':
      return '📊';
    case 'type-check':
      return '📝';
    case 'lint':
      return '✨';
    case 'review':
      return '🔍';
    default:
      return '⚙️';
  }
}

/**
 * Get display name for gate type
 */
function getGateName(gateType: GateTypeE2E): string {
  switch (gateType) {
    case 'tests':
      return 'Tests';
    case 'coverage':
      return 'Coverage';
    case 'type-check':
      return 'Type Check';
    case 'lint':
      return 'Linting';
    case 'review':
      return 'Code Review';
    default:
      return gateType;
  }
}

/**
 * Get status badge classes
 */
function getStatusClasses(status: QualityGateStatusValue): string {
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
 * Get status icon
 */
function getStatusIcon(status: QualityGateStatusValue): string {
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
 * GateStatusIndicator Component
 *
 * Shows individual gate status in a card layout
 */
export default function GateStatusIndicator({
  gateType,
  status,
  testId,
}: GateStatusIndicatorProps) {
  return (
    <div
      data-testid={testId || `gate-${gateType}`}
      className="flex flex-col items-center justify-center p-4 bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow"
    >
      {/* Gate Icon */}
      <div className="text-3xl mb-2">{getGateIcon(gateType)}</div>

      {/* Gate Name */}
      <div className="text-sm font-medium text-gray-900 mb-2 text-center">
        {getGateName(gateType)}
      </div>

      {/* Status Badge */}
      <div
        className={`flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full border ${getStatusClasses(
          status
        )}`}
      >
        <span>{getStatusIcon(status)}</span>
        <span>{status || 'unknown'}</span>
      </div>
    </div>
  );
}
