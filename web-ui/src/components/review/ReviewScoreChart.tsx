/**
 * ReviewScoreChart Component (T063)
 * Displays visual breakdown of review scores
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

'use client';

import type { ReviewReport } from '../../types/review';

interface ReviewScoreChartProps {
  report: ReviewReport;
}

/**
 * Get score color based on value (Nova palette)
 */
function getScoreColor(score: number): string {
  if (score >= 90) return 'bg-secondary';
  if (score >= 70) return 'bg-primary/60';
  if (score >= 50) return 'bg-destructive/60';
  return 'bg-destructive';
}

/**
 * Get status badge color (Nova palette)
 */
function getStatusColor(status: string): string {
  switch (status) {
    case 'approved':
      return 'bg-secondary text-secondary-foreground border-border';
    case 'changes_requested':
      return 'bg-muted text-foreground border-border';
    case 'rejected':
      return 'bg-destructive text-destructive-foreground border-destructive';
    default:
      return 'bg-muted text-muted-foreground border-border';
  }
}

/**
 * ScoreBar subcomponent
 */
function ScoreBar({
  label,
  score,
  weight,
}: {
  label: string;
  score: number;
  weight: number;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-foreground">{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Weight: {weight}%</span>
          <span className="font-semibold text-foreground">{score.toFixed(1)}</span>
        </div>
      </div>
      <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${getScoreColor(
            score
          )}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

export default function ReviewScoreChart({ report }: ReviewScoreChartProps) {
  return (
    <div className="space-y-6 bg-card p-6 rounded-lg border border-border">
      {/* Overall Score */}
      <div className="text-center pb-6 border-b border-border">
        <div className="text-5xl font-bold mb-2">
          <span className={getScoreColor(report.overall_score).replace('bg-', 'text-')}>
            {report.overall_score.toFixed(1)}
          </span>
          <span className="text-2xl text-muted-foreground">/100</span>
        </div>
        <div className="text-sm text-muted-foreground mb-3">Overall Code Quality</div>
        <div className="flex items-center justify-center gap-2">
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium border ${getStatusColor(
              report.status
            )}`}
          >
            {report.status.replace('_', ' ').toUpperCase()}
          </span>
        </div>
      </div>

      {/* Score Breakdown */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-foreground uppercase tracking-wide">
          Score Breakdown
        </h3>

        <ScoreBar label="Security" score={report.security_score} weight={40} />
        <ScoreBar label="Complexity" score={report.complexity_score} weight={30} />
        <ScoreBar label="Style" score={report.style_score} weight={20} />
        <ScoreBar
          label="Coverage"
          score={
            // Coverage score not in ReviewReport, use placeholder
            80
          }
          weight={10}
        />
      </div>

      {/* Summary */}
      <div className="pt-4 border-t border-border">
        <p className="text-sm text-foreground leading-relaxed">{report.summary}</p>
      </div>
    </div>
  );
}
