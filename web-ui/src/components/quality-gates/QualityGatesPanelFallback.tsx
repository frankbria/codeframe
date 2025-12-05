/**
 * QualityGatesPanelFallback Component
 *
 * Error fallback UI for the Quality Gates Panel with retry and dismiss functionality.
 * Designed for use with ErrorBoundary to provide graceful degradation without affecting
 * other Dashboard panels.
 */

'use client';

import React from 'react';

/**
 * Props for QualityGatesPanelFallback component
 */
interface QualityGatesPanelFallbackProps {
  /** The error that was caught (optional) */
  error?: Error;
  /** Callback to retry loading the panel (required) */
  onRetry: () => void;
  /** Optional callback to dismiss the error panel */
  onDismiss?: () => void;
}

/**
 * QualityGatesPanelFallback Component
 *
 * Displays a user-friendly error message when the Quality Gates Panel crashes.
 * Provides retry and dismiss options without requiring a full page reload.
 *
 * @example
 * ```tsx
 * <ErrorBoundary
 *   fallback={
 *     <QualityGatesPanelFallback
 *       onRetry={handleRetry}
 *       onDismiss={handleDismiss}
 *     />
 *   }
 * >
 *   <QualityGatesPanel projectId={1} tasks={tasks} />
 * </ErrorBoundary>
 * ```
 */
export default function QualityGatesPanelFallback({
  error,
  onRetry,
  onDismiss,
}: QualityGatesPanelFallbackProps) {
  return (
    <div
      className="p-6 bg-red-50 rounded-lg border border-red-200 shadow"
      role="alert"
      data-testid="quality-gates-panel-fallback"
    >
      {/* Header with icon and title */}
      <div className="flex items-center gap-3 mb-4">
        <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
          <span className="text-2xl" aria-hidden="true">⚠️</span>
        </div>
        <h3 className="text-lg font-semibold text-red-900">
          Quality Gates Panel Unavailable
        </h3>
      </div>

      {/* Error description */}
      <p className="text-sm text-red-800 mb-4">
        An error occurred while loading the Quality Gates panel. You can retry loading
        the panel or continue using the dashboard without it. Other panels will continue
        to work normally.
      </p>

      {/* Error message */}
      <div className="mb-4 p-3 bg-red-100 rounded-md border border-red-300">
        <p className="text-sm text-red-900 font-medium">
          Error: {error?.message || 'Unknown error'}
        </p>
      </div>

      {/* Development-only error details */}
      {process.env.NODE_ENV === 'development' && error?.stack && (
        <details className="mb-4">
          <summary className="cursor-pointer text-sm font-medium text-red-900 mb-2 hover:text-red-700">
            Error details (development only)
          </summary>
          <pre className="text-xs bg-red-100 p-3 rounded border border-red-300 overflow-auto max-h-48">
            {error.stack}
          </pre>
        </details>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        {/* Retry button (primary action) */}
        <button
          onClick={onRetry}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium text-sm"
          aria-label="Retry loading Quality Gates panel"
        >
          🔄 Retry
        </button>

        {/* Dismiss button (secondary action, only if onDismiss provided) */}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors font-medium text-sm"
            aria-label="Continue without Quality Gates panel"
          >
            Continue Without Quality Gates
          </button>
        )}
      </div>
    </div>
  );
}
