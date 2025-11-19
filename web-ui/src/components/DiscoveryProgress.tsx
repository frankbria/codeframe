/**
 * DiscoveryProgress Component (cf-17.2)
 * Displays discovery phase progress with auto-refresh functionality
 */

'use client';

import { useEffect, useState, memo } from 'react';
import { projectsApi } from '@/lib/api';
import type { DiscoveryProgressResponse } from '@/types/api';
import ProgressBar from './ProgressBar';
import PhaseIndicator from './PhaseIndicator';

interface DiscoveryProgressProps {
  projectId: number;
}

const DiscoveryProgress = memo(function DiscoveryProgress({ projectId }: DiscoveryProgressProps) {
  const [data, setData] = useState<DiscoveryProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Feature: 012-discovery-answer-ui - Answer submission state (T014)
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch discovery progress
  const fetchProgress = async () => {
    try {
      const response = await projectsApi.getDiscoveryProgress(projectId);
      setData(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load discovery progress');
      console.error('Error fetching discovery progress:', err);
    } finally {
      setLoading(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchProgress();
  }, [projectId]);

  // Auto-refresh only during discovery
  useEffect(() => {
    if (!data) return;

    const isDiscovering = data.discovery?.state === 'discovering';
    if (!isDiscovering) return;

    const intervalId = setInterval(() => {
      fetchProgress();
    }, 10000); // 10 seconds

    return () => clearInterval(intervalId);
  }, [data]);

  // Loading state
  if (loading) {
    return (
      <div className="w-full bg-white rounded-lg shadow p-6" role="region" aria-label="Discovery Progress">
        <div className="text-center text-gray-500">Loading...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="w-full bg-white rounded-lg shadow p-6" role="region" aria-label="Discovery Progress">
        <div className="text-center text-red-600">{error}</div>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const { phase, discovery } = data;
  const isDiscovering = discovery?.state === 'discovering';
  const isCompleted = discovery?.state === 'completed';
  const isIdle = discovery?.state === 'idle' || !discovery;

  return (
    <div className="w-full bg-white rounded-lg shadow p-6 mb-6" role="region" aria-label="Discovery Progress">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Discovery Progress</h2>
        <PhaseIndicator phase={phase} />
      </div>

      <div className="space-y-4">
        {/* Discovering State */}
        {isDiscovering && discovery && (
          <>
            <ProgressBar
              percentage={discovery.progress_percentage}
              label="Question Progress"
              showPercentage={true}
            />

            <div className="text-sm text-gray-600">
              Answered: {discovery.answered_count} / {discovery.total_required}
            </div>

            {discovery.current_question && (
              <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
                <div className="text-xs font-medium text-blue-800 uppercase mb-1">
                  Current Question ({discovery.current_question.category})
                </div>
                <div className="text-sm text-gray-900">
                  {discovery.current_question.question}
                </div>
              </div>
            )}

            {/* Feature: 012-discovery-answer-ui - Answer Input (T015, T016) */}
            {discovery.current_question && (
              <div className="mt-4">
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Type your answer here... (Ctrl+Enter to submit)"
                  rows={6}
                  maxLength={5000}
                  disabled={isSubmitting}
                  className={`w-full resize-none rounded-lg border px-4 py-3 focus:ring-2 focus:ring-blue-500 focus:outline-none ${
                    submissionError ? 'border-red-500' : 'border-gray-300'
                  } ${isSubmitting ? 'bg-gray-100' : 'bg-white'}`}
                />
              </div>
            )}
          </>
        )}

        {/* Completed State */}
        {isCompleted && (
          <div className="flex items-center gap-2 p-4 bg-green-50 rounded-lg border border-green-200">
            <span className="text-green-600 text-lg">✓</span>
            <span className="text-sm font-medium text-green-800">
              Discovery Complete
            </span>
          </div>
        )}

        {/* Idle/Not Started State */}
        {isIdle && (
          <div className="text-sm text-gray-500 italic">
            Discovery not started
          </div>
        )}
      </div>
    </div>
  );
});

DiscoveryProgress.displayName = 'DiscoveryProgress';

export default DiscoveryProgress;
