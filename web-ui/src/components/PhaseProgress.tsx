/**
 * PhaseProgress Component
 * Visualizes the current project phase with icons, step counters, and progress bars
 *
 * Note: totalSteps defaults to 15 which matches the codeframe workflow phases.
 * The nextAction prop is available for future integration when the backend
 * provides suggested next actions.
 */

'use client';

export interface PhaseProgressProps {
  phase: string;
  currentStep: number;
  totalSteps: number;
  nextAction?: string;
}

export interface PhaseConfig {
  icon: string;
  label: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
}

/**
 * Phase configurations with dark mode compatible colors.
 * Uses shade-50/950 for backgrounds, shade-700/300 for text,
 * and shade-200/800 for borders to support both light and dark themes.
 */
const PHASE_CONFIGS: Record<string, PhaseConfig> = {
  discovery: {
    icon: '🔍',
    label: 'Discovery Phase',
    bgColor: 'bg-blue-50 dark:bg-blue-950',
    textColor: 'text-blue-700 dark:text-blue-300',
    borderColor: 'border-blue-200 dark:border-blue-800',
  },
  planning: {
    icon: '📋',
    label: 'Planning Phase',
    bgColor: 'bg-purple-50 dark:bg-purple-950',
    textColor: 'text-purple-700 dark:text-purple-300',
    borderColor: 'border-purple-200 dark:border-purple-800',
  },
  development: {
    icon: '🔨',
    label: 'Development Phase',
    bgColor: 'bg-green-50 dark:bg-green-950',
    textColor: 'text-green-700 dark:text-green-300',
    borderColor: 'border-green-200 dark:border-green-800',
  },
  review: {
    icon: '✅',
    label: 'Review Phase',
    bgColor: 'bg-yellow-50 dark:bg-yellow-950',
    textColor: 'text-yellow-700 dark:text-yellow-300',
    borderColor: 'border-yellow-200 dark:border-yellow-800',
  },
  complete: {
    icon: '🎉',
    label: 'Complete',
    bgColor: 'bg-muted',
    textColor: 'text-muted-foreground',
    borderColor: 'border-border',
  },
  shipped: {
    icon: '🚀',
    label: 'Shipped',
    bgColor: 'bg-indigo-50 dark:bg-indigo-950',
    textColor: 'text-indigo-700 dark:text-indigo-300',
    borderColor: 'border-indigo-200 dark:border-indigo-800',
  },
};

const DEFAULT_PHASE_CONFIG: PhaseConfig = {
  icon: '❓',
  label: 'Unknown Phase',
  bgColor: 'bg-muted',
  textColor: 'text-muted-foreground',
  borderColor: 'border-border',
};

export default function PhaseProgress({
  phase,
  currentStep,
  totalSteps,
  nextAction,
}: PhaseProgressProps) {
  // Normalize phase to lowercase for lookup
  const normalizedPhase = phase?.toLowerCase() || '';

  // Get phase configuration or use default
  const config = PHASE_CONFIGS[normalizedPhase] || DEFAULT_PHASE_CONFIG;

  // Calculate progress percentage (avoid division by zero)
  const rawPercentage = totalSteps > 0 ? (currentStep / totalSteps) * 100 : 0;
  const percentage = Math.min(Math.max(Math.round(rawPercentage), 0), 100);

  return (
    <div
      data-testid="phase-progress"
      className={`rounded-lg p-4 border ${config.bgColor} ${config.textColor} ${config.borderColor}`}
    >
      {/* Phase Header */}
      <div className="flex items-center gap-2 mb-2">
        <span data-testid="phase-icon" className="text-2xl">
          {config.icon}
        </span>
        <span className="font-semibold text-lg">{config.label}</span>
      </div>

      {/* Step Counter */}
      <div data-testid="step-counter" className="text-sm mb-2">
        Step {currentStep} of {totalSteps}
      </div>

      {/* Progress Bar */}
      <div
        role="progressbar"
        aria-valuenow={percentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${config.label} Progress: ${percentage}%`}
        className="w-full bg-white/50 rounded-full h-2 mb-2 overflow-hidden"
      >
        <div
          className="h-full rounded-full bg-current opacity-60 transition-all duration-300"
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Next Action Hint */}
      {nextAction && nextAction.trim() && (
        <div data-testid="next-action-hint" className="text-sm mt-2 opacity-90">
          💡 Next: {nextAction}
        </div>
      )}
    </div>
  );
}
