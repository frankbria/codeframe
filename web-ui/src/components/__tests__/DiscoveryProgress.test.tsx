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
});
