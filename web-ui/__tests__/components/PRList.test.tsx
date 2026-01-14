/**
 * Tests for PRList Component
 * TDD: Tests written first to define expected behavior
 *
 * PRList displays pull requests for a project with:
 * - List view with status badges
 * - Status filtering (all, open, merged, closed)
 * - Create PR button
 * - Quick actions (view, merge, close)
 * - Real-time updates via WebSocket
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PRList from '@/components/pr/PRList';
import type { PullRequest, PRStatus } from '@/types/pullRequest';

// Mock Hugeicons to prevent import issues in tests
jest.mock('@hugeicons/react', () => ({
  GitPullRequestIcon: () => <span data-testid="icon-git-pr" />,
  CheckmarkCircle01Icon: () => <span data-testid="icon-checkmark" />,
  Cancel01Icon: () => <span data-testid="icon-cancel" />,
  Loading03Icon: () => <span data-testid="icon-loading" />,
  AlertCircleIcon: () => <span data-testid="icon-alert" />,
  GitBranchIcon: () => <span data-testid="icon-branch" />,
  Link01Icon: () => <span data-testid="icon-link" />,
  Add01Icon: () => <span data-testid="icon-add" />,
  ArrowRight01Icon: () => <span data-testid="icon-arrow" />,
  CheckmarkSquare01Icon: () => <span data-testid="icon-checkmark-square" />,
  Cancel02Icon: () => <span data-testid="icon-cancel2" />,
  Time01Icon: () => <span data-testid="icon-time" />,
}));

// Mock data
const mockPRs: PullRequest[] = [
  {
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
    author: 'developer',
  },
  {
    id: 2,
    pr_number: 41,
    title: 'Fix login bug',
    body: 'Fixes issue with session timeout',
    status: 'merged',
    head_branch: 'fix/login-bug',
    base_branch: 'main',
    pr_url: 'https://github.com/org/repo/pull/41',
    issue_id: 5,
    created_at: '2024-01-14T09:00:00Z',
    updated_at: '2024-01-14T15:00:00Z',
    merged_at: '2024-01-14T15:00:00Z',
    merge_commit_sha: 'abc123',
    files_changed: 3,
    additions: 25,
    deletions: 10,
    ci_status: 'success',
    review_status: 'approved',
    author: 'developer',
  },
  {
    id: 3,
    pr_number: 40,
    title: 'Refactor database layer',
    body: 'Cleanup and optimization',
    status: 'closed',
    head_branch: 'refactor/db',
    base_branch: 'main',
    pr_url: 'https://github.com/org/repo/pull/40',
    issue_id: null,
    created_at: '2024-01-13T08:00:00Z',
    updated_at: '2024-01-13T16:00:00Z',
    merged_at: null,
    merge_commit_sha: null,
    files_changed: 20,
    additions: 200,
    deletions: 300,
    ci_status: 'failure',
    review_status: 'changes_requested',
    author: 'developer',
  },
];

// SWR mock state
let mockSWRData: { prs: PullRequest[]; total: number } | null = { prs: mockPRs, total: 3 };
let mockSWRError: Error | null = null;
let mockSWRIsLoading = false;

// Mock SWR with configurable state
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: mockSWRData,
    error: mockSWRError,
    isLoading: mockSWRIsLoading,
    mutate: jest.fn(),
  })),
}));

// Mock WebSocket client
const mockOnMessage = jest.fn();
const mockUnsubscribe = jest.fn();
jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: () => ({
    onMessage: (handler: (msg: unknown) => void) => {
      mockOnMessage.mockImplementation(handler);
      return mockUnsubscribe;
    },
  }),
}));

// Mock the API
jest.mock('@/lib/api', () => ({
  pullRequestsApi: {
    list: jest.fn().mockResolvedValue({ data: { prs: [], total: 0 } }),
  },
}));

describe('PRList', () => {
  const defaultProps = {
    projectId: 1,
    onCreatePR: jest.fn(),
    onViewPR: jest.fn(),
    onMergePR: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Reset mock state to defaults
    mockSWRData = { prs: mockPRs, total: 3 };
    mockSWRError = null;
    mockSWRIsLoading = false;
  });

  describe('Rendering', () => {
    it('should render the PR list with all PRs', () => {
      render(<PRList {...defaultProps} />);

      expect(screen.getByText('Add user authentication')).toBeInTheDocument();
      expect(screen.getByText('Fix login bug')).toBeInTheDocument();
      expect(screen.getByText('Refactor database layer')).toBeInTheDocument();
    });

    it('should display PR numbers', () => {
      render(<PRList {...defaultProps} />);

      expect(screen.getByText('#42')).toBeInTheDocument();
      expect(screen.getByText('#41')).toBeInTheDocument();
      expect(screen.getByText('#40')).toBeInTheDocument();
    });

    it('should display status badges', () => {
      render(<PRList {...defaultProps} />);

      const prCards = screen.getAllByTestId('pr-card');
      expect(prCards.length).toBe(3);

      // Check status badges exist
      expect(screen.getByText('open')).toBeInTheDocument();
      expect(screen.getByText('merged')).toBeInTheDocument();
      expect(screen.getByText('closed')).toBeInTheDocument();
    });

    it('should display branch information', () => {
      render(<PRList {...defaultProps} />);

      expect(screen.getByText('feature/auth')).toBeInTheDocument();
      expect(screen.getByText('fix/login-bug')).toBeInTheDocument();
    });

    it('should display file change counts', () => {
      render(<PRList {...defaultProps} />);

      expect(screen.getByText(/15 files/)).toBeInTheDocument();
      expect(screen.getByText(/\+450/)).toBeInTheDocument();
      expect(screen.getByText(/-50/)).toBeInTheDocument();
    });

    it('should display Create PR button', () => {
      render(<PRList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /create pr/i })).toBeInTheDocument();
    });
  });

  describe('Filtering', () => {
    it('should display filter buttons', () => {
      render(<PRList {...defaultProps} />);

      expect(screen.getByRole('tab', { name: /all/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /open/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /merged/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /closed/i })).toBeInTheDocument();
    });

    it('should have "All" filter selected by default', () => {
      render(<PRList {...defaultProps} />);

      const allButton = screen.getByRole('tab', { name: /all/i });
      expect(allButton).toHaveAttribute('data-active', 'true');
    });

    it('should call filter change handler when filter is clicked', async () => {
      const user = userEvent.setup();
      render(<PRList {...defaultProps} />);

      const openButton = screen.getByRole('tab', { name: /^open$/i });
      await user.click(openButton);

      expect(openButton).toHaveAttribute('data-active', 'true');
    });
  });

  describe('Actions', () => {
    it('should call onCreatePR when Create PR button is clicked', async () => {
      const user = userEvent.setup();
      render(<PRList {...defaultProps} />);

      const createButton = screen.getByRole('button', { name: /create pr/i });
      await user.click(createButton);

      expect(defaultProps.onCreatePR).toHaveBeenCalled();
    });

    it('should call onViewPR when View button is clicked', async () => {
      const user = userEvent.setup();
      render(<PRList {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /view/i });
      await user.click(viewButtons[0]);

      expect(defaultProps.onViewPR).toHaveBeenCalledWith(42);
    });

    it('should show Merge button only for open PRs', () => {
      render(<PRList {...defaultProps} />);

      const prCards = screen.getAllByTestId('pr-card');

      // First PR (open) should have Merge button
      const openPRCard = prCards[0];
      expect(within(openPRCard).getByRole('button', { name: /merge/i })).toBeInTheDocument();

      // Second PR (merged) should not have Merge button
      const mergedPRCard = prCards[1];
      expect(within(mergedPRCard).queryByRole('button', { name: /merge/i })).not.toBeInTheDocument();
    });

    it('should call onMergePR when Merge button is clicked', async () => {
      const user = userEvent.setup();
      render(<PRList {...defaultProps} />);

      const mergeButton = screen.getByRole('button', { name: /merge/i });
      await user.click(mergeButton);

      expect(defaultProps.onMergePR).toHaveBeenCalledWith(mockPRs[0]);
    });
  });

  describe('CI/Review Status', () => {
    it('should display CI status indicator', () => {
      render(<PRList {...defaultProps} />);

      // Should show success indicator for first PR
      const prCards = screen.getAllByTestId('pr-card');
      expect(within(prCards[0]).getByTestId('ci-status')).toHaveAttribute('data-status', 'success');
    });

    it('should display review status indicator', () => {
      render(<PRList {...defaultProps} />);

      const prCards = screen.getAllByTestId('pr-card');
      expect(within(prCards[0]).getByTestId('review-status')).toHaveAttribute('data-status', 'approved');
    });
  });

  describe('Empty State', () => {
    it('should display empty state when no PRs exist', () => {
      mockSWRData = { prs: [], total: 0 };
      render(<PRList {...defaultProps} />);

      expect(screen.getByText(/no pull requests/i)).toBeInTheDocument();
    });

    it('should still show Create PR button in empty state', () => {
      mockSWRData = { prs: [], total: 0 };
      render(<PRList {...defaultProps} />);

      // There should be at least one Create PR button
      const createButtons = screen.getAllByRole('button', { name: /create pr/i });
      expect(createButtons.length).toBeGreaterThan(0);
    });
  });

  describe('Loading State', () => {
    it('should display loading skeleton when loading', () => {
      mockSWRData = null;
      mockSWRIsLoading = true;
      render(<PRList {...defaultProps} />);

      expect(screen.getByTestId('pr-list-loading')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('should display error message when fetch fails', () => {
      mockSWRData = null;
      mockSWRError = new Error('Failed to load PRs');
      render(<PRList {...defaultProps} />);

      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });

    it('should show retry button on error', () => {
      mockSWRData = null;
      mockSWRError = new Error('Failed to load PRs');
      render(<PRList {...defaultProps} />);

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  describe('External Links', () => {
    it('should render GitHub link with correct URL', () => {
      render(<PRList {...defaultProps} />);

      const githubLinks = screen.getAllByRole('link', { name: /github/i });
      expect(githubLinks[0]).toHaveAttribute('href', 'https://github.com/org/repo/pull/42');
      expect(githubLinks[0]).toHaveAttribute('target', '_blank');
      expect(githubLinks[0]).toHaveAttribute('rel', 'noopener noreferrer');
    });
  });
});
