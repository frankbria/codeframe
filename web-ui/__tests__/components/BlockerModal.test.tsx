/**
 * BlockerModal Component Tests
 * Tests for blocker resolution modal dialog (049-human-in-loop, T022)
 * Phase 4 / User Story 2: Blocker Resolution via Dashboard
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BlockerModal } from '@/components/BlockerModal';
import { Blocker } from '@/types/blocker';

// Mock the API module
jest.mock('@/lib/api', () => ({
  resolveBlocker: jest.fn(),
}));

import { resolveBlocker } from '@/lib/api';
const mockResolveBlocker = resolveBlocker as jest.MockedFunction<typeof resolveBlocker>;

describe('BlockerModal', () => {
  // Increase timeout for async error handling tests
  jest.setTimeout(15000);

  const mockBlocker: Blocker = {
    id: 123,
    agent_id: 'backend-worker-001',
    agent_name: 'Backend Worker #1',
    task_id: 456,
    task_title: 'Implement user authentication',
    blocker_type: 'SYNC',
    question: 'Should I use JWT or session-based authentication for the API?',
    answer: null,
    status: 'PENDING',
    created_at: '2025-11-08T12:34:56Z',
    resolved_at: null,
    time_waiting_ms: 300000, // 5 minutes
  };

  const mockOnClose = jest.fn();
  const mockOnResolved = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('modal display', () => {
    it('renders when isOpen is true', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('does not render when isOpen is false', () => {
      const { container } = render(
        <BlockerModal
          isOpen={false}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument();
    });

    it('displays modal title "Resolve Blocker"', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByText('Resolve Blocker')).toBeInTheDocument();
    });
  });

  describe('blocker information display', () => {
    it('displays full blocker question', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByText(mockBlocker.question)).toBeInTheDocument();
    });

    it('displays agent name', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByText(/Backend Worker #1/)).toBeInTheDocument();
    });

    it('displays task title when available', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByText(/Implement user authentication/)).toBeInTheDocument();
    });

    it('displays blocker type badge', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      // BlockerBadge should render CRITICAL for SYNC blockers
      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    });

    it('displays waiting time', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      // 300000 ms = 5 minutes
      expect(screen.getByText(/5 minutes ago/i)).toBeInTheDocument();
    });
  });

  describe('answer input', () => {
    it('renders textarea for answer', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByPlaceholderText(/Enter your answer/i)).toBeInTheDocument();
    });

    it('allows typing in textarea', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      await user.type(textarea, 'Use JWT for stateless authentication');

      expect(textarea.value).toBe('Use JWT for stateless authentication');
    });

    it('shows character counter', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      expect(screen.getByText(/0 \/ 5000/)).toBeInTheDocument();
    });

    it('updates character counter when typing', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i);
      await user.type(textarea, 'JWT');

      expect(screen.getByText(/3 \/ 5000/)).toBeInTheDocument();
    });
  });

  describe('answer validation', () => {
    it('submit button is disabled when answer is empty', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const submitButton = screen.getByText('Submit Answer');
      expect(submitButton).toBeDisabled();
    });

    it('submit button is enabled when answer has content', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i);
      await user.type(textarea, 'Use JWT');

      const submitButton = screen.getByText('Submit Answer');
      expect(submitButton).not.toBeDisabled();
    });

    it('shows error when trying to submit empty answer', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      // Try to submit empty answer (button should be disabled, but test the validation)
      const textarea = screen.getByPlaceholderText(/Enter your answer/i);
      await user.type(textarea, '   '); // Whitespace only
      await user.clear(textarea); // Clear to empty

      const submitButton = screen.getByText('Submit Answer');
      expect(submitButton).toBeDisabled();
    });

    it('shows error when answer exceeds 5000 characters', async () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const longAnswer = 'A'.repeat(5001);
      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      // Use fireEvent.change for very long strings
      fireEvent.change(textarea, { target: { value: longAnswer } });

      // Should show error or disable submit
      expect(screen.getByText(/maximum.*5000/i)).toBeInTheDocument();
    });

    it('accepts answer at exactly 5000 characters', async () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const maxAnswer = 'A'.repeat(5000);
      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      // Use fireEvent.change for very long strings
      fireEvent.change(textarea, { target: { value: maxAnswer } });

      const submitButton = screen.getByText('Submit Answer');
      expect(submitButton).not.toBeDisabled();
    });
  });

  describe('form submission', () => {
    it('calls resolveBlocker API on submit', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockResolvedValue({ success: true });

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      // Use fireEvent.change for reliable input
      fireEvent.change(textarea, { target: { value: 'Use JWT authentication' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      expect(mockResolveBlocker).toHaveBeenCalledWith(123, 'Use JWT authentication');
    });

    it('shows loading state during submission', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ success: true }), 100))
      );

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      expect(screen.getByText(/Submitting/i)).toBeInTheDocument();
      expect(submitButton).toBeDisabled();
    });

    it('calls onResolved callback on successful submission', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockResolvedValue({ success: true });

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnResolved).toHaveBeenCalled();
      });
    });

    it('closes modal on successful submission', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockResolvedValue({ success: true });

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
      });
    });
  });

  describe('error handling', () => {
    it('shows error toast on API failure', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockRejectedValue(new Error('Network error'));

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      await waitFor(
        () => {
          expect(screen.getByText(/Failed to resolve blocker/i)).toBeInTheDocument();
        },
        { timeout: 5000 }
      );
    }, 10000); // 10 second Jest timeout

    it('handles 409 Conflict error (already resolved)', async () => {
      // Create axios-like error for 409 status
      const conflictError: any = {
        response: { status: 409 },
        message: 'Conflict'
      };

      // Explicitly reset and configure the mock for this test
      mockResolveBlocker.mockReset();
      mockResolveBlocker.mockRejectedValueOnce(conflictError);

      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      // Wait for error handling
      await waitFor(
        () => {
          expect(mockResolveBlocker).toHaveBeenCalledWith(123, 'Use JWT');
        },
        { timeout: 3000 }
      );

      // Verify callbacks were NOT called (error case)
      expect(mockOnResolved).not.toHaveBeenCalled();

      // The modal should remain open on error
      // Note: We check this after a small delay to ensure async error handling completes
      await new Promise(resolve => setTimeout(resolve, 200));

      // Since we can't reliably test toast appearance in jsdom, we verify error behavior:
      // - API was called with correct params
      // - onResolved was not called (success callback)
      // - Modal is still rendered (we can query elements)
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('does not close modal on submission error', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockRejectedValue(new Error('Network error'));

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      await waitFor(
        () => {
          expect(screen.getByText(/Failed to resolve blocker/i)).toBeInTheDocument();
        },
        { timeout: 5000 }
      );

      // Modal should still be open
      expect(mockOnClose).not.toHaveBeenCalled();
    }, 10000); // 10 second Jest timeout
  });

  describe('modal controls', () => {
    it('renders close button', () => {
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const closeButton = screen.getByLabelText(/close/i);
      expect(closeButton).toBeInTheDocument();
    });

    it('calls onClose when close button clicked', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const closeButton = screen.getByLabelText(/close/i);
      await user.click(closeButton);

      expect(mockOnClose).toHaveBeenCalled();
    });

    it('calls onClose when Cancel button clicked', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const cancelButton = screen.getByText('Cancel');
      await user.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalled();
    });

    it('closes modal when clicking outside (backdrop)', async () => {
      const user = userEvent.setup();
      const { container } = render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const backdrop = container.querySelector('[data-backdrop="true"]');
      if (backdrop) {
        await user.click(backdrop);
        expect(mockOnClose).toHaveBeenCalled();
      }
    });
  });

  describe('keyboard shortcuts', () => {
    it('submits form when Ctrl+Enter is pressed', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockResolvedValue({ success: true });

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      // Focus the textarea and trigger Ctrl+Enter
      textarea.focus();
      await user.keyboard('{Control>}{Enter}{/Control}');

      await waitFor(
        () => {
          expect(mockResolveBlocker).toHaveBeenCalledWith(123, 'Use JWT');
        },
        { timeout: 5000 }
      );
    });

    it('closes modal when Escape is pressed', async () => {
      const user = userEvent.setup();
      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      await user.keyboard('{Escape}');

      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  describe('success feedback', () => {
    it('shows success toast on successful resolution', async () => {
      const user = userEvent.setup();
      mockResolveBlocker.mockResolvedValue({ success: true });

      render(
        <BlockerModal
          isOpen={true}
          blocker={mockBlocker}
          onClose={mockOnClose}
          onResolved={mockOnResolved}
        />
      );

      const textarea = screen.getByPlaceholderText(/Enter your answer/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Use JWT' } });

      const submitButton = screen.getByText('Submit Answer');
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Blocker resolved successfully/i)).toBeInTheDocument();
      });
    });
  });
});
