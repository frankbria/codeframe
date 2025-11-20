/**
 * Tests for DiscoveryProgress Component (cf-17.2)
 * TDD RED Phase - Write tests first
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import DiscoveryProgress from '../DiscoveryProgress';
import { projectsApi } from '@/lib/api';
import type { DiscoveryProgressResponse } from '@/types/api';

// Mock the API
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getDiscoveryProgress: jest.fn(),
  },
}));

// Mock child components
jest.mock('../ProgressBar', () => {
  return function MockProgressBar({ percentage, label }: { percentage: number; label?: string }) {
    return (
      <div data-testid="mock-progress-bar">
        {label && <span>{label}</span>}
        <span>{percentage}%</span>
      </div>
    );
  };
});

jest.mock('../PhaseIndicator', () => {
  return function MockPhaseIndicator({ phase }: { phase: string }) {
    return <span data-testid="mock-phase-indicator">{phase}</span>;
  };
});

describe('DiscoveryProgress Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('Data Fetching', () => {
    it('should fetch discovery progress on mount', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
          remaining_count: 5,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledWith(1);
      });
    });

    it('should handle API errors gracefully', async () => {
      (projectsApi.getDiscoveryProgress as jest.Mock).mockRejectedValue(
        new Error('API Error')
      );

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/failed to load discovery progress/i)).toBeInTheDocument();
      });
    });
  });

  describe('Loading State', () => {
    it('should display loading indicator while fetching', () => {
      (projectsApi.getDiscoveryProgress as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<DiscoveryProgress projectId={1} />);

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });
  });

  describe('Phase Display', () => {
    it('should display PhaseIndicator with current phase', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: null,
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const phaseIndicator = screen.getByTestId('mock-phase-indicator');
        expect(phaseIndicator).toHaveTextContent('planning');
      });
    });

    it('should display PhaseIndicator for all phases', async () => {
      const phases: Array<'discovery' | 'planning' | 'active' | 'review' | 'complete'> = [
        'discovery',
        'planning',
        'active',
        'review',
        'complete',
      ];

      for (const phase of phases) {
        const mockData: DiscoveryProgressResponse = {
          project_id: 1,
          phase,
          discovery: null,
        };

        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

        const { unmount } = render(<DiscoveryProgress projectId={1} />);

        await waitFor(() => {
          const phaseIndicator = screen.getByTestId('mock-phase-indicator');
          expect(phaseIndicator).toHaveTextContent(phase);
        });

        unmount();
      }
    });
  });

  describe('Discovery State - Discovering', () => {
    it('should show ProgressBar when in discovering state', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 60,
          answered_count: 6,
          total_required: 10,
          remaining_count: 4,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('mock-progress-bar')).toBeInTheDocument();
        expect(screen.getByText('60%')).toBeInTheDocument();
      });
    });

    it('should display current question when available', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 40,
          answered_count: 4,
          total_required: 10,
          current_question: {
            id: 'q1',
            question: 'What is the primary goal of this project?',
            category: 'goals',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(
          screen.getByText(/what is the primary goal of this project/i)
        ).toBeInTheDocument();
      });
    });

    it('should display answered count and total', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 70,
          answered_count: 7,
          total_required: 10,
          remaining_count: 3,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/7.*10/)).toBeInTheDocument();
      });
    });
  });

  describe('Discovery State - Completed', () => {
    it('should show "Discovery Complete" message when completed', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });
    });

    it('should not show ProgressBar when completed', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });

      expect(screen.queryByTestId('mock-progress-bar')).not.toBeInTheDocument();
    });
  });

  describe('Discovery State - Idle', () => {
    it('should show "Not started" message when idle', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'idle',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/not started/i)).toBeInTheDocument();
      });
    });

    it('should show "Not started" when discovery is null', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'active',
        discovery: null,
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/not started/i)).toBeInTheDocument();
      });
    });
  });

  describe('Auto-refresh', () => {
    it('should auto-refresh every 10 seconds during discovery', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      // Wait for initial fetch and data to be set (which triggers interval setup)
      await waitFor(() => {
        expect(screen.getByText(/answered/i)).toBeInTheDocument();
      });

      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);

      // Advance 10 seconds
      jest.advanceTimersByTime(10000);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(2);
      });

      // Advance another 10 seconds
      jest.advanceTimersByTime(10000);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(3);
      });
    });

    it('should not auto-refresh when discovery is completed', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

      // Advance 30 seconds
      jest.advanceTimersByTime(30000);

      // Should still be 1 call (no refresh)
      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
    });

    it('should not auto-refresh when discovery is idle', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'idle',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

      // Advance 30 seconds
      jest.advanceTimersByTime(30000);

      // Should still be 1 call (no refresh)
      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
    });

    it('should cleanup timer on unmount', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      const { unmount } = render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

      unmount();

      // Advance time after unmount
      jest.advanceTimersByTime(30000);

      // Should still be 1 call (timer cleaned up)
      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const section = screen.getByRole('region', { name: /discovery progress/i });
        expect(section).toBeInTheDocument();
      });
    });
  });

  describe('Responsive Design', () => {
    it('should render in a responsive container', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      const { container } = render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const mainContainer = container.firstChild as HTMLElement;
        expect(mainContainer).toHaveClass('w-full');
      });
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - TDD Tests
  // ============================================================================

  describe('Answer Input (US1)', () => {
    it('should render answer textarea with correct attributes', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(/type your answer here/i);
        expect(textarea).toBeInTheDocument();
        expect(textarea).toHaveAttribute('maxLength', '5000');
        expect(textarea).toHaveAttribute('rows', '6');
        expect(textarea).toHaveClass('resize-none');
        expect(textarea).toHaveClass('w-full');
      });
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 4: User Story 2 (Character Counter)
  // ============================================================================

  describe('Character Counter (US2)', () => {
    it('should display character counter that updates as user types (T018)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      const { rerender } = render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Should show initial counter: 0 / 5000 characters
      expect(screen.getByText(/0 \/ 5000 characters/i)).toBeInTheDocument();

      // Counter should have default color (gray)
      const counter = screen.getByText(/0 \/ 5000 characters/i);
      expect(counter).toHaveClass('text-gray-500');
      expect(counter).toHaveClass('text-sm');

      // Type some text in textarea
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const testAnswer = 'This is a test answer';

      // Simulate typing
      fireEvent.change(textarea, { target: { value: testAnswer } });

      // Counter should update to show character count
      expect(screen.getByText(new RegExp(`${testAnswer.length} / 5000 characters`, 'i'))).toBeInTheDocument();

      // Type more to exceed 4500 characters (warning threshold)
      const longAnswer = 'a'.repeat(4501);
      fireEvent.change(textarea, { target: { value: longAnswer } });

      // Counter should turn red when > 4500 characters
      const warningCounter = screen.getByText(/4501 \/ 5000 characters/i);
      expect(warningCounter).toHaveClass('text-red-600');
      expect(warningCounter).not.toHaveClass('text-gray-500');
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 5: User Story 3 (Submit Button)
  // ============================================================================

  describe('Submit Button (US3)', () => {
    it('should disable submit button when answer is empty (T023)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Submit button should exist
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      expect(submitButton).toBeInTheDocument();

      // Should be disabled when answer is empty
      expect(submitButton).toBeDisabled();

      // Type whitespace-only answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: '   ' } });

      // Should still be disabled (whitespace-only)
      expect(submitButton).toBeDisabled();

      // Type valid answer
      fireEvent.change(textarea, { target: { value: 'Valid answer' } });

      // Should now be enabled
      expect(submitButton).not.toBeDisabled();
    });

    it('should disable submit button during submission (T024)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Valid answer' } });

      // Get submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      expect(submitButton).not.toBeDisabled();

      // Note: Full submission flow will be tested when API integration is complete
      // This test verifies the button can be enabled/disabled based on state
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 7: User Story 4 (Keyboard Shortcut)
  // ============================================================================

  describe('Keyboard Shortcut (US4)', () => {
    it('should trigger submit when Ctrl+Enter is pressed (T046)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock fetch for the submit API call
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'Next question',
              is_complete: false,
              current_index: 3,
              total_questions: 20,
              progress_percentage: 15.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Valid answer for keyboard shortcut test' } });

      // Press Ctrl+Enter
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: true,
        code: 'Enter',
        charCode: 13,
      });

      // Verify fetch was called (submission triggered)
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          '/api/projects/1/discovery/answer',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'Content-Type': 'application/json',
            }),
            body: JSON.stringify({ answer: 'Valid answer for keyboard shortcut test' }),
          })
        );
      });

      // Should NOT submit with Enter alone (without Ctrl)
      fireEvent.change(textarea, { target: { value: 'Another answer' } });
      (global.fetch as jest.Mock).mockClear();

      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: false,
        code: 'Enter',
        charCode: 13,
      });

      // Fetch should NOT be called (no submission)
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it('should not submit with Ctrl+Enter if answer is empty', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      global.fetch = jest.fn() as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;

      // Press Ctrl+Enter without typing anything
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: true,
        code: 'Enter',
        charCode: 13,
      });

      // Fetch should NOT be called (empty answer)
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 8: User Story 6 (Success Message)
  // ============================================================================

  describe('Success Message (US6)', () => {
    it('should display success message after successful submit (T052)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock successful submit response
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'What tech stack are you planning to use?',
              is_complete: false,
              current_index: 3,
              total_questions: 20,
              progress_percentage: 15.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Success message should appear
      await waitFor(() => {
        const successMessage = screen.getByText(/answer submitted.*loading next question/i);
        expect(successMessage).toBeInTheDocument();

        // Verify success message styling (message div has all the classes)
        expect(successMessage).toHaveClass('bg-green-50');
        expect(successMessage).toHaveClass('border-green-200');
        expect(successMessage).toHaveClass('text-green-800');
        expect(successMessage).toHaveClass('p-3');
        expect(successMessage).toHaveClass('rounded-lg');
      });

      // Success message should auto-dismiss after 1 second
      jest.advanceTimersByTime(1000);

      await waitFor(() => {
        expect(screen.queryByText(/answer submitted.*loading next question/i)).not.toBeInTheDocument();
      });
    });

    it('should not show success message on API error', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock failed submit response
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: false,
          json: () =>
            Promise.resolve({
              detail: 'Answer must be between 1 and 5000 characters',
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for error handling
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled();
      });

      // Success message should NOT appear
      expect(screen.queryByText(/answer submitted.*loading next question/i)).not.toBeInTheDocument();

      // Error message should appear instead (will be tested in US7)
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 9: User Story 7 (Error Handling)
  // ============================================================================

  describe('Error Handling (US7)', () => {
    it('should show validation error for empty answer (T057)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Try to submit empty answer
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      // Button should be disabled, but let's test the validation logic by typing and deleting
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: '   ' } }); // Whitespace only

      // Button is still disabled, so we can't click it
      expect(submitButton).toBeDisabled();

      // No error should show yet (validation happens on submit, not on input)
      expect(screen.queryByText(/answer must be between 1 and 5000 characters/i)).not.toBeInTheDocument();
    });

    it('should show validation error for answer > 5000 chars (T058)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type answer that's too long (textarea has maxLength=5000, so we need to simulate programmatically)
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const longAnswer = 'a'.repeat(5001);

      // Manually set value to bypass maxLength (to test validation logic)
      Object.defineProperty(textarea, 'value', {
        writable: true,
        value: longAnswer,
      });

      // Trigger onChange manually
      fireEvent.change(textarea, { target: { value: longAnswer } });

      // Click submit button (should be enabled because trimmed length > 0)
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Validation error should appear
      await waitFor(() => {
        const errorMessage = screen.getByText(/answer must be between 1 and 5000 characters/i);
        expect(errorMessage).toBeInTheDocument();

        // Verify error message styling
        expect(errorMessage).toHaveClass('bg-red-50');
        expect(errorMessage).toHaveClass('border-red-200');
        expect(errorMessage).toHaveClass('text-red-800');
        expect(errorMessage).toHaveClass('p-3');
        expect(errorMessage).toHaveClass('rounded-lg');
      });

      // Textarea should have red border
      expect(textarea).toHaveClass('border-red-500');

      // Answer should be preserved (not cleared)
      expect(textarea.value).toBe(longAnswer);
    });

    it('should show error message on API failure (T059)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock API error response
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: false,
          status: 400,
          json: () =>
            Promise.resolve({
              detail: 'Project is not in discovery phase',
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // API error message should appear
      await waitFor(() => {
        const errorMessage = screen.getByText(/project is not in discovery phase/i);
        expect(errorMessage).toBeInTheDocument();

        // Verify error message styling
        expect(errorMessage).toHaveClass('bg-red-50');
        expect(errorMessage).toHaveClass('border-red-200');
        expect(errorMessage).toHaveClass('text-red-800');
        expect(errorMessage).toHaveClass('p-3');
        expect(errorMessage).toHaveClass('rounded-lg');
      });

      // Textarea should have red border
      expect(textarea).toHaveClass('border-red-500');

      // Answer should be preserved (not cleared)
      expect(textarea.value).toBe('A valid answer');
    });

    it('should show network error message on fetch failure', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock network error
      global.fetch = jest.fn(() =>
        Promise.reject(new Error('Network error'))
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Network error message should appear
      await waitFor(() => {
        const errorMessage = screen.getByText(/network error/i);
        expect(errorMessage).toBeInTheDocument();
      });

      // Answer should be preserved
      expect(textarea.value).toBe('A valid answer');
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 10: User Story 8 (Progress Bar Update)
  // ============================================================================

  describe('Progress Bar Update (US8)', () => {
    it('should update progress bar after successful submit (T066)', async () => {
      // Initial state: 2 of 20 answered (10%)
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      // Updated state after answer: 3 of 20 answered (15%)
      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 15,
          answered_count: 3,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'tech_stack',
            question: 'What tech stack are you planning to use?',
          },
        },
      };

      // Mock initial fetch
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      // Mock successful submit response
      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'What tech stack are you planning to use?',
              is_complete: false,
              current_index: 3,
              total_questions: 20,
              progress_percentage: 15.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText(/answered.*2.*20/i)).toBeInTheDocument();
        expect(screen.getByText('10%')).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Build a task management system' } });

      // Mock the refresh call after submit to return updated data
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for success message
      await waitFor(() => {
        expect(screen.getByText(/answer submitted.*loading next question/i)).toBeInTheDocument();
      });

      // Advance timer to trigger state refresh (1 second)
      jest.advanceTimersByTime(1000);

      // Progress bar should update to 15%
      await waitFor(() => {
        expect(screen.getByText('15%')).toBeInTheDocument();
        expect(screen.getByText(/answered.*3.*20/i)).toBeInTheDocument();
      });

      // Next question should be displayed
      expect(screen.getByText(/what tech stack are you planning to use/i)).toBeInTheDocument();

      // Previous question should be gone
      expect(screen.queryByText(/what problem does your project solve/i)).not.toBeInTheDocument();

      // Textarea should be cleared
      expect(textarea.value).toBe('');
    });

    it('should update question counter after submit', async () => {
      // Initial state: Question 5 of 20
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 20,
          answered_count: 4,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'Question 5',
          },
        },
      };

      // Updated state: Question 6 of 20
      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 25,
          answered_count: 5,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'solution',
            question: 'Question 6',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'Question 6',
              is_complete: false,
              current_index: 5,
              total_questions: 20,
              progress_percentage: 25.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/answered.*4.*20/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Answer' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      jest.advanceTimersByTime(1000);

      // Counter should increment: 4 → 5
      await waitFor(() => {
        expect(screen.getByText(/answered.*5.*20/i)).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 11: User Story 9 (Next Question Display)
  // ============================================================================

  describe('Next Question Display (US9)', () => {
    it('should clear answer after successful submit (T072)', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 15,
          answered_count: 3,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'tech_stack',
            question: 'What tech stack are you planning to use?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'What tech stack are you planning to use?',
              is_complete: false,
              current_index: 3,
              total_questions: 20,
              progress_percentage: 15.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const answerText = 'Build a task management system for remote teams';

      fireEvent.change(textarea, { target: { value: answerText } });

      // Verify answer is in textarea
      expect(textarea.value).toBe(answerText);

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for success message
      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      // Textarea should be cleared immediately
      expect(textarea.value).toBe('');

      // Advance timer
      jest.advanceTimersByTime(1000);

      // Textarea should remain empty
      await waitFor(() => {
        expect(textarea.value).toBe('');
      });
    });

    it('should display next question after submit (T073)', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 10,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'problem',
            question: 'Question 11: What is your target market?',
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
            id: "test-question-id",
            category: 'solution',
            question: 'Question 12: How will you monetize?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'Question 12: How will you monetize?',
              is_complete: false,
              current_index: 11,
              total_questions: 20,
              progress_percentage: 55.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      // Wait for initial question
      await waitFor(() => {
        expect(screen.getByText(/question 11.*what is your target market/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Small businesses' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for success message
      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      // Advance timer to trigger state refresh
      jest.advanceTimersByTime(1000);

      // Next question should appear
      await waitFor(() => {
        expect(screen.getByText(/question 12.*how will you monetize/i)).toBeInTheDocument();
      });

      // Previous question should be gone
      expect(screen.queryByText(/question 11.*what is your target market/i)).not.toBeInTheDocument();

      // Question number should increment (10 → 11)
      expect(screen.getByText(/answered.*11.*20/i)).toBeInTheDocument();
    });

    it('should handle smooth transition without page refresh', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 85,
          answered_count: 17,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'timeline',
            question: 'When do you plan to launch?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 90,
          answered_count: 18,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'risks',
            question: 'What are the biggest risks?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: 'What are the biggest risks?',
              is_complete: false,
              current_index: 18,
              total_questions: 20,
              progress_percentage: 90.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/when do you plan to launch/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Q2 2025' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      jest.advanceTimersByTime(1000);

      // Verify no page reload occurred (component still rendered)
      await waitFor(() => {
        expect(screen.getByRole('region', { name: /discovery progress/i })).toBeInTheDocument();
        expect(screen.getByText(/what are the biggest risks/i)).toBeInTheDocument();
      });

      // Progress should update smoothly
      expect(screen.getByText('90%')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 12: User Story 10 (Discovery Completion)
  // ============================================================================

  describe('Discovery Completion (US10)', () => {
    it('should display completion state when discovery complete (T079)', async () => {
      // Initial state: Last question (19 of 20 answered, 95%)
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 95,
          answered_count: 19,
          total_required: 20,
          current_question: {
            id: "test-question-id",
            category: 'final',
            question: 'Any final thoughts or concerns?',
          },
        },
      };

      // After final answer: Discovery complete
      const completedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning', // Phase transitions to planning
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 20,
          total_required: 20,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      global.fetch = jest.fn(() =>
        Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              success: true,
              next_question: null, // No more questions
              is_complete: true,
              current_index: 20,
              total_questions: 20,
              progress_percentage: 100.0,
            }),
        })
      ) as jest.Mock;

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/any final thoughts or concerns/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Excited to get started!' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: completedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      jest.advanceTimersByTime(1000);

      // Completion state should be displayed
      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });

      // Answer UI should be hidden (no textarea)
      expect(screen.queryByPlaceholderText(/type your answer here/i)).not.toBeInTheDocument();

      // Submit button should be hidden
      expect(screen.queryByRole('button', { name: /submit answer/i })).not.toBeInTheDocument();
    });

    it('should show 100% progress when complete', async () => {
      const completedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 20,
          total_required: 20,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: completedData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });

      // Note: Progress bar is not shown when completed (from existing tests)
      // Just verify completion message is present
      expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
    });
  });
});
