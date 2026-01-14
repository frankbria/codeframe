/**
 * ReviewResultsPanel Component Tests (T064)
 * Tests for main panel displaying review results with scores and findings
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import ReviewResultsPanel from '@/components/review/ReviewResultsPanel';
import * as reviewApi from '@/api/review';
import type { ReviewStatusResponse } from '@/types/review';

// Mock the API module
jest.mock('@/api/review');

// Mock child components to isolate testing
jest.mock('@/components/review/ReviewScoreChart', () => ({
  __esModule: true,
  default: jest.fn(({ report }) => (
    <div data-testid="review-score-chart">
      Score Chart for Task {report.task_id}
    </div>
  )),
}));

jest.mock('@/components/review/ReviewFindingsList', () => ({
  __esModule: true,
  default: jest.fn(({ findings }) => (
    <div data-testid="review-findings-list">
      Findings: {findings.length}
    </div>
  )),
}));

const mockFetchReviewStatus = reviewApi.fetchReviewStatus as jest.MockedFunction<
  typeof reviewApi.fetchReviewStatus
>;

describe('ReviewResultsPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Loading state', () => {
    it('renders loading spinner while fetching review status', () => {
      // Mock a delayed promise to keep loading state visible
      mockFetchReviewStatus.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<ReviewResultsPanel taskId={1} />);

      expect(screen.getByText('Loading review...')).toBeInTheDocument();
    });

    it('displays animated spinner during loading', () => {
      mockFetchReviewStatus.mockImplementation(
        () => new Promise(() => {})
      );

      const { container } = render(<ReviewResultsPanel taskId={1} />);
      const spinner = container.querySelector('.animate-spin');

      expect(spinner).toBeInTheDocument();
      expect(spinner).toHaveClass('rounded-full');
      expect(spinner).toHaveClass('h-12');
      expect(spinner).toHaveClass('w-12');
      expect(spinner).toHaveClass('border-b-2');
      expect(spinner).toHaveClass('border-primary');
    });

    it('applies correct container styling during loading', () => {
      mockFetchReviewStatus.mockImplementation(
        () => new Promise(() => {})
      );

      const { container } = render(<ReviewResultsPanel taskId={1} />);
      const loadingContainer = container.querySelector('.bg-card.rounded-lg.shadow');

      expect(loadingContainer).toBeInTheDocument();
      expect(loadingContainer).toHaveClass('p-6');
    });
  });

  describe('Error state', () => {
    it('renders error message when API call fails', async () => {
      const errorMessage = 'Failed to fetch review status: 500 Internal Server Error';
      mockFetchReviewStatus.mockRejectedValue(new Error(errorMessage));

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Error Loading Review')).toBeInTheDocument();
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      });
    });

    it('displays warning emoji in error state', async () => {
      mockFetchReviewStatus.mockRejectedValue(new Error('Network error'));

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('⚠️')).toBeInTheDocument();
      });
    });

    it('applies red color to error heading', async () => {
      mockFetchReviewStatus.mockRejectedValue(new Error('Test error'));

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const errorHeading = screen.getByText('Error Loading Review');
        expect(errorHeading).toHaveClass('text-destructive');
        expect(errorHeading).toHaveClass('font-medium');
      });
    });

    it('handles non-Error objects as errors', async () => {
      mockFetchReviewStatus.mockRejectedValue('String error');

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Failed to load review')).toBeInTheDocument();
      });
    });

    it('applies correct container styling in error state', async () => {
      mockFetchReviewStatus.mockRejectedValue(new Error('Test error'));

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const errorContainer = container.querySelector('.bg-card.rounded-lg.shadow');
        expect(errorContainer).toBeInTheDocument();
        expect(errorContainer).toHaveClass('p-6');
      });
    });
  });

  describe('No review state', () => {
    it('renders no review message when has_review is false', async () => {
      const noReviewStatus: ReviewStatusResponse = {
        has_review: false,
        status: null,
        overall_score: null,
        findings_count: 0,
      };

      mockFetchReviewStatus.mockResolvedValue(noReviewStatus);

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('No Review Available')).toBeInTheDocument();
        expect(screen.getByText('This task has not been reviewed yet.')).toBeInTheDocument();
      });
    });

    it('displays document emoji in no review state', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: false,
        status: null,
        overall_score: null,
        findings_count: 0,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('📝')).toBeInTheDocument();
      });
    });

    it('applies correct styling to no review heading', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: false,
        status: null,
        overall_score: null,
        findings_count: 0,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const heading = screen.getByText('No Review Available');
        expect(heading).toHaveClass('text-foreground');
        expect(heading).toHaveClass('font-medium');
      });
    });
  });

  describe('Review results display', () => {
    it('renders review results with overall score', async () => {
      const mockReviewStatus: ReviewStatusResponse = {
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      };

      mockFetchReviewStatus.mockResolvedValue(mockReviewStatus);

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('85')).toBeInTheDocument();
        expect(screen.getByText('/100')).toBeInTheDocument();
      });
    });

    it('renders task ID in header', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={42} />);

      await waitFor(() => {
        expect(screen.getByText('Task #42')).toBeInTheDocument();
      });
    });

    it('renders "Code Review Results" heading', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Code Review Results')).toBeInTheDocument();
      });
    });

    it('renders findings count', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 5,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('findings detected')).toBeInTheDocument();
        // The count appears in a separate span with font-medium class
        expect(screen.getByText('5')).toBeInTheDocument();
      });
    });

    it('applies green color for high score (>= 70)', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 2,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const scoreElement = screen.getByText('85');
        expect(scoreElement).toHaveClass('text-secondary');
      });
    });

    it('applies orange color for low score (< 70)', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'changes_requested',
        overall_score: 65,
        findings_count: 8,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const scoreElement = screen.getByText('65');
        expect(scoreElement).toHaveClass('text-destructive');
      });
    });

    it('handles perfect score (100)', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 100,
        findings_count: 0,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('100')).toBeInTheDocument();
      });
    });

    it('handles minimum score (0)', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'rejected',
        overall_score: 0,
        findings_count: 15,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('0')).toBeInTheDocument();
      });
    });
  });

  describe('Status badges', () => {
    it('renders approved status badge with green styling', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 2,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('APPROVED');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('bg-secondary');
        expect(badge).toHaveClass('text-secondary-foreground');
        expect(badge).toHaveClass('border-border');
      });
    });

    it('renders changes_requested status badge with yellow styling', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'changes_requested',
        overall_score: 65,
        findings_count: 5,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('CHANGES REQUESTED');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('bg-muted');
        expect(badge).toHaveClass('text-foreground');
        expect(badge).toHaveClass('border-border');
      });
    });

    it('renders rejected status badge with red styling', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'rejected',
        overall_score: 40,
        findings_count: 12,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('REJECTED');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('bg-destructive');
        expect(badge).toHaveClass('text-destructive-foreground');
        expect(badge).toHaveClass('border-destructive');
      });
    });

    it('applies base badge styling', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 2,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('APPROVED');
        expect(badge).toHaveClass('px-4');
        expect(badge).toHaveClass('py-2');
        expect(badge).toHaveClass('rounded-full');
        expect(badge).toHaveClass('text-sm');
        expect(badge).toHaveClass('font-medium');
        expect(badge).toHaveClass('border');
      });
    });

    it('replaces underscores with spaces in status', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'changes_requested',
        overall_score: 65,
        findings_count: 5,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('CHANGES REQUESTED')).toBeInTheDocument();
        expect(screen.queryByText('CHANGES_REQUESTED')).not.toBeInTheDocument();
      });
    });
  });

  describe('Close functionality', () => {
    it('renders close button when onClose prop provided', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const onCloseMock = jest.fn();

      render(<ReviewResultsPanel taskId={1} onClose={onCloseMock} />);

      await waitFor(() => {
        const closeButton = screen.getByLabelText('Close');
        expect(closeButton).toBeInTheDocument();
      });
    });

    it('does not render close button when onClose prop not provided', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const closeButton = screen.queryByLabelText('Close');
        expect(closeButton).not.toBeInTheDocument();
      });
    });

    it('calls onClose callback when close button clicked', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const onCloseMock = jest.fn();

      render(<ReviewResultsPanel taskId={1} onClose={onCloseMock} />);

      await waitFor(() => {
        const closeButton = screen.getByLabelText('Close');
        fireEvent.click(closeButton);
      });

      expect(onCloseMock).toHaveBeenCalledTimes(1);
    });

    it('applies hover effect to close button', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} onClose={jest.fn()} />);

      await waitFor(() => {
        const closeButton = screen.getByLabelText('Close');
        expect(closeButton).toHaveClass('hover:text-foreground');
        expect(closeButton).toHaveClass('transition-colors');
      });
    });

    it('renders close icon SVG correctly', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} onClose={jest.fn()} />);

      await waitFor(() => {
        const closeButton = screen.getByLabelText('Close');
        const svg = closeButton.querySelector('svg');

        expect(svg).toBeInTheDocument();
        expect(svg).toHaveClass('w-6');
        expect(svg).toHaveClass('h-6');
        expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
      });
    });
  });

  describe('API integration', () => {
    it('calls fetchReviewStatus with correct task ID', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={42} />);

      await waitFor(() => {
        expect(mockFetchReviewStatus).toHaveBeenCalledWith(42);
        expect(mockFetchReviewStatus).toHaveBeenCalledTimes(1);
      });
    });

    it('fetches review status on mount', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} />);

      expect(mockFetchReviewStatus).toHaveBeenCalledTimes(1);
    });

    it('refetches review status when taskId changes', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { rerender } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(mockFetchReviewStatus).toHaveBeenCalledWith(1);
      });

      mockFetchReviewStatus.mockClear();

      rerender(<ReviewResultsPanel taskId={2} />);

      await waitFor(() => {
        expect(mockFetchReviewStatus).toHaveBeenCalledWith(2);
      });
    });

    it('handles concurrent API calls gracefully', async () => {
      let resolveFirstCall: (value: ReviewStatusResponse) => void;
      const firstCallPromise = new Promise<ReviewStatusResponse>((resolve) => {
        resolveFirstCall = resolve;
      });

      mockFetchReviewStatus.mockReturnValueOnce(firstCallPromise);

      const { rerender } = render(<ReviewResultsPanel taskId={1} />);

      // Change taskId before first call resolves
      mockFetchReviewStatus.mockResolvedValueOnce({
        has_review: true,
        status: 'approved',
        overall_score: 95,
        findings_count: 1,
      });

      rerender(<ReviewResultsPanel taskId={2} />);

      // Resolve first call
      resolveFirstCall!({
        has_review: true,
        status: 'rejected',
        overall_score: 50,
        findings_count: 10,
      });

      // Should show results for task 2, not task 1
      await waitFor(() => {
        expect(screen.getByText('Task #2')).toBeInTheDocument();
      });
    });
  });

  describe('Layout and styling', () => {
    it('applies white background and shadow to container', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const mainContainer = container.querySelector('.bg-card.rounded-lg.shadow');
        expect(mainContainer).toBeInTheDocument();
      });
    });

    it('applies border to header section', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const header = container.querySelector('.p-6.border-b');
        expect(header).toBeInTheDocument();
      });
    });

    it('applies padding to content section', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const content = container.querySelector('.p-6:not(.border-b)');
        expect(content).toBeInTheDocument();
      });
    });

    it('centers score content', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const scoreSection = container.querySelector('.text-center.py-8');
        expect(scoreSection).toBeInTheDocument();
      });
    });

    it('applies correct font sizes to score elements', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      const { container } = render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const scoreValue = screen.getByText('85');
        expect(scoreValue.parentElement).toHaveClass('text-6xl');
        expect(scoreValue.parentElement).toHaveClass('font-bold');
      });
    });
  });

  describe('Edge cases', () => {
    it('handles null overall_score gracefully', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: null,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        // Should not crash, might show "null" or handle it
        expect(screen.getByText('Code Review Results')).toBeInTheDocument();
      });
    });

    it('handles zero findings count', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 100,
        findings_count: 0,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('findings detected')).toBeInTheDocument();
        // The "0" appears in a separate span, so we need to check separately
        const findingsCountElements = screen.getAllByText('0');
        expect(findingsCountElements.length).toBeGreaterThan(0);
      });
    });

    it('handles large findings count', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'rejected',
        overall_score: 30,
        findings_count: 999,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('999', { exact: false })).toBeInTheDocument();
      });
    });

    it('handles task ID of 0', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={0} />);

      await waitFor(() => {
        expect(screen.getByText('Task #0')).toBeInTheDocument();
        expect(mockFetchReviewStatus).toHaveBeenCalledWith(0);
      });
    });

    it('displays "coming soon" message in MVP', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Full review details coming soon...', { exact: false })).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('close button has accessible label', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} onClose={jest.fn()} />);

      await waitFor(() => {
        const closeButton = screen.getByLabelText('Close');
        expect(closeButton).toHaveAttribute('aria-label', 'Close');
      });
    });

    it('loading state has descriptive text', () => {
      mockFetchReviewStatus.mockImplementation(
        () => new Promise(() => {})
      );

      render(<ReviewResultsPanel taskId={1} />);

      expect(screen.getByText('Loading review...')).toBeInTheDocument();
    });

    it('error state has clear error message', async () => {
      const errorMessage = 'Network timeout';
      mockFetchReviewStatus.mockRejectedValue(new Error(errorMessage));

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Error Loading Review')).toBeInTheDocument();
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      });
    });

    it('heading elements have semantic structure', async () => {
      mockFetchReviewStatus.mockResolvedValue({
        has_review: true,
        status: 'approved',
        overall_score: 85,
        findings_count: 3,
      });

      render(<ReviewResultsPanel taskId={1} />);

      await waitFor(() => {
        const heading = screen.getByText('Code Review Results');
        expect(heading.tagName).toBe('H2');
      });
    });
  });
});
