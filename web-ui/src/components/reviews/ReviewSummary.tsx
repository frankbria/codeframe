/**
 * ReviewSummary Component - Display review statistics (Sprint 10 Phase 2)
 *
 * Features:
 * - Display summary statistics (total findings, breakdown by severity/category)
 * - Show blocking status (if critical/high findings exist)
 * - Progress indicators
 *
 * Tasks: T037
 */

import React, { useMemo } from 'react';
import type { ReviewResult, Severity, ReviewCategory } from '../../types/reviews';
import { CATEGORY_ICONS } from '../../types/reviews';

interface ReviewSummaryProps {
  /** Review result data */
  reviewResult: ReviewResult | null;

  /** Loading state */
  loading?: boolean;

  /** Error message if fetch failed */
  error?: string | null;
}

/**
 * Display review summary statistics and blocking status
 */
export function ReviewSummary({
  reviewResult,
  loading = false,
  error = null,
}: ReviewSummaryProps): JSX.Element {
  // Calculate blocking status
  const isBlocking = useMemo(() => {
    if (!reviewResult) return false;
    return reviewResult.has_blocking_findings;
  }, [reviewResult]);

  // Calculate total critical + high findings
  const blockingCount = useMemo(() => {
    if (!reviewResult) return 0;
    return (
      reviewResult.severity_counts.critical + reviewResult.severity_counts.high
    );
  }, [reviewResult]);

  // Loading state
  if (loading) {
    return (
      <div className="review-summary" data-testid="review-summary">
        <h3 className="text-lg font-semibold mb-4">Review Summary</h3>
        <div className="text-gray-500">Loading summary...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="review-summary" data-testid="review-summary">
        <h3 className="text-lg font-semibold mb-4">Review Summary</h3>
        <div className="text-red-600 bg-red-50 p-4 rounded border border-red-200">
          <strong>Error:</strong> {error}
        </div>
      </div>
    );
  }

  // Empty state (no review data)
  if (!reviewResult) {
    return (
      <div className="review-summary" data-testid="review-summary">
        <h3 className="text-lg font-semibold mb-4">Review Summary</h3>
        <div className="text-gray-500 bg-gray-50 p-4 rounded">
          No review data available. Trigger a code review to see results.
        </div>
      </div>
    );
  }

  return (
    <div className="review-summary" data-testid="review-summary">
      <h3 className="text-lg font-semibold mb-4">Review Summary</h3>

      {/* Blocking Status Banner */}
      {isBlocking && (
        <div
          className="blocking-banner bg-red-100 border-2 border-red-500 text-red-800 p-4 rounded-lg mb-4"
          data-testid="blocking-banner"
        >
          <div className="flex items-center gap-2">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="font-semibold">Review Blocked</p>
              <p className="text-sm">
                Found {blockingCount} critical/high severity finding
                {blockingCount !== 1 ? 's' : ''} that must be addressed before
                proceeding.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Non-blocking Success Banner */}
      {!isBlocking && reviewResult.total_count === 0 && (
        <div
          className="success-banner bg-green-100 border-2 border-green-500 text-green-800 p-4 rounded-lg mb-4"
          data-testid="success-banner"
        >
          <div className="flex items-center gap-2">
            <span className="text-2xl">✅</span>
            <div>
              <p className="font-semibold">Review Passed</p>
              <p className="text-sm">No issues found. Code looks great!</p>
            </div>
          </div>
        </div>
      )}

      {/* Total Findings */}
      <div className="total-findings mb-6">
        <div className="bg-gray-100 p-4 rounded-lg">
          <p className="text-sm text-gray-600">Total Findings</p>
          <p className="text-3xl font-bold" data-testid="total-count">
            {reviewResult.total_count}
          </p>
        </div>
      </div>

      {/* Review Score Chart (placeholder) */}
      <div className="review-score-chart mb-6" data-testid="review-score-chart">
        <h4 className="text-md font-semibold mb-3">Score Overview</h4>
        {reviewResult.total_count === 0 ? (
          <div className="bg-gray-50 p-4 rounded-lg text-center text-gray-500" data-testid="chart-empty">
            No findings to display
          </div>
        ) : (
          <div className="bg-gray-50 p-4 rounded-lg" data-testid="chart-data">
            <div className="text-center text-gray-600">
              Chart placeholder - {reviewResult.total_count} issues across {Object.keys(reviewResult.severity_counts).length} severity levels
            </div>
          </div>
        )}
      </div>

      {/* Review Findings List (severity breakdown serves as findings list) */}
      <div className="severity-breakdown mb-6" data-testid="review-findings-list">
        <h4 className="text-md font-semibold mb-3">By Severity</h4>
        <div className="space-y-2">
          {(['critical', 'high', 'medium', 'low', 'info'] as Severity[]).map(
            (severity) => {
              const count = reviewResult.severity_counts[severity];
              const percentage =
                reviewResult.total_count > 0
                  ? (count / reviewResult.total_count) * 100
                  : 0;

              return (
                <div
                  key={severity}
                  className="severity-bar"
                  data-testid={`severity-${severity}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium capitalize">
                      {severity}
                    </span>
                    <span className="text-sm font-semibold">{count}</span>
                  </div>
                  <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        severity === 'critical'
                          ? 'bg-red-500'
                          : severity === 'high'
                          ? 'bg-orange-500'
                          : severity === 'medium'
                          ? 'bg-yellow-500'
                          : severity === 'low'
                          ? 'bg-blue-500'
                          : 'bg-gray-500'
                      }`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              );
            }
          )}
        </div>
      </div>

      {/* Category Breakdown */}
      <div className="category-breakdown">
        <h4 className="text-md font-semibold mb-3">By Category</h4>
        <div className="grid grid-cols-2 gap-2">
          {(
            [
              'security',
              'performance',
              'quality',
              'maintainability',
              'style',
            ] as ReviewCategory[]
          ).map((category) => {
            const count = reviewResult.category_counts[category];
            const icon = CATEGORY_ICONS[category];

            return (
              <div
                key={category}
                className="category-card bg-gray-50 border border-gray-200 p-3 rounded"
                data-testid={`category-${category}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{icon}</span>
                    <span className="text-xs font-medium capitalize">
                      {category}
                    </span>
                  </div>
                  <span className="text-sm font-semibold">{count}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default React.memo(ReviewSummary);
