/**
 * Tests for PRMergeDialog Component
 * TDD: Tests written first to define expected behavior
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PRMergeDialog from '@/components/pr/PRMergeDialog';
import type { PullRequest } from '@/types/pullRequest';

// Mock PR data
const mockPR: PullRequest = {
  id: 1,
  pr_number: 42,
  title: 'Add user authentication',
  body: 'Implements OAuth 2.0 flow',
  status: 'open',
  head_branch: 'feature/auth',
  base_branch: 'main',
  pr_url: 'https://github.com/org/repo/pull/42',
  issue_id: null,
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T12:00:00Z',
  merged_at: null,
  merge_commit_sha: null,
  files_changed: 15,
  additions: 450,
  deletions: 50,
  ci_status: 'success',
  review_status: 'approved',
};

// Mock the API
jest.mock('@/lib/api', () => ({
  pullRequestsApi: {
    merge: jest.fn().mockResolvedValue({
      data: {
        merged: true,
        merge_commit_sha: 'def456',
      },
    }),
  },
}));

describe('PRMergeDialog', () => {
  const defaultProps = {
    pr: mockPR,
    projectId: 1,
    isOpen: true,
    onClose: jest.fn(),
    onSuccess: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render the dialog when open', () => {
      render(<PRMergeDialog {...defaultProps} />);

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/merge pull request/i)).toBeInTheDocument();
    });

    it('should not render when closed', () => {
      render(<PRMergeDialog {...defaultProps} isOpen={false} />);

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('should display PR information', () => {
      render(<PRMergeDialog {...defaultProps} />);

      expect(screen.getByText(/#42/)).toBeInTheDocument();
      expect(screen.getByText('Add user authentication')).toBeInTheDocument();
      expect(screen.getByText(/feature\/auth/)).toBeInTheDocument();
      // Use getAllByText since 'main' appears multiple times (in branch info and description)
      const mainElements = screen.getAllByText(/main/);
      expect(mainElements.length).toBeGreaterThan(0);
    });
  });

  describe('Merge Method Selection', () => {
    it('should display all merge method options', () => {
      render(<PRMergeDialog {...defaultProps} />);

      expect(screen.getByLabelText(/squash and merge/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/create merge commit/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/rebase and merge/i)).toBeInTheDocument();
    });

    it('should have squash selected by default', () => {
      render(<PRMergeDialog {...defaultProps} />);

      const squashRadio = screen.getByLabelText(/squash and merge/i);
      expect(squashRadio).toBeChecked();
    });

    it('should allow changing merge method', async () => {
      const user = userEvent.setup();
      render(<PRMergeDialog {...defaultProps} />);

      const rebaseRadio = screen.getByLabelText(/rebase and merge/i);
      await user.click(rebaseRadio);

      expect(rebaseRadio).toBeChecked();
    });
  });

  describe('Delete Branch Option', () => {
    it('should have delete branch checkbox checked by default', () => {
      render(<PRMergeDialog {...defaultProps} />);

      const checkbox = screen.getByLabelText(/delete branch after merge/i);
      expect(checkbox).toBeChecked();
    });

    it('should allow unchecking delete branch option', async () => {
      const user = userEvent.setup();
      render(<PRMergeDialog {...defaultProps} />);

      const checkbox = screen.getByLabelText(/delete branch after merge/i);
      await user.click(checkbox);

      expect(checkbox).not.toBeChecked();
    });
  });

  describe('Form Submission', () => {
    it('should call API with selected options on confirm', async () => {
      const user = userEvent.setup();
      const { pullRequestsApi } = jest.requireMock('@/lib/api');

      render(<PRMergeDialog {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: /confirm merge/i });
      await user.click(confirmButton);

      await waitFor(() => {
        expect(pullRequestsApi.merge).toHaveBeenCalledWith(1, 42, {
          method: 'squash',
          delete_branch: true,
        });
      });
    });

    it('should call onSuccess after successful merge', async () => {
      const user = userEvent.setup();
      render(<PRMergeDialog {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: /confirm merge/i });
      await user.click(confirmButton);

      await waitFor(() => {
        expect(defaultProps.onSuccess).toHaveBeenCalled();
      });
    });

    it('should close dialog after successful merge', async () => {
      const user = userEvent.setup();
      render(<PRMergeDialog {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: /confirm merge/i });
      await user.click(confirmButton);

      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled();
      });
    });

    it('should show loading state during submission', async () => {
      // Make the API call take time to show loading state
      const { pullRequestsApi } = jest.requireMock('@/lib/api');
      let resolvePromise: (value: unknown) => void;
      pullRequestsApi.merge.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve;
          })
      );

      const user = userEvent.setup();
      render(<PRMergeDialog {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: /confirm merge/i });
      await user.click(confirmButton);

      // Button should show loading state
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /merging/i })).toBeInTheDocument();
      });

      // Cleanup: resolve the promise
      resolvePromise!({ data: { merged: true, merge_commit_sha: 'def456' } });
    });
  });

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      const user = userEvent.setup();
      const { pullRequestsApi } = jest.requireMock('@/lib/api');
      pullRequestsApi.merge.mockRejectedValueOnce(new Error('Merge conflicts detected'));

      render(<PRMergeDialog {...defaultProps} />);

      const confirmButton = screen.getByRole('button', { name: /confirm merge/i });
      await user.click(confirmButton);

      await waitFor(() => {
        expect(screen.getByText(/merge conflicts detected/i)).toBeInTheDocument();
      });
    });
  });

  describe('Cancel Action', () => {
    it('should call onClose when cancel button is clicked', async () => {
      const user = userEvent.setup();
      render(<PRMergeDialog {...defaultProps} />);

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(defaultProps.onClose).toHaveBeenCalled();
    });
  });

  describe('Warning Message', () => {
    it('should display warning about irreversibility', () => {
      render(<PRMergeDialog {...defaultProps} />);

      expect(screen.getByText(/this action cannot be undone/i)).toBeInTheDocument();
    });
  });
});
