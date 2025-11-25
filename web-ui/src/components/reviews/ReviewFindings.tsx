/**
 * ReviewFindings Component - Display code review findings (Sprint 10 Phase 2)
 *
 * Features:
 * - Display list of code review findings grouped by severity
 * - Show file path, line number, message, recommendation
 * - Color coding by severity
 * - Filter by severity
 * - Sort by severity or file path
 *
 * Tasks: T036
 */

import React, { useState, useMemo } from 'react';
import type {
  CodeReview,
  Severity,

} from '../../types/reviews';
import {
  SEVERITY_COLORS,
  CATEGORY_ICONS,
} from '../../types/reviews';

interface ReviewFindingsProps {
  /** List of review findings to display */
  findings: CodeReview[];

  /** Loading state */
  loading?: boolean;

  /** Error message if fetch failed */
  error?: string | null;

  /** Optional callback when a finding is clicked */
  onFindingClick?: (finding: CodeReview) => void;
}

type SortField = 'severity' | 'file_path';
type SortDirection = 'asc' | 'desc';

/**
 * Severity ordering for sorting (higher severity = higher priority)
 */
const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

/**
 * Display code review findings with filtering and sorting
 */
export function ReviewFindings({
  findings,
  loading = false,
  error = null,
  onFindingClick,
}: ReviewFindingsProps): JSX.Element {
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all');
  const [sortField, setSortField] = useState<SortField>('severity');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Filter and sort findings
  const processedFindings = useMemo(() => {
    let filtered = findings;

    // Apply severity filter
    if (severityFilter !== 'all') {
      filtered = filtered.filter((f) => f.severity === severityFilter);
    }

    // Sort findings
    const sorted = [...filtered].sort((a, b) => {
      let comparison = 0;

      if (sortField === 'severity') {
        comparison = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
      } else if (sortField === 'file_path') {
        comparison = a.file_path.localeCompare(b.file_path);
      }

      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return sorted;
  }, [findings, severityFilter, sortField, sortDirection]);

  // Group findings by severity for display
  const groupedFindings = useMemo(() => {
    const groups: Record<Severity, CodeReview[]> = {
      critical: [],
      high: [],
      medium: [],
      low: [],
      info: [],
    };

    processedFindings.forEach((finding) => {
      groups[finding.severity].push(finding);
    });

    return groups;
  }, [processedFindings]);

  // Toggle sort direction or change sort field
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="review-findings" data-testid="review-findings">
        <h3 className="text-lg font-semibold mb-4">Code Review Findings</h3>
        <div className="text-gray-500">Loading findings...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="review-findings" data-testid="review-findings">
        <h3 className="text-lg font-semibold mb-4">Code Review Findings</h3>
        <div className="text-red-600 bg-red-50 p-4 rounded border border-red-200">
          <strong>Error:</strong> {error}
        </div>
      </div>
    );
  }

  // Empty state
  if (findings.length === 0) {
    return (
      <div className="review-findings" data-testid="review-findings">
        <h3 className="text-lg font-semibold mb-4">Code Review Findings</h3>
        <div className="text-gray-500 bg-gray-50 p-8 rounded text-center">
          No review findings. Code looks good! ✅
        </div>
      </div>
    );
  }

  return (
    <div className="review-findings" data-testid="review-findings">
      <h3 className="text-lg font-semibold mb-4">
        Code Review Findings ({processedFindings.length})
      </h3>

      {/* Filters and Sort Controls */}
      <div className="controls mb-4 flex gap-4 items-center">
        {/* Severity Filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="severity-filter" className="text-sm font-medium">
            Filter by severity:
          </label>
          <select
            id="severity-filter"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as Severity | 'all')}
            className="border rounded px-2 py-1 text-sm"
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

        {/* Sort Controls */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Sort by:</span>
          <button
            onClick={() => handleSort('severity')}
            className={`px-3 py-1 text-sm rounded ${
              sortField === 'severity'
                ? 'bg-blue-500 text-white'
                : 'bg-gray-200 text-gray-700'
            }`}
            data-testid="sort-severity"
          >
            Severity {sortField === 'severity' && (sortDirection === 'asc' ? '↑' : '↓')}
          </button>
          <button
            onClick={() => handleSort('file_path')}
            className={`px-3 py-1 text-sm rounded ${
              sortField === 'file_path'
                ? 'bg-blue-500 text-white'
                : 'bg-gray-200 text-gray-700'
            }`}
            data-testid="sort-file-path"
          >
            File Path {sortField === 'file_path' && (sortDirection === 'asc' ? '↑' : '↓')}
          </button>
        </div>
      </div>

      {/* Findings List */}
      <div className="findings-list space-y-6">
        {(['critical', 'high', 'medium', 'low', 'info'] as Severity[]).map((severity) => {
          const severityFindings = groupedFindings[severity];
          if (severityFindings.length === 0) return null;

          return (
            <div key={severity} className="severity-group">
              <h4 className="text-md font-semibold mb-2 capitalize">
                {severity} ({severityFindings.length})
              </h4>
              <div className="space-y-3">
                {severityFindings.map((finding) => (
                  <div
                    key={finding.id || `${finding.file_path}-${finding.line_number}`}
                    className={`finding-card border rounded-lg p-4 cursor-pointer hover:shadow-md transition-shadow ${
                      SEVERITY_COLORS[finding.severity]
                    }`}
                    onClick={() => onFindingClick?.(finding)}
                    data-testid={`finding-${finding.severity}`}
                  >
                    {/* Header: File path and line number */}
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <code className="text-sm font-mono bg-white bg-opacity-50 px-2 py-1 rounded">
                          {finding.file_path}
                          {finding.line_number && `:${finding.line_number}`}
                        </code>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <span className="text-lg" title={finding.category}>
                          {CATEGORY_ICONS[finding.category]}
                        </span>
                        <span className="text-xs font-semibold uppercase px-2 py-1 bg-white bg-opacity-50 rounded">
                          {finding.severity}
                        </span>
                      </div>
                    </div>

                    {/* Message */}
                    <div className="mb-2">
                      <p className="text-sm">{finding.message}</p>
                    </div>

                    {/* Recommendation */}
                    {finding.recommendation && (
                      <div className="mb-2 bg-white bg-opacity-50 rounded p-2">
                        <p className="text-xs font-semibold mb-1">Recommendation:</p>
                        <p className="text-sm">{finding.recommendation}</p>
                      </div>
                    )}

                    {/* Code snippet */}
                    {finding.code_snippet && (
                      <div className="bg-gray-900 text-gray-100 rounded p-2 overflow-x-auto">
                        <pre className="text-xs font-mono">{finding.code_snippet}</pre>
                      </div>
                    )}

                    {/* Category badge */}
                    <div className="mt-2">
                      <span className="text-xs text-gray-600 capitalize">
                        {finding.category}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* No findings after filtering */}
      {processedFindings.length === 0 && findings.length > 0 && (
        <div className="text-gray-500 bg-gray-50 p-4 rounded text-center">
          No findings match the selected filter.
        </div>
      )}
    </div>
  );
}

export default ReviewFindings;
