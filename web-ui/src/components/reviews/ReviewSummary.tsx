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

import React, { useMemo, useState } from 'react';
import type { ReviewResult, Severity, ReviewCategory, CodeReview } from '../../types/reviews';
import { CATEGORY_ICONS, SEVERITY_COLORS } from '../../types/reviews';

interface ReviewSummaryProps {
  /** Review result data */
  reviewResult: ReviewResult | null;

  /** Loading state */
  loading?: boolean;

  /** Error message if fetch failed */
  error?: string | null;
}

/**
 * Individual Finding Card Component (Memoized for performance)
 * Addresses Issue #1 (Performance) and #2 (Accessibility)
 */
interface FindingCardProps {
  finding: CodeReview;
  index: number;
  isExpanded: boolean;
  onToggle: (id: number) => void;
}

const FindingCard = React.memo(({ finding, index, isExpanded, onToggle }: FindingCardProps) => {
  // Use ID if available, fallback to index to avoid collisions (Issue #3)
  const findingId = finding.id ?? index;

  // Defensive check for severity color (Issue #5) - Nova palette
  const severityColor = SEVERITY_COLORS[finding.severity as Severity] || 'bg-muted text-muted-foreground border-border';

  // Defensive check for category icon (Issue #5)
  const categoryIcon = CATEGORY_ICONS[finding.category as ReviewCategory] || '📄';

  // Keyboard event handler for accessibility (Issue #2)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle(findingId);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={isExpanded}
      aria-label={`${finding.severity} severity finding in ${finding.file_path}${finding.line_number ? ` line ${finding.line_number}` : ''}`}
      className={`finding-card border-2 rounded-lg p-4 cursor-pointer transition-all hover:shadow-md focus:ring-2 focus:ring-blue-500 focus:outline-none ${severityColor}`}
      onClick={() => onToggle(findingId)}
      onKeyDown={handleKeyDown}
      data-testid={`review-finding-${findingId}`}
    >
      {/* Finding Header */}
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <code className="text-sm font-mono bg-card px-2 py-1 rounded border border-border">
              {finding.file_path}
              {finding.line_number && `:${finding.line_number}`}
            </code>
          </div>
          <p className="text-sm font-medium text-foreground">{finding.message}</p>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <span className="text-lg" title={finding.category} aria-hidden="true">
            {categoryIcon}
          </span>
          <span
            className="text-xs font-semibold uppercase px-2 py-1 bg-card rounded border border-border"
            data-testid="severity-badge"
          >
            {finding.severity}
          </span>
        </div>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="finding-details mt-4 space-y-3" data-testid="finding-details">
          {/* Full Message (if needed) */}
          {finding.message && (
            <div className="bg-muted rounded p-3">
              <p className="text-xs font-semibold text-muted-foreground mb-1">Details:</p>
              <p className="text-sm text-foreground">{finding.message}</p>
            </div>
          )}

          {/* Recommendation */}
          {finding.recommendation && (
            <div
              className="bg-muted border border-border rounded p-3"
              data-testid="finding-recommendation"
            >
              <div className="flex items-start gap-2">
                <span className="text-foreground text-lg" aria-hidden="true">💡</span>
                <div>
                  <p className="text-xs font-semibold text-foreground mb-1">
                    Recommendation:
                  </p>
                  <p className="text-sm text-muted-foreground">{finding.recommendation}</p>
                </div>
              </div>
            </div>
          )}

          {/* Code Snippet */}
          {finding.code_snippet && (
            <div className="bg-accent text-accent-foreground rounded p-3 overflow-x-auto border border-border">
              <p className="text-xs font-semibold text-muted-foreground mb-2">Code:</p>
              <pre className="text-xs font-mono">{finding.code_snippet}</pre>
            </div>
          )}

          {/* File Details */}
          <div className="text-xs text-muted-foreground bg-muted rounded p-2">
            <span className="font-semibold">File:</span> {finding.file_path}
            {finding.line_number && (
              <>
                {' '}
                <span className="font-semibold">Line:</span> {finding.line_number}
              </>
            )}
            {' '}
            <span className="font-semibold">Category:</span>{' '}
            <span className="capitalize">{finding.category}</span>
          </div>
        </div>
      )}
    </div>
  );
});

