/**
 * ReviewFindingsList Component (T062)
 * Displays list of review findings with severity indicators
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

'use client';

import type { ReviewFinding, FindingSeverity } from '../../types/review';
import {
  LockIcon,
  RepeatIcon,
  SparklesIcon,
  ChartBarLineIcon,
  KnightShieldIcon,
  FileEditIcon,
  CheckmarkCircle01Icon,
  Idea01Icon,
} from '@hugeicons/react';

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
 * Get category icon component
 */
function getCategoryIcon(category: string): JSX.Element {
  const iconProps = { className: 'h-5 w-5', 'aria-hidden': true as const };
  switch (category) {
    case 'security':
      return <LockIcon {...iconProps} />;
    case 'complexity':
      return <RepeatIcon {...iconProps} />;
    case 'style':
      return <SparklesIcon {...iconProps} />;
    case 'coverage':
      return <ChartBarLineIcon {...iconProps} />;
    case 'owasp':
      return <KnightShieldIcon {...iconProps} />;
    default:
      return <FileEditIcon {...iconProps} />;
  }
}

export default function ReviewFindingsList({ findings }: ReviewFindingsListProps) {
  if (findings.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <div className="mb-2 flex justify-center">
          <CheckmarkCircle01Icon className="h-10 w-10 text-secondary" aria-hidden="true" />
        </div>
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
            <div className="mt-2 p-2 bg-muted border border-border rounded text-sm flex items-start gap-2">
              <Idea01Icon className="h-4 w-4 text-foreground flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <span className="font-medium text-foreground">Suggestion: </span>
                <span className="text-muted-foreground">{finding.suggestion}</span>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
