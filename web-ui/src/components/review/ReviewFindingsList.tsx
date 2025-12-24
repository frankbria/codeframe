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
 * Get severity badge color classes (Nova palette)
 */
function getSeverityColor(severity: FindingSeverity): string {
  switch (severity) {
    case 'critical':
      return 'bg-destructive text-destructive-foreground border-destructive';
    case 'high':
      return 'bg-destructive/80 text-destructive-foreground border-destructive';
    case 'medium':
      return 'bg-muted text-foreground border-border';
    case 'low':
      return 'bg-secondary text-secondary-foreground border-border';
    case 'info':
      return 'bg-muted text-muted-foreground border-border';
    default:
      return 'bg-muted text-muted-foreground border-border';
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
      <div className="text-center py-8 text-muted-foreground">
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
          className="border border-border rounded-lg p-4 hover:bg-muted transition-colors bg-card"
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
              <span className="text-sm font-medium text-foreground capitalize">
                {finding.category}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              Line {finding.line_number}
            </div>
          </div>

          {/* File path */}
          <div className="text-sm text-muted-foreground mb-2 font-mono">
            {finding.file_path}
          </div>

          {/* Message */}
          <div className="text-sm text-foreground mb-2">
            {finding.message}
          </div>

          {/* Suggestion (if available) */}
          {finding.suggestion && (
            <div className="mt-2 p-2 bg-muted border border-border rounded text-sm">
              <span className="font-medium text-foreground">💡 Suggestion: </span>
              <span className="text-muted-foreground">{finding.suggestion}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
