/**
 * ReviewFindingsList Component (T062)
 * Displays list of review findings with severity indicators
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

'use client';

import type { ReviewFinding, FindingSeverity } from '../../types/review';

interface ReviewFindingsListProps {
  findings: ReviewFinding[];
}

/**
 * Get severity badge color classes
 */
function getSeverityColor(severity: FindingSeverity): string {
  switch (severity) {
    case 'critical':
      return 'bg-red-100 text-red-800 border-red-300';
    case 'high':
      return 'bg-orange-100 text-orange-800 border-orange-300';
    case 'medium':
      return 'bg-yellow-100 text-yellow-800 border-yellow-300';
    case 'low':
      return 'bg-blue-100 text-blue-800 border-blue-300';
    case 'info':
      return 'bg-gray-100 text-gray-800 border-gray-300';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-300';
  }
}

/**
 * Get category icon
 */
function getCategoryIcon(category: string): string {
  switch (category) {
    case 'security':
      return '🔒';
    case 'complexity':
      return '🔄';
    case 'style':
      return '✨';
    case 'coverage':
      return '📊';
    case 'owasp':
      return '🛡️';
    default:
      return '📝';
  }
}

export default function ReviewFindingsList({ findings }: ReviewFindingsListProps) {
  if (findings.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        <div className="text-4xl mb-2">✅</div>
        <p className="text-sm">No findings - excellent code quality!</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {findings.map((finding, index) => (
        <div
          key={index}
          className="border rounded-lg p-4 hover:bg-gray-50 transition-colors"
        >
          {/* Header: Severity + Category */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">{getCategoryIcon(finding.category)}</span>
              <span
                className={`px-2 py-1 rounded-full text-xs font-medium border ${getSeverityColor(
                  finding.severity
                )}`}
              >
                {finding.severity.toUpperCase()}
              </span>
              <span className="text-sm font-medium text-gray-700 capitalize">
                {finding.category}
              </span>
            </div>
            <div className="text-xs text-gray-500">
              Line {finding.line_number}
            </div>
          </div>

          {/* File path */}
          <div className="text-sm text-gray-600 mb-2 font-mono">
            {finding.file_path}
          </div>

          {/* Message */}
          <div className="text-sm text-gray-800 mb-2">
            {finding.message}
          </div>

          {/* Suggestion (if available) */}
          {finding.suggestion && (
            <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded text-sm">
              <span className="font-medium text-blue-800">💡 Suggestion: </span>
              <span className="text-blue-700">{finding.suggestion}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
