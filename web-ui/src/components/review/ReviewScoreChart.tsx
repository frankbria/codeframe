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
 * Get score color based on value
 */
function getScoreColor(score: number): string {
  if (score >= 90) return 'bg-green-500';
  if (score >= 70) return 'bg-yellow-500';
  if (score >= 50) return 'bg-orange-500';
  return 'bg-red-500';
}

/**
 * Get status badge color
 */
function getStatusColor(status: string): string {
  switch (status) {
    case 'approved':
      return 'bg-green-100 text-green-800 border-green-300';
    case 'changes_requested':
      return 'bg-yellow-100 text-yellow-800 border-yellow-300';
    case 'rejected':
      return 'bg-red-100 text-red-800 border-red-300';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-300';
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
        <span className="font-medium text-gray-700">{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Weight: {weight}%</span>
          <span className="font-semibold text-gray-900">{score.toFixed(1)}</span>
        </div>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
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
    <div className="space-y-6">
      {/* Overall Score */}
      <div className="text-center pb-6 border-b">
        <div className="text-5xl font-bold mb-2">
          <span className={getScoreColor(report.overall_score).replace('bg-', 'text-')}>
            {report.overall_score.toFixed(1)}
          </span>
          <span className="text-2xl text-gray-400">/100</span>
        </div>
        <div className="text-sm text-gray-600 mb-3">Overall Code Quality</div>
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
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
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
      <div className="pt-4 border-t">
        <p className="text-sm text-gray-700 leading-relaxed">{report.summary}</p>
      </div>
    </div>
  );
}
