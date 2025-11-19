/**
 * Discovery Answer UI Integration - Type Definitions
 * Feature: 012-discovery-answer-ui
 */

/**
 * Discovery state representation for frontend
 */
export interface DiscoveryState {
  /** Current phase: discovering | prd_generation | complete */
  phase: 'discovering' | 'prd_generation' | 'complete';

  /** Current question being presented to user */
  currentQuestion: string | null;

  /** Unique identifier for current question */
  currentQuestionId: string | null;

  /** Current question number (1-based for display) */
  currentQuestionIndex: number;

  /** Total number of questions in discovery */
  totalQuestions: number;

  /** Number of questions answered so far */
  answeredCount: number;

  /** Discovery completion percentage (0-100) */
  progressPercentage: number;

  /** Whether all questions have been answered */
  isComplete: boolean;
}

/**
 * Discovery answer submission payload
 */
export interface DiscoveryAnswer {
  /** User's answer text (1-5000 characters after trimming) */
  answer: string;
}

/**
 * Props for DiscoveryProgress component
 */
export interface DiscoveryProgressProps {
  /** Project ID for API calls */
  projectId: number;

  /** Refresh interval in milliseconds (default: 5000) */
  refreshInterval?: number;
}

/**
 * API response after answer submission
 */
export interface DiscoveryAnswerResponse {
  /** Whether the answer was successfully processed */
  success: boolean;

  /** Next discovery question text (null if discovery complete) */
  next_question: string | null;

  /** Whether the discovery phase is complete */
  is_complete: boolean;

  /** Current question index (0-based) */
  current_index: number;

  /** Total number of discovery questions */
  total_questions: number;

  /** Discovery completion percentage (0.0 - 100.0) */
  progress_percentage: number;
}
