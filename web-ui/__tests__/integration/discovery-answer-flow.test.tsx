/**
 * Integration Tests: Discovery Answer Flow (012-discovery-answer-ui)
 * Tests complete user workflows end-to-end
 */

// Mock the api-client module BEFORE imports
jest.mock('@/lib/api-client', () => ({
  authFetch: jest.fn(),
}));

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import DiscoveryProgress from '@/components/DiscoveryProgress';
import { projectsApi } from '@/lib/api';
import { authFetch } from '@/lib/api-client';
import type { DiscoveryProgressResponse } from '@/types/api';

const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

// Mock the API
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getDiscoveryProgress: jest.fn(),
  },
}));

// Mock child components
jest.mock('@/components/ProgressBar', () => {
  return function MockProgressBar({ percentage, label }: { percentage: number; label?: string }) {
    return (
      <div data-testid="mock-progress-bar">
        {label && <span>{label}</span>}
        <span>{percentage}%</span>
      </div>
    );
  };
});

jest.mock('@/components/PhaseIndicator', () => {
  return function MockPhaseIndicator({ phase }: { phase: string }) {
    return <span data-testid="mock-phase-indicator">{phase}</span>;
  };
});

describe('Discovery Answer Flow - Integration Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAuthFetch.mockReset();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('Full Submission Flow (T085)', () => {
    it('should complete full flow: type → submit → next question', async () => {
      // Initial state: Question 1 of 20
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      // Updated state: Question 2 of 20
      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 5,
          answered_count: 1,
          total_required: 20,
          current_question: {
            id: 'q2',
            category: 'target_users',
            question: 'Who are your target users?',
          },
        },
      };

      // Mock initial load
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      // Mock successful submit
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Who are your target users?',
        is_complete: false,
        current_index: 1,
        total_questions: 20,
        progress_percentage: 5.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      // STEP 1: Wait for component to load
      await waitFor(() => {
        expect(screen.getByText(/what problem does your project solve/i)).toBeInTheDocument();
      });

      // Verify initial state
      expect(screen.getByText('0%')).toBeInTheDocument();
      expect(screen.getByText(/answered.*0.*20/i)).toBeInTheDocument();

      // STEP 2: Type answer in textarea
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const answer = 'We help remote teams collaborate more effectively with real-time task management.';

      fireEvent.change(textarea, { target: { value: answer } });

      // Verify character counter updates
      expect(screen.getByText(new RegExp(`${answer.length} / 5000 characters`, 'i'))).toBeInTheDocument();

      // Verify submit button is enabled
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      expect(submitButton).not.toBeDisabled();

      // STEP 3: Submit answer
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      fireEvent.click(submitButton);

      // STEP 4: Verify loading state
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /submitting/i })).toBeInTheDocument();
      });

      // Verify textarea is disabled during submission
      expect(textarea).toBeDisabled();

      // STEP 5: Verify success message appears
      await waitFor(() => {
        expect(screen.getByText(/answer submitted.*loading next question/i)).toBeInTheDocument();
      });

      // Verify answer is cleared
      expect(textarea.value).toBe('');

      // STEP 6: Advance timer to trigger state refresh
      jest.advanceTimersByTime(1000);

      // STEP 7: Verify next question appears
      await waitFor(() => {
        expect(screen.getByText(/who are your target users/i)).toBeInTheDocument();
      });

      // Verify previous question is gone
      expect(screen.queryByText(/what problem does your project solve/i)).not.toBeInTheDocument();

      // STEP 8: Verify progress updates
      expect(screen.getByText('5%')).toBeInTheDocument();
      expect(screen.getByText(/answered.*1.*20/i)).toBeInTheDocument();

      // Verify success message is dismissed
      expect(screen.queryByText(/answer submitted/i)).not.toBeInTheDocument();

      // Verify textarea is re-enabled and empty
      expect(textarea).not.toBeDisabled();
      expect(textarea.value).toBe('');

      // Verify submit button is disabled (no new answer yet)
      expect(submitButton).toBeDisabled();
    });

    it('should handle multiple consecutive submissions', async () => {
      const questions = [
        {
          data: {
            project_id: 1,
            phase: 'discovery' as const,
            discovery: {
              state: 'discovering' as const,
              progress_percentage: 0,
              answered_count: 0,
              total_required: 20,
              current_question: {
                category: 'q1',
                question: 'Question 1',
              },
            },
          },
          answer: 'Answer 1',
        },
        {
          data: {
            project_id: 1,
            phase: 'discovery' as const,
            discovery: {
              state: 'discovering' as const,
              progress_percentage: 5,
              answered_count: 1,
              total_required: 20,
              current_question: {
                category: 'q2',
                question: 'Question 2',
              },
            },
          },
          answer: 'Answer 2',
        },
        {
          data: {
            project_id: 1,
            phase: 'discovery' as const,
            discovery: {
              state: 'discovering' as const,
              progress_percentage: 10,
              answered_count: 2,
              total_required: 20,
              current_question: {
                category: 'q3',
                question: 'Question 3',
              },
            },
          },
          answer: 'Answer 3',
        },
      ];

      // Mock initial load
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: questions[0].data });

      mockAuthFetch.mockResolvedValue({ success: true });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Question 1')).toBeInTheDocument();
      });

      // Submit 3 answers in sequence
      for (let i = 0; i < 3; i++) {
        const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;

        fireEvent.change(textarea, { target: { value: questions[i].answer } });

        if (i < 2) {
          (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: questions[i + 1].data });
        }

        const submitButton = screen.getByRole('button', { name: /submit answer/i });
        fireEvent.click(submitButton);

        await waitFor(() => {
          expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
        });

        jest.advanceTimersByTime(1000);

        if (i < 2) {
          await waitFor(() => {
            expect(screen.getByText(`Question ${i + 2}`)).toBeInTheDocument();
          });
        }
      }

      // Verify final state
      expect(screen.getByText('Question 3')).toBeInTheDocument();
      expect(screen.getByText('10%')).toBeInTheDocument();
    });
  });

  describe('Error Recovery Flow (T086)', () => {
    it('should recover from error → fix → successful retry', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 25,
          answered_count: 5,
          total_required: 20,
          current_question: {
            id: 'q6',
            category: 'tech_stack',
            question: 'What technologies will you use?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 30,
          answered_count: 6,
          total_required: 20,
          current_question: {
            id: 'q7',
            category: 'timeline',
            question: 'What is your timeline?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/what technologies will you use/i)).toBeInTheDocument();
      });

      // STEP 1: Attempt to submit with API error
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Project is not in discovery phase')
      );

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const originalAnswer = 'React, TypeScript, Node.js';

      fireEvent.change(textarea, { target: { value: originalAnswer } });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // STEP 2: Verify error message appears
      await waitFor(() => {
        expect(screen.getByText(/project is not in discovery phase/i)).toBeInTheDocument();
      });

      // Verify answer is preserved (not cleared)
      expect(textarea.value).toBe(originalAnswer);

      // Verify textarea has error border
      expect(textarea).toHaveClass('border-destructive');

      // Verify no success message
      expect(screen.queryByText(/answer submitted/i)).not.toBeInTheDocument();

      // Verify submit button is re-enabled
      expect(submitButton).not.toBeDisabled();

      // STEP 3: Fix the error by modifying the answer
      const correctedAnswer = 'React, TypeScript, Node.js, PostgreSQL';
      fireEvent.change(textarea, { target: { value: correctedAnswer } });

      // Error message should still be visible (doesn't auto-clear on input)
      expect(screen.getByText(/project is not in discovery phase/i)).toBeInTheDocument();

      // STEP 4: Retry submission with successful response
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What is your timeline?',
        is_complete: false,
        current_index: 6,
        total_questions: 20,
        progress_percentage: 30.0,
      });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      fireEvent.click(submitButton);

      // STEP 5: Verify success flow
      await waitFor(() => {
        expect(screen.getByText(/answer submitted.*loading next question/i)).toBeInTheDocument();
      });

      // Error message should be cleared
      expect(screen.queryByText(/project is not in discovery phase/i)).not.toBeInTheDocument();

      // Answer should be cleared
      expect(textarea.value).toBe('');

      // Textarea should not have error border anymore
      expect(textarea).not.toHaveClass('border-destructive');

      jest.advanceTimersByTime(1000);

      // STEP 6: Verify next question appears
      await waitFor(() => {
        expect(screen.getByText(/what is your timeline/i)).toBeInTheDocument();
      });

      // Verify progress updated
      expect(screen.getByText('30%')).toBeInTheDocument();
      expect(screen.getByText(/answered.*6.*20/i)).toBeInTheDocument();
    });

    it('should handle network error recovery', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 10,
          total_required: 20,
          current_question: {
            id: 'q11',
            category: 'monetization',
            question: 'How will you make money?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 55,
          answered_count: 11,
          total_required: 20,
          current_question: {
            id: 'q12',
            category: 'competition',
            question: 'Who are your competitors?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/how will you make money/i)).toBeInTheDocument();
      });

      // Simulate network error
      mockAuthFetch.mockRejectedValueOnce(new Error('Network error'));

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const answer = 'Subscription model';

      fireEvent.change(textarea, { target: { value: answer } });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Verify network error message
      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
      });

      // Answer preserved
      expect(textarea.value).toBe(answer);

      // Retry with success
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Who are your competitors?',
        is_complete: false,
        current_index: 11,
        total_questions: 20,
        progress_percentage: 55.0,
      });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      expect(screen.queryByText(/network error/i)).not.toBeInTheDocument();

      jest.advanceTimersByTime(1000);

      await waitFor(() => {
        expect(screen.getByText(/who are your competitors/i)).toBeInTheDocument();
      });
    });
  });
});
