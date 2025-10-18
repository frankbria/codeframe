/**
 * ProgressBar Component (cf-17.2)
 * Displays a horizontal progress bar with color coding and optional percentage display
 */

'use client';

interface ProgressBarProps {
  percentage: number;
  label?: string;
  showPercentage?: boolean;
}

export default function ProgressBar({ percentage, label, showPercentage = false }: ProgressBarProps) {
  // Clamp percentage to 0-100 range
  const clampedPercentage = Math.max(0, Math.min(100, percentage));

  // Determine color based on percentage
  const getColorClass = (value: number): string => {
    if (value > 75) return 'bg-green-500';
    if (value >= 25) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const colorClass = getColorClass(clampedPercentage);
  const ariaLabel = label || 'Progress';

  return (
    <div className="w-full">
      {/* Label */}
      {label && (
        <div
          data-testid="progress-bar-label"
          className="text-sm font-medium text-gray-700 mb-1"
        >
          {label}
        </div>
      )}

      {/* Progress Bar Container */}
      <div
        data-testid="progress-bar-container"
        role="progressbar"
        aria-valuenow={clampedPercentage}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel}
        className="w-full bg-gray-200 rounded-full h-4 relative overflow-hidden"
      >
        {/* Filled Progress Bar */}
        <div
          data-testid="progress-bar-filled"
          className={`h-full rounded-full transition-all duration-300 ${colorClass}`}
          style={{ width: `${clampedPercentage}%` }}
        />

        {/* Percentage Text Overlay */}
        {showPercentage && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-xs font-semibold text-gray-800">
              {clampedPercentage}%
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
