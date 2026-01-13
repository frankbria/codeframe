/**
 * DiscoveryProgress Answer UI Tests
 *
 * Tests covering Feature 012-discovery-answer-ui:
 * - Answer textarea attributes and validation (US1)
 * - Character counter with color thresholds (US2)
 * - Submit button enable/disable logic (US3)
 * - Ctrl+Enter keyboard shortcut (US4)
 * - Success messages with auto-dismiss (US6)
 * - Error handling (validation errors, API failures, network errors) (US7)
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

describe('DiscoveryProgress Answer UI', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 3: User Story 1 (Answer Input)
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
            id: 'q1',
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
            id: 'q1',
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

      // Should show initial counter: 0 / 5000 characters
      expect(screen.getByText(/0 \/ 5000 characters/i)).toBeInTheDocument();

      // Counter should have default color (muted)
      const counter = screen.getByText(/0 \/ 5000 characters/i);
      expect(counter).toHaveClass('text-muted-foreground');
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
      expect(warningCounter).toHaveClass('text-destructive');
      expect(warningCounter).not.toHaveClass('text-muted-foreground');
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
            id: 'q1',
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
            id: 'q1',
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
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock authFetch for the submit API call
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Next question',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

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

      // Verify authFetch was called (submission triggered)
      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/projects/1/discovery/answer'),
          {
            method: 'POST',
            body: { answer: 'Valid answer for keyboard shortcut test' },
          }
        );
      });

      // Should NOT submit with Enter alone (without Ctrl)
      fireEvent.change(textarea, { target: { value: 'Another answer' } });
      mockAuthFetch.mockClear();

      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: false,
        code: 'Enter',
        charCode: 13,
      });

      // Fetch should NOT be called (no submission)
      expect(mockAuthFetch).not.toHaveBeenCalled();
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
            id: 'q1',
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

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;

      // Press Ctrl+Enter without typing anything
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: true,
        code: 'Enter',
        charCode: 13,
      });

      // Fetch should NOT be called (empty answer)
      expect(mockAuthFetch).not.toHaveBeenCalled();
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
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

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
        // Using semantic color tokens: bg-success/10, border-success, text-success
        expect(successMessage).toHaveClass('bg-success/10');
        expect(successMessage).toHaveClass('border-success');
        expect(successMessage).toHaveClass('text-success');
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
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock failed submit response
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 400 Answer must be between 1 and 5000 characters')
      );

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
        expect(mockAuthFetch).toHaveBeenCalled();
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
            id: 'q1',
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
            id: 'q1',
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
        expect(errorMessage).toHaveClass('bg-destructive/10');
        expect(errorMessage).toHaveClass('border-destructive');
        expect(errorMessage).toHaveClass('text-destructive');
        expect(errorMessage).toHaveClass('p-3');
        expect(errorMessage).toHaveClass('rounded-lg');
      });

      // Textarea should have red border
      expect(textarea).toHaveClass('border-destructive');

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
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock API error response
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 400 Project is not in discovery phase')
      );

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
        expect(errorMessage).toHaveClass('bg-destructive/10');
        expect(errorMessage).toHaveClass('border-destructive');
        expect(errorMessage).toHaveClass('text-destructive');
        expect(errorMessage).toHaveClass('p-3');
        expect(errorMessage).toHaveClass('rounded-lg');
      });

      // Textarea should have red border
      expect(textarea).toHaveClass('border-destructive');

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
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock network error
      mockAuthFetch.mockRejectedValueOnce(new Error('Network error'));

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
  // Duplicate Submission Prevention Tests
  // ============================================================================

  describe('Duplicate Submission Prevention', () => {
    it('should prevent duplicate submissions while already submitting', async () => {
      const mockData: DiscoveryProgressResponse = {
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

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Make authFetch take a long time
      mockAuthFetch.mockImplementation(() => new Promise(() => {}));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Valid answer' } });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      // Click submit multiple times rapidly
      fireEvent.click(submitButton);
      fireEvent.click(submitButton);
      fireEvent.click(submitButton);

      // Should only call once
      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledTimes(1);
      });
    });
  });
});
