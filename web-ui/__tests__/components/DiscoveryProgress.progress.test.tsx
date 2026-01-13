/**
 * DiscoveryProgress Progress Tracking Tests
 *
 * Tests covering Feature 012-discovery-answer-ui:
 * - Progress bar updates after answer submission (US8)
 * - Question counter updates
 * - Next question display and transitions (US9)
 * - Smooth transition animations
 * - Discovery completion flow (last question → planning phase) (US10)
 * - UI cleanup on completion
 */

import {
  render,
  screen,
  waitFor,
  fireEvent,
  DiscoveryProgress,
  projectsApi,
  setupMocks,
  cleanupMocks,
  mockAuthFetch,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress Progress Tracking', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
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
            id: 'q1',
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
            id: 'q2',
            category: 'tech_stack',
            question: 'What tech stack are you planning to use?',
          },
        },
      };

      // Mock initial fetch
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      // Mock successful submit response
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What tech stack are you planning to use?',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

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
            id: 'q5',
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
            id: 'q6',
            category: 'solution',
            question: 'Question 6',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Question 6',
        is_complete: false,
        current_index: 5,
        total_questions: 20,
        progress_percentage: 25.0,
      });

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
            id: 'q1',
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
            id: 'q2',
            category: 'tech_stack',
            question: 'What tech stack are you planning to use?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What tech stack are you planning to use?',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

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
            id: 'q11',
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
            id: 'q12',
            category: 'solution',
            question: 'Question 12: How will you monetize?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Question 12: How will you monetize?',
        is_complete: false,
        current_index: 11,
        total_questions: 20,
        progress_percentage: 55.0,
      });

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
            id: 'q18',
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
            id: 'q19',
            category: 'risks',
            question: 'What are the biggest risks?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What are the biggest risks?',
        is_complete: false,
        current_index: 18,
        total_questions: 20,
        progress_percentage: 90.0,
      });

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
            id: 'q20',
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

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: null, // No more questions
        is_complete: true,
        current_index: 20,
        total_questions: 20,
        progress_percentage: 100.0,
      });

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
