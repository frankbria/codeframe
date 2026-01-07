/**
 * PhaseProgress Component
 * Visualizes the current project phase with icons, step counters, and progress bars
 */

'use client';

interface PhaseProgressProps {
  phase: string;
  currentStep: number;
  totalSteps: number;
  nextAction?: string;
}

interface PhaseConfig {
  icon: string;
  label: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
}

const PHASE_CONFIGS: Record<string, PhaseConfig> = {
  discovery: {
    icon: '🔍',
    label: 'Discovery Phase',
    bgColor: 'bg-blue-100',
    textColor: 'text-blue-800',
    borderColor: 'border-blue-300',
  },
  planning: {
    icon: '📋',
    label: 'Planning Phase',
    bgColor: 'bg-purple-100',
    textColor: 'text-purple-800',
    borderColor: 'border-purple-300',
  },
  development: {
    icon: '🔨',
    label: 'Development Phase',
    bgColor: 'bg-green-100',
    textColor: 'text-green-800',
    borderColor: 'border-green-300',
  },
  review: {
    icon: '✅',
    label: 'Review Phase',
    bgColor: 'bg-yellow-100',
    textColor: 'text-yellow-800',
    borderColor: 'border-yellow-300',
  },
  complete: {
    icon: '🎉',
    label: 'Complete',
    bgColor: 'bg-gray-100',
    textColor: 'text-gray-800',
    borderColor: 'border-gray-300',
  },
  shipped: {
    icon: '🚀',
    label: 'Shipped',
    bgColor: 'bg-indigo-100',
    textColor: 'text-indigo-800',
    borderColor: 'border-indigo-300',
  },
};

const DEFAULT_PHASE_CONFIG: PhaseConfig = {
  icon: '❓',
  label: 'Unknown Phase',
  bgColor: 'bg-gray-100',
  textColor: 'text-gray-800',
  borderColor: 'border-gray-300',
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
