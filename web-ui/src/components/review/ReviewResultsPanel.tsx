/**
 * ReviewResultsPanel Component (T064)
 * Main panel displaying review results with scores and findings
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

'use client';

import { useState, useEffect } from 'react';
import type { ReviewStatusResponse } from '../../types/review';
import { fetchReviewStatus } from '../../api/review';

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
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
        </div>
        <p className="text-center text-gray-500 mt-4">Loading review...</p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-center py-8">
          <div className="text-4xl mb-2">⚠️</div>
          <p className="text-red-600 font-medium">Error Loading Review</p>
          <p className="text-sm text-gray-500 mt-2">{error}</p>
        </div>
      </div>
    );
  }

  // No review exists
  if (!reviewStatus?.has_review) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-center py-8">
          <div className="text-4xl mb-2">📝</div>
          <p className="text-gray-600 font-medium">No Review Available</p>
          <p className="text-sm text-gray-500 mt-2">
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
    <div className="bg-white rounded-lg shadow">
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b">
        <div>
          <h2 className="text-xl font-semibold text-gray-800">Code Review Results</h2>
          <p className="text-sm text-gray-500 mt-1">Task #{taskId}</p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
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
            <span className={reviewStatus.overall_score! >= 70 ? 'text-green-500' : 'text-orange-500'}>
              {reviewStatus.overall_score}
            </span>
            <span className="text-2xl text-gray-400">/100</span>
          </div>

          <div className="mb-6">
            <span
              className={`px-4 py-2 rounded-full text-sm font-medium border ${
                reviewStatus.status === 'approved'
                  ? 'bg-green-100 text-green-800 border-green-300'
                  : reviewStatus.status === 'changes_requested'
                  ? 'bg-yellow-100 text-yellow-800 border-yellow-300'
                  : 'bg-red-100 text-red-800 border-red-300'
              }`}
            >
              {reviewStatus.status?.replace('_', ' ').toUpperCase()}
            </span>
          </div>

          <div className="text-sm text-gray-600">
            <p className="mb-2">
              <span className="font-medium">{reviewStatus.findings_count}</span> findings detected
            </p>
            <p className="text-xs text-gray-500 mt-4">
              Full review details coming soon...
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
