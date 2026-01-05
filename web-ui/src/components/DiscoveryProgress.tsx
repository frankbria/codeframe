/**
 * DiscoveryProgress Component (cf-17.2)
 * Displays discovery phase progress with auto-refresh functionality
 */

'use client';

import { useEffect, useState, memo, useCallback, useRef } from 'react';
import { projectsApi } from '@/lib/api';
import { authFetch } from '@/lib/api-client';
import { getWebSocketClient } from '@/lib/websocket';
import type { DiscoveryProgressResponse } from '@/types/api';
import type { WebSocketMessage } from '@/types';
import ProgressBar from './ProgressBar';
import PhaseIndicator from './PhaseIndicator';
import { Cancel01Icon, CheckmarkCircle01Icon } from '@hugeicons/react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

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
  const [isLoadingNextQuestion, setIsLoadingNextQuestion] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  // Start Discovery state
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // PRD Generation state
  const [isGeneratingPRD, setIsGeneratingPRD] = useState(false);
  const [prdCompleted, setPrdCompleted] = useState(false);
  const [prdError, setPrdError] = useState<string | null>(null);
  const [prdStage, setPrdStage] = useState<string>('');
  const [prdMessage, setPrdMessage] = useState<string>('');
  const [prdProgressPct, setPrdProgressPct] = useState<number>(0);

  // Timeout/Stuck state detection
  const [waitingForQuestionStart, setWaitingForQuestionStart] = useState<number | null>(null);
  const [isStuck, setIsStuck] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);
  const STUCK_TIMEOUT_MS = 30000; // 30 seconds without a question = stuck

  // Ref to track if we should clear isStarting on next fetch
  const clearIsStartingOnFetch = useRef(false);

  // PRD retry state
  const [isRetryingPrd, setIsRetryingPrd] = useState(false);

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

    try {
      // T038: POST request to backend with authentication
      await authFetch(
        `${API_BASE_URL}/api/projects/${projectId}/discovery/answer`,
        {
          method: 'POST',
          body: { answer: trimmedAnswer },
        }
      );

      // Success - immediately show loading state for next question
      setIsSubmitting(false);
      setIsLoadingNextQuestion(true);
      setAnswer(''); // Clear textarea
      setSubmissionError(null);

      // Fetch next question immediately (separate try-catch for fetch failure)
      try {
        const response = await projectsApi.getDiscoveryProgress(projectId);
        setData(response.data);

        // Check if discovery just completed
        if (response.data.discovery?.state === 'completed') {
          setIsGeneratingPRD(true);
        }
      } catch (fetchError) {
        // Answer was submitted successfully, but refresh failed
        console.warn('Failed to fetch updated progress after answer submission:', fetchError);
        // Don't show error - answer was submitted. User can manually refresh.
      } finally {
        setIsLoadingNextQuestion(false);
      }

    } catch (error) {
      // T040: Handle network and API errors - this is a submission failure
      console.error('Failed to submit answer:', error);
      if (error instanceof Error) {
        setSubmissionError(error.message);
      } else {
        setSubmissionError('Failed to submit answer. Please check your connection.');
      }
      // Keep answer in textarea for retry
      setIsSubmitting(false);
      setIsLoadingNextQuestion(false);
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
  const fetchProgress = useCallback(async () => {
    try {
      const response = await projectsApi.getDiscoveryProgress(projectId);
      setData(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load discovery progress');
      console.error('Error fetching discovery progress:', err);
    } finally {
      setLoading(false);
      // Only clear isStarting if this fetch was triggered by handleStartDiscovery
      if (clearIsStartingOnFetch.current) {
        setIsStarting(false);
        clearIsStartingOnFetch.current = false;
      }
    }
  }, [projectId]);

  // Start discovery for idle projects
  const handleStartDiscovery = async () => {
    if (isStarting) return;

    setIsStarting(true);
    setStartError(null);

    try {
      await projectsApi.startProject(projectId);
      // WebSocket "discovery_starting" message will trigger refresh
      // Poll after 2 seconds as fallback in case WebSocket is slow
      clearIsStartingOnFetch.current = true;
      setTimeout(() => {
        fetchProgress();
      }, 2000);
    } catch (err) {
      console.error('Failed to start discovery:', err);
      setStartError('Failed to start discovery. Please try again.');
      setIsStarting(false);
    }
    // Note: isStarting is cleared by fetchProgress() when data arrives (via clearIsStartingOnFetch ref)
  };

  // Restart discovery when stuck
  const handleRestartDiscovery = async () => {
    if (isRestarting) return;

    setIsRestarting(true);
    setRestartError(null);
    setIsStuck(false);

    try {
      await projectsApi.restartDiscovery(projectId);
      // This resets state to idle, so the Start Discovery button will appear
      setWaitingForQuestionStart(null);
      fetchProgress();
    } catch (err) {
      console.error('Failed to restart discovery:', err);
      setRestartError('Failed to restart discovery. Please try again.');
      setIsRestarting(false);
    }
  };

  // Retry PRD generation when it fails
  const handleRetryPrdGeneration = async () => {
    if (isRetryingPrd || isGeneratingPRD) return;

    setIsRetryingPrd(true);
    setPrdError(null);

    try {
      await projectsApi.retryPrdGeneration(projectId);
      // The WebSocket message will update the UI
      setIsGeneratingPRD(true);
      setPrdStage('starting');
      setPrdMessage('Retrying PRD generation...');
      setPrdProgressPct(0);
    } catch (err) {
      console.error('Failed to retry PRD generation:', err);
      if (err instanceof Error) {
        setPrdError(`Failed to retry: ${err.message}`);
      } else {
        setPrdError('Failed to retry PRD generation. Please try again.');
      }
    } finally {
      setIsRetryingPrd(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  // Timeout detection for stuck discovery state
  useEffect(() => {
    const isDiscovering = data?.discovery?.state === 'discovering';
    const hasQuestion = !!data?.discovery?.current_question;

    // If we're discovering but have no question, start tracking timeout
    if (isDiscovering && !hasQuestion && !isLoadingNextQuestion) {
      if (!waitingForQuestionStart) {
        setWaitingForQuestionStart(Date.now());
      }
    } else {
      // Reset when we have a question or leave discovering state
      setWaitingForQuestionStart(null);
      setIsStuck(false);
      setIsRestarting(false);
    }
  }, [data?.discovery?.state, data?.discovery?.current_question, isLoadingNextQuestion, waitingForQuestionStart]);

  // Check for stuck state periodically
  useEffect(() => {
    if (!waitingForQuestionStart) return;

    const checkStuck = () => {
      const elapsed = Date.now() - waitingForQuestionStart;
      if (elapsed >= STUCK_TIMEOUT_MS && !isStuck) {
        setIsStuck(true);
      }
    };

    // Check immediately and then every 5 seconds
    checkStuck();
    const intervalId = setInterval(checkStuck, 5000);

    return () => clearInterval(intervalId);
  }, [waitingForQuestionStart, isStuck, STUCK_TIMEOUT_MS]);

  // WebSocket listener for immediate feedback
  useEffect(() => {
    const wsClient = getWebSocketClient();

    const handleMessage = (message: WebSocketMessage) => {
      // Only handle messages for this project
      if ('project_id' in message && message.project_id !== projectId) {
        return;
      }

      // Handle discovery_starting - shows immediate feedback when Start Discovery is clicked
      if (message.type === 'discovery_starting') {
        setIsStarting(true);
        // Fetch latest progress after a short delay
        setTimeout(() => fetchProgress(), 500);
      }

      // Handle agent_started - refresh to get current discovery state
      if (message.type === 'agent_started') {
        fetchProgress();
      }

      // Handle status_update - may indicate discovery state change
      if (message.type === 'status_update') {
        fetchProgress();
      }

      // Handle discovery_completed - show PRD generation status
      if (message.type === 'discovery_completed') {
        setIsGeneratingPRD(true);
        fetchProgress();
      }

      // Handle PRD generation events
      if (message.type === 'prd_generation_started') {
        setIsGeneratingPRD(true);
        setPrdCompleted(false);
        setPrdError(null);
        setPrdStage('starting');
        setPrdMessage('Initializing PRD generation...');
        setPrdProgressPct(0);
      }

      // Handle PRD generation progress updates
      if (message.type === 'prd_generation_progress') {
        setIsGeneratingPRD(true);
        setPrdStage(message.stage || '');
        setPrdMessage(message.message || '');
        setPrdProgressPct(message.progress_pct || 0);
      }

      if (message.type === 'prd_generation_completed') {
        setIsGeneratingPRD(false);
        setPrdCompleted(true);
        setPrdError(null);
        setPrdStage('completed');
        setPrdMessage('PRD generated successfully');
        setPrdProgressPct(100);
        fetchProgress(); // Refresh to get updated phase
      }

      if (message.type === 'prd_generation_failed') {
        setIsGeneratingPRD(false);
        setPrdCompleted(false);
        // Extract error from data or use default message
        const errorMsg = message.data?.error ||
          (message as { error?: string }).error ||
          'PRD generation failed';
        setPrdError(errorMsg);
        setPrdStage('failed');
        setPrdProgressPct(0);
      }

      // Handle discovery reset - refresh to show idle state
      if (message.type === 'discovery_reset') {
        setIsStuck(false);
        setIsRestarting(false);
        setWaitingForQuestionStart(null);
        fetchProgress();
      }

      // Handle discovery_question_ready - first question is available
      if (message.type === 'discovery_question_ready') {
        // Clear any stuck/waiting state
        setIsStuck(false);
        setWaitingForQuestionStart(null);
        setIsStarting(false);
        // Refresh to get the question data
        fetchProgress();
      }
    };

    const unsubscribe = wsClient.onMessage(handleMessage);
    return () => {
      unsubscribe();
    };
  }, [projectId, fetchProgress]);

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

            {/* Loading state for next question */}
            {isLoadingNextQuestion && (
              <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary" data-testid="loading-next-question">
                <div className="flex items-center justify-center gap-3 py-4">
                  <svg className="animate-spin h-5 w-5 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span className="text-sm text-primary font-medium">Generating next question...</span>
                </div>
              </div>
            )}

            {/* Current question (hidden while loading next) */}
            {discovery.current_question && !isLoadingNextQuestion && (
              <div className="mt-4 p-4 bg-primary/10 rounded-lg border border-primary" data-testid="discovery-question">
                <div className="text-xs font-medium text-primary uppercase mb-1">
                  Current Question ({discovery.current_question.category})
                </div>
                <div className="text-sm text-foreground">
                  {discovery.current_question.question}
                </div>
              </div>
            )}

            {/* No question available - show loading/waiting state or stuck state */}
            {!discovery.current_question && !isLoadingNextQuestion && (
              <div
                className={`mt-4 p-4 rounded-lg border ${
                  isStuck ? 'bg-amber-50 border-amber-300' : 'bg-primary/10 border-primary'
                }`}
                data-testid={isStuck ? 'discovery-stuck' : 'waiting-for-question'}
              >
                {isStuck ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <span className="text-amber-600 text-lg">⚠️</span>
                      <span className="text-sm font-medium text-amber-800">
                        Discovery appears to be stuck
                      </span>
                    </div>
                    <p className="text-xs text-amber-700">
                      The discovery process has been waiting for a question for too long.
                      This can happen if there was a network error or the AI service is unavailable.
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={handleRestartDiscovery}
                        disabled={isRestarting}
                        data-testid="restart-discovery-button"
                        className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                          isRestarting
                            ? 'bg-muted cursor-not-allowed text-muted-foreground'
                            : 'bg-amber-600 hover:bg-amber-700 text-white'
                        }`}
                      >
                        {isRestarting ? 'Restarting...' : 'Restart Discovery'}
                      </button>
                    </div>
                    {restartError && (
                      <div
                        role="alert"
                        className="p-2 bg-destructive/10 border border-destructive rounded text-destructive text-xs"
                      >
                        {restartError}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center justify-center gap-3 py-4">
                    <svg className="animate-spin h-5 w-5 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span className="text-sm text-primary font-medium">Preparing discovery questions...</span>
                  </div>
                )}
              </div>
            )}

            {/* Feature: 012-discovery-answer-ui - Answer Input (T015, T016) */}
            {discovery.current_question && !isLoadingNextQuestion && (
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
                    className={`py-2 px-6 rounded-lg font-semibold transition-colors flex items-center gap-2 ${
                      isSubmitting || !answer.trim()
                        ? 'bg-muted cursor-not-allowed text-muted-foreground'
                        : 'bg-primary hover:bg-primary/90 text-primary-foreground'
                    }`}
                  >
                    {isSubmitting && (
                      <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                    )}
                    {isSubmitting ? 'Submitting...' : 'Submit Answer'}
                  </button>
                </div>

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
          <div className="space-y-4">
            {/* Discovery Complete Banner */}
            <div className="flex items-center gap-2 p-4 bg-green-50 rounded-lg border border-green-200">
              <span className="text-green-600 text-lg">✓</span>
              <span className="text-sm font-medium text-green-800">
                Discovery Complete — All questions answered
              </span>
            </div>

            {/* PRD Generation Status */}
            <div className={`p-4 rounded-lg border ${
              prdCompleted
                ? 'bg-green-50 border-green-200'
                : prdError
                  ? 'bg-destructive/10 border-destructive'
                  : 'bg-primary/10 border-primary'
            }`} data-testid="prd-generation-status">
              <div className="flex items-center gap-3">
                {isGeneratingPRD ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-primary flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <div className="flex-1">
                      <div className="text-sm font-medium text-primary">
                        {prdMessage || 'Generating Project Requirements Document...'}
                      </div>
                      {/* Progress bar for PRD generation */}
                      <div className="mt-2">
                        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                          <span className="capitalize">{prdStage.replace('_', ' ') || 'Starting'}</span>
                          <span>{prdProgressPct}%</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary transition-all duration-500 ease-out"
                            style={{ width: `${prdProgressPct}%` }}
                          />
                        </div>
                      </div>
                      <div className="text-xs text-muted-foreground mt-2">
                        The Lead Agent is analyzing your answers and creating a detailed PRD
                      </div>
                    </div>
                  </>
                ) : prdCompleted ? (
                  <>
                    <CheckmarkCircle01Icon className="text-green-600 h-5 w-5 flex-shrink-0" aria-hidden="true" />
                    <div>
                      <div className="text-sm font-medium text-green-800">PRD Generated Successfully</div>
                      <div className="text-xs text-green-700 mt-1">Your Project Requirements Document is ready. View it in the Documents section.</div>
                    </div>
                  </>
                ) : prdError ? (
                  <>
                    <Cancel01Icon className="text-destructive h-5 w-5 flex-shrink-0" aria-hidden="true" />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-destructive">PRD Generation Failed</div>
                      <div className="text-xs text-destructive/80 mt-1">{prdError}</div>
                      <button
                        onClick={handleRetryPrdGeneration}
                        disabled={isRetryingPrd}
                        data-testid="retry-prd-button"
                        className={`mt-3 px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                          isRetryingPrd
                            ? 'bg-muted cursor-not-allowed text-muted-foreground'
                            : 'bg-destructive hover:bg-destructive/90 text-destructive-foreground'
                        }`}
                      >
                        {isRetryingPrd ? 'Retrying...' : 'Retry PRD Generation'}
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <svg className="animate-spin h-5 w-5 text-primary flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <div>
                      <div className="text-sm font-medium text-primary">Starting PRD Generation...</div>
                      <div className="text-xs text-muted-foreground mt-1">The Lead Agent is preparing to generate your Project Requirements Document</div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Idle/Not Started State */}
        {isIdle && (
          <div className="space-y-3">
            <div className="text-sm text-muted-foreground italic">
              Discovery not started
            </div>
            <button
              onClick={handleStartDiscovery}
              disabled={isStarting}
              data-testid="start-discovery-button"
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                isStarting
                  ? 'bg-muted cursor-not-allowed text-muted-foreground'
                  : 'bg-primary hover:bg-primary/90 text-primary-foreground'
              }`}
            >
              {isStarting ? 'Starting...' : 'Start Discovery'}
            </button>
            {startError && (
              <div
                role="alert"
                className="p-3 bg-destructive/10 border border-destructive rounded-lg text-destructive text-sm"
              >
                {startError}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

DiscoveryProgress.displayName = 'DiscoveryProgress';

export default DiscoveryProgress;
