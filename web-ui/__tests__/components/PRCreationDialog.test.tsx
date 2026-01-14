/**
 * Tests for PRCreationDialog Component
 * TDD: Tests written first to define expected behavior
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PRCreationDialog from '@/components/pr/PRCreationDialog';

// Mock the API
jest.mock('@/lib/api', () => ({
  pullRequestsApi: {
    create: jest.fn().mockResolvedValue({
      data: {
        pr_id: 1,
        pr_number: 42,
        pr_url: 'https://github.com/org/repo/pull/42',
        status: 'open',
      },
    }),
  },
}));

// Mock git API for branch list
jest.mock('@/api/git', () => ({
  gitApi: {
    getBranches: jest.fn().mockResolvedValue({
      data: {
        branches: [
          { id: 1, branch_name: 'feature/auth', status: 'active' },
          { id: 2, branch_name: 'feature/dashboard', status: 'active' },
          { id: 3, branch_name: 'main', status: 'active' },
        ],
      },
    }),
  },
}));

describe('PRCreationDialog', () => {
  const defaultProps = {
    projectId: 1,
    isOpen: true,
    onClose: jest.fn(),
    onSuccess: jest.fn(),
    defaultBranch: 'feature/auth',
    defaultTitle: 'Add authentication feature',
    defaultDescription: 'Implements OAuth 2.0 login flow',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the dialog when open', () => {
      render(<PRCreationDialog {...defaultProps} />);

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/create pull request/i)).toBeInTheDocument();
    });

    it('should not render when closed', () => {
      render(<PRCreationDialog {...defaultProps} isOpen={false} />);

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('should pre-fill form with default values', () => {
      render(<PRCreationDialog {...defaultProps} />);

      expect(screen.getByDisplayValue('Add authentication feature')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Implements OAuth 2.0 login flow')).toBeInTheDocument();
    });
  });

  describe('Form Fields', () => {
    it('should have title input field', () => {
      render(<PRCreationDialog {...defaultProps} />);

      const titleInput = screen.getByLabelText(/title/i);
      expect(titleInput).toBeInTheDocument();
      expect(titleInput).toHaveAttribute('type', 'text');
    });

    it('should have description textarea', () => {
      render(<PRCreationDialog {...defaultProps} />);

      const descriptionInput = screen.getByLabelText(/description/i);
      expect(descriptionInput).toBeInTheDocument();
      expect(descriptionInput.tagName.toLowerCase()).toBe('textarea');
    });

    it('should have branch selector', () => {
      render(<PRCreationDialog {...defaultProps} />);

      expect(screen.getByLabelText(/source branch/i)).toBeInTheDocument();
    });

    it('should have base branch selector with main as default', () => {
      render(<PRCreationDialog {...defaultProps} />);

      const baseBranchSelect = screen.getByLabelText(/target branch/i);
      expect(baseBranchSelect).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('should require title', async () => {
      const user = userEvent.setup();
      render(<PRCreationDialog {...defaultProps} defaultTitle="" />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      expect(screen.getByText(/title is required/i)).toBeInTheDocument();
    });

    it('should require branch selection', async () => {
      const user = userEvent.setup();
      render(<PRCreationDialog {...defaultProps} defaultBranch="" />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      expect(screen.getByText(/branch is required/i)).toBeInTheDocument();
    });
  });

  describe('Form Submission', () => {
    it('should call API with form data on submit', async () => {
      const user = userEvent.setup();
      const { pullRequestsApi } = jest.requireMock('@/lib/api');

      render(<PRCreationDialog {...defaultProps} />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(pullRequestsApi.create).toHaveBeenCalledWith(1, {
          branch: 'feature/auth',
          title: 'Add authentication feature',
          body: 'Implements OAuth 2.0 login flow',
          base: 'main',
        });
      });
    });

    it('should call onSuccess after successful creation', async () => {
      const user = userEvent.setup();
      render(<PRCreationDialog {...defaultProps} />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(defaultProps.onSuccess).toHaveBeenCalled();
      });
    });

    it('should close dialog after successful creation', async () => {
      const user = userEvent.setup();
      render(<PRCreationDialog {...defaultProps} />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled();
      });
    });

    it('should show loading state during submission', async () => {
      const user = userEvent.setup();
      render(<PRCreationDialog {...defaultProps} />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      // Button should show loading state
      expect(screen.getByRole('button', { name: /creating/i })).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      const user = userEvent.setup();
      const { pullRequestsApi } = jest.requireMock('@/lib/api');
      pullRequestsApi.create.mockRejectedValueOnce(new Error('Branch already has an open PR'));

      render(<PRCreationDialog {...defaultProps} />);

      const submitButton = screen.getByRole('button', { name: /create/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/branch already has an open pr/i)).toBeInTheDocument();
      });
    });
  });

  describe('Cancel Action', () => {
    it('should call onClose when cancel button is clicked', async () => {
      const user = userEvent.setup();
      render(<PRCreationDialog {...defaultProps} />);

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(defaultProps.onClose).toHaveBeenCalled();
    });

    it('should reset form when reopened', async () => {
      const user = userEvent.setup();
      const { rerender } = render(<PRCreationDialog {...defaultProps} />);

      // Modify title
      const titleInput = screen.getByLabelText(/title/i);
      await user.clear(titleInput);
      await user.type(titleInput, 'Modified title');

      // Close and reopen
      rerender(<PRCreationDialog {...defaultProps} isOpen={false} />);
      rerender(<PRCreationDialog {...defaultProps} isOpen={true} />);

      // Should have original default value
      expect(screen.getByDisplayValue('Add authentication feature')).toBeInTheDocument();
    });
  });
});
