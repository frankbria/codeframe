/**
 * ReviewResultsPanel Component (T064)
 * Main panel displaying review results with scores and findings
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

'use client';

import { useState, useEffect } from 'react';
import type { ReviewStatusResponse } from '../../types/review';
import { fetchReviewStatus } from '../../api/review';
import { Alert02Icon, FileEditIcon } from '@hugeicons/react';

interface ReviewResultsPanelProps {
  taskId: number;
  onClose?: () => void;
}

export default function ReviewResultsPanel({
  taskId,
  onClose,
}: ReviewResultsPanelProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewStatus, setReviewStatus] = useState<ReviewStatusResponse | null>(null);
  const [_activeTab, _setActiveTab] = useState<'scores' | 'findings'>('scores');

  // Fetch review status on mount
  useEffect(() => {
    async function loadReviewStatus() {
      try {
        setLoading(true);
        setError(null);
        const status = await fetchReviewStatus(taskId);
        setReviewStatus(status);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load review');
      } finally {
        setLoading(false);
      }
    }

    loadReviewStatus();
  }, [taskId]);

  // Loading state
  if (loading) {
    return (
      <div className="bg-card rounded-lg shadow p-6 border border-border">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
        </div>
        <p className="text-center text-muted-foreground mt-4">Loading review...</p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-card rounded-lg shadow p-6 border border-border">
        <div className="text-center py-8">
          <div className="mb-2 flex justify-center">
            <Alert02Icon className="h-10 w-10 text-destructive" aria-hidden="true" />
          </div>
          <p className="text-destructive font-medium">Error Loading Review</p>
          <p className="text-sm text-muted-foreground mt-2">{error}</p>
        </div>
      </div>
    );
  }

  // No review exists
  if (!reviewStatus?.has_review) {
    return (
      <div className="bg-card rounded-lg shadow p-6 border border-border">
        <div className="text-center py-8">
          <div className="mb-2 flex justify-center">
            <FileEditIcon className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
          </div>
          <p className="text-foreground font-medium">No Review Available</p>
          <p className="text-sm text-muted-foreground mt-2">
            This task has not been reviewed yet.
          </p>
        </div>
      </div>
    );
  }

  // For now, we only have status info from the API
  // In a real implementation, we'd fetch the full report
  // For this MVP, we'll show the status information we have
  return (
    <div className="bg-card rounded-lg shadow border border-border">
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-border">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Code Review Results</h2>
          <p className="text-sm text-muted-foreground mt-1">Task #{taskId}</p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Close"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Content - Simplified for MVP since we only have summary data */}
      <div className="p-6">
        <div className="text-center py-8">
          <div className="text-6xl font-bold mb-4">
            <span className={reviewStatus.overall_score! >= 70 ? 'text-secondary' : 'text-destructive'}>
              {reviewStatus.overall_score}
            </span>
            <span className="text-2xl text-muted-foreground">/100</span>
          </div>

          <div className="mb-6">
            <span
              className={`px-4 py-2 rounded-full text-sm font-medium border ${
                reviewStatus.status === 'approved'
                  ? 'bg-secondary text-secondary-foreground border-border'
                  : reviewStatus.status === 'changes_requested'
                  ? 'bg-muted text-foreground border-border'
                  : 'bg-destructive text-destructive-foreground border-destructive'
              }`}
            >
              {reviewStatus.status?.replace('_', ' ').toUpperCase()}
            </span>
          </div>

          <div className="text-sm text-muted-foreground">
            <p className="mb-2">
              <span className="font-medium text-foreground">{reviewStatus.findings_count}</span> findings detected
            </p>
            <p className="text-xs text-muted-foreground mt-4">
              Full review details coming soon...
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
