/**
 * PhaseIndicator Component (cf-17.2)
 * Displays a color-coded badge showing the current project phase
 */

'use client';

export type ProjectPhase = 'discovery' | 'planning' | 'active' | 'review' | 'complete';

interface PhaseIndicatorProps {
  phase: ProjectPhase | string;
}

interface PhaseConfig {
  label: string;
  bgColor: string;
  textColor: string;
}

const PHASE_CONFIGS: Record<string, PhaseConfig> = {
  discovery: {
    label: 'Discovery',
    bgColor: 'bg-blue-100',
    textColor: 'text-blue-800',
  },
  planning: {
    label: 'Planning',
    bgColor: 'bg-purple-100',
    textColor: 'text-purple-800',
  },
  active: {
    label: 'Active',
    bgColor: 'bg-green-100',
    textColor: 'text-green-800',
  },
  review: {
    label: 'Review',
    bgColor: 'bg-yellow-100',
    textColor: 'text-yellow-800',
  },
  complete: {
    label: 'Complete',
    bgColor: 'bg-gray-100',
    textColor: 'text-gray-800',
  },
};

const DEFAULT_PHASE_CONFIG: PhaseConfig = {
  label: 'Unknown',
  bgColor: 'bg-gray-100',
  textColor: 'text-gray-800',
};

export default function PhaseIndicator({ phase }: PhaseIndicatorProps) {
  // Normalize phase to lowercase for lookup
  const normalizedPhase = phase?.toLowerCase() || '';

  // Get phase configuration or use default
  const config = PHASE_CONFIGS[normalizedPhase] || DEFAULT_PHASE_CONFIG;

  // Create aria-label
  const ariaLabel = `Project phase: ${config.label}`;

  return (
    <span
      data-testid="phase-badge"
      role="status"
      aria-label={ariaLabel}
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${config.bgColor} ${config.textColor}`}
    >
      {config.label}
    </span>
  );
}