FindingCard.displayName = 'FindingCard';

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

  // State for expand/collapse individual findings
  const [expandedFindings, setExpandedFindings] = useState<Set<number>>(new Set());

  // State for severity filter
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all');

  // Filter findings based on selected severity
  const filteredFindings = useMemo(() => {
    if (!reviewResult) return [];
    if (severityFilter === 'all') return reviewResult.findings;
    return reviewResult.findings.filter((finding) => finding.severity === severityFilter);
  }, [reviewResult, severityFilter]);

  // Toggle finding expansion
  const toggleFinding = (findingId: number) => {
    setExpandedFindings((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(findingId)) {
        newSet.delete(findingId);
      } else {
        newSet.add(findingId);
      }
      return newSet;
    });
  };

  // Loading state
  if (loading) {
    return (
      <div className="review-summary" data-testid="review-summary">
        <h3 className="text-lg font-semibold mb-4 text-foreground">Review Summary</h3>
        <div className="text-muted-foreground">Loading summary...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="review-summary" data-testid="review-summary">
        <h3 className="text-lg font-semibold mb-4 text-foreground">Review Summary</h3>
        <div className="text-destructive bg-destructive/10 p-4 rounded border border-destructive/30">
          <strong>Error:</strong> {error}
        </div>
      </div>
    );
  }

  // Empty state (no review data) - still render container with findings list placeholder
  if (!reviewResult) {
    return (
      <div className="review-summary" data-testid="review-summary">
        <h3 className="text-lg font-semibold mb-4 text-foreground">Review Summary</h3>
        <div className="text-muted-foreground bg-muted p-4 rounded mb-6">
          No review data available. Trigger a code review to see results.
        </div>
        {/* Always render review-findings-list container for test consistency */}
        <div className="review-findings-list" data-testid="review-findings-list">
          <div className="text-muted-foreground bg-muted p-4 rounded text-center">
            No review findings yet.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="review-summary" data-testid="review-summary">
      <h3 className="text-lg font-semibold mb-4 text-foreground">Review Summary</h3>

      {/* Blocking Status Banner */}
      {isBlocking && (
        <div
          className="blocking-banner bg-destructive/10 border-2 border-destructive text-destructive p-4 rounded-lg mb-4"
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
          className="success-banner bg-secondary/10 border-2 border-secondary text-secondary-foreground p-4 rounded-lg mb-4"
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
        <div className="bg-muted p-4 rounded-lg">
          <p className="text-sm text-muted-foreground">Total Findings</p>
          <p className="text-3xl font-bold text-foreground" data-testid="total-count">
            {reviewResult.total_count}
          </p>
        </div>
      </div>

      {/* Review Score Chart (placeholder) */}
      <div className="review-score-chart mb-6" data-testid="review-score-chart">
        <h4 className="text-md font-semibold mb-3 text-foreground">Score Overview</h4>
        {reviewResult.total_count === 0 ? (
          <div className="bg-muted p-4 rounded-lg text-center text-muted-foreground" data-testid="chart-empty">
            No findings to display
          </div>
        ) : (
          <div className="bg-muted p-4 rounded-lg" data-testid="chart-data">
            <div className="text-center text-muted-foreground">
              Chart placeholder - {reviewResult.total_count} issues across {Object.keys(reviewResult.severity_counts).length} severity levels
            </div>
          </div>
        )}
      </div>

      {/* Severity Breakdown */}
      <div className="severity-breakdown mb-6">
        <h4 className="text-md font-semibold mb-3 text-foreground">By Severity</h4>
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
                  data-testid={`severity-badge-${severity}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium capitalize text-foreground">
                      {severity}
                    </span>
                    <span className="text-sm font-semibold text-foreground">{count}</span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        severity === 'critical'
                          ? 'bg-destructive'
                          : severity === 'high'
                          ? 'bg-destructive/70'
                          : severity === 'medium'
                          ? 'bg-primary/60'
                          : severity === 'low'
                          ? 'bg-secondary'
                          : 'bg-muted-foreground'
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
      <div className="category-breakdown mb-6">
        <h4 className="text-md font-semibold mb-3 text-foreground">By Category</h4>
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
                className="category-card bg-muted border border-border p-3 rounded"
                data-testid={`category-${category}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{icon}</span>
                    <span className="text-xs font-medium capitalize text-foreground">
                      {category}
                    </span>
                  </div>
                  <span className="text-sm font-semibold text-foreground">{count}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Individual Findings Section */}
      <div className="individual-findings">
        {/* Severity Filter - only show if there are findings */}
        {reviewResult.findings.length > 0 && (
          <div className="mb-4">
            <label htmlFor="severity-filter" className="text-sm font-medium mr-2 text-foreground">
              Filter by severity:
            </label>
            <select
              id="severity-filter"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as Severity | 'all')}
              className="border border-border rounded px-3 py-1 text-sm bg-background text-foreground"
              data-testid="severity-filter"
            >
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
          </div>
        )}

        {/* Findings List - always rendered */}
        <div className="review-findings-list space-y-3" data-testid="review-findings-list">
          {reviewResult.findings.length === 0 ? (
            <div className="text-muted-foreground bg-muted p-4 rounded text-center" data-testid="no-findings">
              No review findings. All code reviews will appear here.
            </div>
          ) : filteredFindings.length === 0 ? (
            <div className="text-muted-foreground bg-muted p-4 rounded text-center" data-testid="no-findings">
              No findings match the selected filter.
            </div>
          ) : (
            filteredFindings.map((finding, index) => {
              const findingId = finding.id ?? index;
              const isExpanded = expandedFindings.has(findingId);

              return (
                <FindingCard
                  key={findingId}
                  finding={finding}
                  index={index}
                  isExpanded={isExpanded}
                  onToggle={toggleFinding}
                />
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

export default React.memo(ReviewSummary);
