/**
 * GateStatusIndicator Component
 *
 * Displays status for an individual quality gate with icon, name, and status badge
 * Used in QualityGatesPanel to show overview of all gate types
 */

'use client';

import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';
import { getGateIcon, getGateName, getStatusClasses, getStatusIcon } from '@/lib/qualityGateUtils';

interface GateStatusIndicatorProps {
  gateType: GateTypeE2E;
  status: QualityGateStatusValue;
  testId?: string;
}

/**
 * GateStatusIndicator Component
 *
 * Shows individual gate status in a card layout with proper accessibility
 */
export default function GateStatusIndicator({
  gateType,
  status,
  testId,
}: GateStatusIndicatorProps) {
  const gateName = getGateName(gateType);
  const statusText = status || 'pending';

  return (
    <div
      data-testid={testId || `gate-${gateType}`}
      className="flex flex-col items-center justify-center p-4 bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow"
      role="listitem"
      aria-label={`${gateName} gate: ${statusText}`}
    >
      {/* Gate Icon */}
      <div className="text-3xl mb-2" aria-hidden="true">
        {getGateIcon(gateType)}
      </div>

      {/* Gate Name */}
      <div className="text-sm font-medium text-gray-900 mb-2 text-center">
        {gateName}
      </div>

      {/* Status Badge */}
      <div
        className={`flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-full border ${getStatusClasses(
          status
        )}`}
        role="status"
        aria-label={`Status: ${statusText}`}
      >
        <span aria-hidden="true">{getStatusIcon(status)}</span>
        <span>{statusText}</span>
      </div>
    </div>
  );
}
