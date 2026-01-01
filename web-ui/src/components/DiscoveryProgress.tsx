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

  // Feature: 012-discovery-answer-ui - Submit Answer (T038-T040)
  const submitAnswer = async () => {
    // Guard: Prevent duplicate concurrent submissions
    if (isSubmitting) {
      return;
    }

    // Client-side validation
    const trimmedAnswer = answer.trim();
    if (!trimmedAnswer || trimmedAnswer.length > 5000) {
      setSubmissionError('Answer must be between 1 and 5000 characters');
      return;
    }

    // Start submission
    setIsSubmitting(true);
    setSubmissionError(null);
    setSuccessMessage(null);

    try {
      // T038: POST request to backend
      const response = await fetch(`/api/projects/${projectId}/discovery/answer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ answer: trimmedAnswer }),
      });

      // T040: Error handling
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `Server error: ${response.status}`);
      }

      // T039: Parse response
      const _data = await response.json();

      // Success - show message and refresh
      setSuccessMessage('Answer submitted! Loading next question...');
      setAnswer(''); // Clear textarea
      setSubmissionError(null);

      // Refresh discovery state after 1 second
      setTimeout(() => {
        fetchProgress();
        setSuccessMessage(null);
      }, 1000);

    } catch (error) {
      // T040: Handle network and API errors
      console.error('Failed to submit answer:', error);
      if (error instanceof Error) {
        setSubmissionError(error.message);
      } else {
        setSubmissionError('Failed to submit answer. Please check your connection.');
      }
      // Keep answer in textarea for retry
    } finally {
      setIsSubmitting(false);
    }
  };

  // Feature: 012-discovery-answer-ui - Keyboard Shortcut (T049)
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Check for Ctrl+Enter
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault(); // Prevent default Enter behavior
      submitAnswer();
    }
  };

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // Loading state
  if (loading) {
    return (
      <div className="w-full bg-card rounded-lg shadow p-6" role="region" aria-label="Discovery Progress">
        <div className="text-center text-muted-foreground">Loading...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="w-full bg-card rounded-lg shadow p-6" role="region" aria-label="Discovery Progress">
        <div className="text-center text-destructive">{error}</div>
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
    <div className="w-full bg-card rounded-lg shadow p-6 mb-6" role="region" aria-label="Discovery Progress">
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

            <div className="text-sm text-muted-foreground">
              Answered: {discovery.answered_count} / {discovery.total_required}
            </div>

            {discovery.current_question && (
              <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary" data-testid="discovery-question">
                <div className="text-xs font-medium text-primary uppercase mb-1">
                  Current Question ({discovery.current_question.category})
                </div>
                <div className="text-sm text-foreground">
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
                  onKeyDown={handleKeyPress}
                  data-testid="discovery-answer-input"
                  placeholder="Type your answer here... (Ctrl+Enter to submit)"
                  rows={6}
                  maxLength={5000}
                  disabled={isSubmitting}
                  aria-label="Discovery question answer"
                  aria-describedby={submissionError ? 'answer-error' : undefined}
                  aria-invalid={submissionError ? 'true' : 'false'}
                  className={`w-full resize-none rounded-lg border px-4 py-3 focus:ring-2 focus:ring-primary focus:outline-none ${
                    submissionError ? 'border-destructive' : 'border-input'
                  } ${isSubmitting ? 'bg-muted' : 'bg-card'}`}
                />

                {/* Feature: 012-discovery-answer-ui - Character Counter (T020, T021) */}
                <div className="mt-2 flex items-center justify-between">
                  <span className={`text-sm ${answer.length > 4500 ? 'text-destructive' : 'text-muted-foreground'}`}>
                    {answer.length} / 5000 characters
                  </span>

                  {/* Feature: 012-discovery-answer-ui - Submit Button (T026, T027, T028) */}
                  <button
                    type="button"
                    onClick={submitAnswer}
                    disabled={isSubmitting || !answer.trim()}
                    data-testid="submit-answer-button"
                    className={`py-2 px-6 rounded-lg font-semibold transition-colors ${
                      isSubmitting || !answer.trim()
                        ? 'bg-muted cursor-not-allowed text-muted-foreground'
                        : 'bg-primary hover:bg-primary/90 text-primary-foreground'
                    }`}
                  >
                    {isSubmitting ? 'Submitting...' : 'Submit Answer'}
                  </button>
                </div>

                {/* Feature: 012-discovery-answer-ui - Success Message (US6, T091) */}
                {successMessage && (
                  <div
                    role="status"
                    aria-live="polite"
                    className="mt-2 p-3 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm"
                  >
                    {successMessage}
                  </div>
                )}

                {/* Feature: 012-discovery-answer-ui - Error Message (US7, T091) */}
                {submissionError && (
                  <div
                    id="answer-error"
                    role="alert"
                    aria-live="assertive"
                    className="mt-2 p-3 bg-destructive/10 border border-destructive rounded-lg text-destructive text-sm"
                  >
                    {submissionError}
                  </div>
                )}

                {/* Feature: 012-discovery-answer-ui - Keyboard Shortcut Hint (T050) */}
                <div className="mt-2 text-center text-xs text-muted-foreground">
                  💡 Tip: Press <kbd className="px-2 py-1 bg-muted border border-border rounded">Ctrl+Enter</kbd> to submit
                </div>
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
          <div className="text-sm text-muted-foreground italic">
            Discovery not started
          </div>
        )}
      </div>
    </div>
  );
});

DiscoveryProgress.displayName = 'DiscoveryProgress';

export default DiscoveryProgress;
