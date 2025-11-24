/**
 * ReviewSummary Component Tests (Sprint 10 Phase 2 - T041)
 *
 * Test coverage:
 * - Rendering summary statistics
 * - Blocking indicator for critical/high findings
 * - Success banner for clean code
 * - Empty state (no review data)
 * - Loading state
 * - Error handling
 * - Severity and category breakdowns
 */

import { render, screen } from '@testing-library/react';
import { ReviewSummary } from '@/components/reviews/ReviewSummary';
import {
  mockReviewResultBlocking,
  mockReviewResultNonBlocking,
  mockReviewResultEmpty,
} from '../fixtures/reviews';

describe('ReviewSummary', () => {
  describe('loading state', () => {
    it('renders loading state when loading is true', () => {
      render(<ReviewSummary reviewResult={null} loading={true} />);
      expect(screen.getByText('Loading summary...')).toBeInTheDocument();
    });

    it('does not render summary when loading', () => {
      render(
        <ReviewSummary reviewResult={mockReviewResultBlocking} loading={true} />
      );
      expect(screen.queryByTestId('total-count')).not.toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('renders error message when error prop is provided', () => {
      render(
        <ReviewSummary
          reviewResult={null}
          error="Failed to fetch review summary"
        />
      );
      expect(
        screen.getByText(/Failed to fetch review summary/)
      ).toBeInTheDocument();
    });

    it('displays error banner with red styling', () => {
      render(<ReviewSummary reviewResult={null} error="Network error" />);
      const errorDiv = screen.getByText(/Network error/).closest('div');
      expect(errorDiv).toHaveClass('text-red-600');
    });

    it('does not render summary when error exists', () => {
      render(
        <ReviewSummary reviewResult={mockReviewResultBlocking} error="Error" />
      );
      expect(screen.queryByTestId('total-count')).not.toBeInTheDocument();
    });
  });

  describe('empty state (no review data)', () => {
    it('renders empty state when reviewResult is null', () => {
      render(<ReviewSummary reviewResult={null} />);
      expect(screen.getByText(/No review data available/)).toBeInTheDocument();
    });

    it('suggests triggering a review in empty state', () => {
      render(<ReviewSummary reviewResult={null} />);
      expect(
        screen.getByText(/Trigger a code review to see results/)
      ).toBeInTheDocument();
    });

    it('does not render statistics in empty state', () => {
      render(<ReviewSummary reviewResult={null} />);
      expect(screen.queryByTestId('total-count')).not.toBeInTheDocument();
    });
  });

  describe('blocking status banner', () => {
    it('displays blocking banner when has_blocking_findings is true', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      expect(screen.getByTestId('blocking-banner')).toBeInTheDocument();
    });

    it('shows warning emoji in blocking banner', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      const banner = screen.getByTestId('blocking-banner');
      expect(banner).toHaveTextContent('⚠️');
    });

    it('displays correct blocking count (critical + high)', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      // mockReviewResultBlocking has 1 critical + 2 high = 3
      expect(
        screen.getByText(/Found 3 critical\/high severity findings/)
      ).toBeInTheDocument();
    });

    it('uses singular "finding" when count is 1', () => {
      const singleBlockingResult = {
        ...mockReviewResultBlocking,
        severity_counts: {
          critical: 1,
          high: 0,
          medium: 0,
          low: 0,
          info: 0,
        },
      };
      render(<ReviewSummary reviewResult={singleBlockingResult} />);
      expect(screen.getByText(/1 critical\/high severity finding/)).toBeInTheDocument();
      expect(screen.queryByText(/findings/)).not.toBeInTheDocument();
    });

    it('does not display blocking banner when has_blocking_findings is false', () => {
      render(<ReviewSummary reviewResult={mockReviewResultNonBlocking} />);
      expect(screen.queryByTestId('blocking-banner')).not.toBeInTheDocument();
    });

    it('applies red styling to blocking banner', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      const banner = screen.getByTestId('blocking-banner');
      expect(banner).toHaveClass('bg-red-100');
      expect(banner).toHaveClass('border-red-500');
    });
  });

  describe('success banner', () => {
    it('displays success banner when no findings exist', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);
      expect(screen.getByTestId('success-banner')).toBeInTheDocument();
    });

    it('shows checkmark emoji in success banner', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);
      const banner = screen.getByTestId('success-banner');
      expect(banner).toHaveTextContent('✅');
    });

    it('displays "Review Passed" message', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);
      expect(screen.getByText('Review Passed')).toBeInTheDocument();
      expect(screen.getByText(/No issues found/)).toBeInTheDocument();
    });

    it('applies green styling to success banner', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);
      const banner = screen.getByTestId('success-banner');
      expect(banner).toHaveClass('bg-green-100');
      expect(banner).toHaveClass('border-green-500');
    });

    it('does not display success banner when blocking findings exist', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      expect(screen.queryByTestId('success-banner')).not.toBeInTheDocument();
    });

    it('does not display success banner when non-blocking findings exist', () => {
      render(<ReviewSummary reviewResult={mockReviewResultNonBlocking} />);
      expect(screen.queryByTestId('success-banner')).not.toBeInTheDocument();
    });
  });

  describe('total findings count', () => {
    it('displays total findings count', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      const totalCount = screen.getByTestId('total-count');
      expect(totalCount).toHaveTextContent('6');
    });

    it('displays zero when no findings', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);
      const totalCount = screen.getByTestId('total-count');
      expect(totalCount).toHaveTextContent('0');
    });

    it('displays correct count for non-blocking review', () => {
      render(<ReviewSummary reviewResult={mockReviewResultNonBlocking} />);
      const totalCount = screen.getByTestId('total-count');
      expect(totalCount).toHaveTextContent('2');
    });
  });

  describe('severity breakdown', () => {
    it('renders severity breakdown section', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      expect(screen.getByText('By Severity')).toBeInTheDocument();
    });

    it('displays all severity levels', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      expect(screen.getByTestId('severity-critical')).toBeInTheDocument();
      expect(screen.getByTestId('severity-high')).toBeInTheDocument();
      expect(screen.getByTestId('severity-medium')).toBeInTheDocument();
      expect(screen.getByTestId('severity-low')).toBeInTheDocument();
      expect(screen.getByTestId('severity-info')).toBeInTheDocument();
    });

    it('displays correct counts for each severity', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);

      const criticalBar = screen.getByTestId('severity-critical');
      expect(criticalBar).toHaveTextContent('1');

      const highBar = screen.getByTestId('severity-high');
      expect(highBar).toHaveTextContent('2');

      const mediumBar = screen.getByTestId('severity-medium');
      expect(mediumBar).toHaveTextContent('1');
    });

    it('displays zero counts when no findings of that severity', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);

      const criticalBar = screen.getByTestId('severity-critical');
      expect(criticalBar).toHaveTextContent('0');
    });

    it('renders progress bars with correct colors', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);

      const criticalBar = screen.getByTestId('severity-critical');
      const progressBar = criticalBar.querySelector('.bg-red-500');
      expect(progressBar).toBeInTheDocument();
    });
  });

  describe('category breakdown', () => {
    it('renders category breakdown section', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      expect(screen.getByText('By Category')).toBeInTheDocument();
    });

    it('displays all category types', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      expect(screen.getByTestId('category-security')).toBeInTheDocument();
      expect(screen.getByTestId('category-performance')).toBeInTheDocument();
      expect(screen.getByTestId('category-quality')).toBeInTheDocument();
      expect(
        screen.getByTestId('category-maintainability')
      ).toBeInTheDocument();
      expect(screen.getByTestId('category-style')).toBeInTheDocument();
    });

    it('displays correct counts for each category', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);

      const securityCard = screen.getByTestId('category-security');
      expect(securityCard).toHaveTextContent('2');

      const performanceCard = screen.getByTestId('category-performance');
      expect(performanceCard).toHaveTextContent('1');
    });

    it('displays category icons', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);

      const securityCard = screen.getByTestId('category-security');
      expect(securityCard).toHaveTextContent('🔒');

      const performanceCard = screen.getByTestId('category-performance');
      expect(performanceCard).toHaveTextContent('⚡');
    });

    it('displays zero counts when no findings in that category', () => {
      render(<ReviewSummary reviewResult={mockReviewResultEmpty} />);

      const securityCard = screen.getByTestId('category-security');
      expect(securityCard).toHaveTextContent('0');
    });
  });

  describe('layout and styling', () => {
    it('uses grid layout for category cards', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      const categoryBreakdown = screen
        .getByText('By Category')
        .nextElementSibling;
      expect(categoryBreakdown).toHaveClass('grid');
      expect(categoryBreakdown).toHaveClass('grid-cols-2');
    });

    it('renders severity bars with proper styling', () => {
      render(<ReviewSummary reviewResult={mockReviewResultBlocking} />);
      const severityBar = screen.getByTestId('severity-critical');
      const progressContainer = severityBar.querySelector('.h-2.bg-gray-200');
      expect(progressContainer).toBeInTheDocument();
    });
  });
});
