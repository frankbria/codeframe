/**
 * ReviewFindings Component Tests (Sprint 10 Phase 2 - T040)
 *
 * Test coverage:
 * - Rendering with findings
 * - Filtering by severity
 * - Sorting by severity and file path
 * - Empty state
 * - Loading state
 * - Error handling
 */

import { render, screen, fireEvent, within } from '@testing-library/react';
import { ReviewFindings } from '@/components/reviews/ReviewFindings';
import {
  mockAllFindings,
  mockCriticalOnlyFindings,
  mockHighOnlyFindings,
  mockMediumOnlyFindings,
  mockCriticalSecurityFinding,
  mockHighPerformanceFinding,
} from '../fixtures/reviews';

describe('ReviewFindings', () => {
  describe('loading state', () => {
    it('renders loading state when loading is true', () => {
      render(<ReviewFindings findings={[]} loading={true} />);
      expect(screen.getByText('Loading findings...')).toBeInTheDocument();
    });

    it('does not render findings when loading', () => {
      render(<ReviewFindings findings={mockAllFindings} loading={true} />);
      expect(screen.queryByTestId('severity-filter')).not.toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('renders error message when error prop is provided', () => {
      render(
        <ReviewFindings
          findings={[]}
          error="Failed to fetch reviews from server"
        />
      );
      expect(
        screen.getByText(/Failed to fetch reviews from server/)
      ).toBeInTheDocument();
    });

    it('displays error banner with red styling', () => {
      render(<ReviewFindings findings={[]} error="Network error" />);
      const errorDiv = screen.getByText(/Network error/).closest('div');
      expect(errorDiv).toHaveClass('text-destructive');
    });

    it('does not render findings when error exists', () => {
      render(
        <ReviewFindings findings={mockAllFindings} error="Some error" />
      );
      expect(screen.queryByTestId('severity-filter')).not.toBeInTheDocument();
    });
  });

  describe('empty state', () => {
    it('renders empty state when findings array is empty', () => {
      render(<ReviewFindings findings={[]} />);
      expect(screen.getByText(/No review findings/)).toBeInTheDocument();
      expect(screen.getByText(/Code looks good!/)).toBeInTheDocument();
    });

    it('displays checkmark emoji in empty state', () => {
      render(<ReviewFindings findings={[]} />);
      expect(screen.getByText(/✅/)).toBeInTheDocument();
    });
  });

  describe('findings display', () => {
    it('renders all findings with correct count', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      expect(
        screen.getByText(`Code Review Findings (${mockAllFindings.length})`)
      ).toBeInTheDocument();
    });

    it('displays critical findings with appropriate styling', () => {
      render(<ReviewFindings findings={mockCriticalOnlyFindings} />);
      const criticalFinding = screen.getByTestId('finding-critical');
      // SEVERITY_COLORS from types/reviews.ts defines the actual colors
      expect(criticalFinding).toHaveClass('border');
    });

    it('displays high findings with appropriate styling', () => {
      render(<ReviewFindings findings={mockHighOnlyFindings} />);
      const highFindings = screen.getAllByTestId('finding-high');
      // SEVERITY_COLORS from types/reviews.ts defines the actual colors
      expect(highFindings[0]).toHaveClass('border');
    });

    it('displays file path for each finding', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      expect(screen.getByText(/src\/auth\/login.ts/)).toBeInTheDocument();
    });

    it('displays line number when present', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      expect(screen.getByText(/:45/)).toBeInTheDocument();
    });

    it('displays message for each finding', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      expect(
        screen.getByText(/SQL injection vulnerability detected/)
      ).toBeInTheDocument();
    });

    it('displays recommendation when present', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      expect(screen.getByText('Recommendation:')).toBeInTheDocument();
      expect(
        screen.getByText(/Use parameterized queries/)
      ).toBeInTheDocument();
    });

    it('displays code snippet when present', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      expect(
        screen.getByText(/SELECT \* FROM users WHERE username/)
      ).toBeInTheDocument();
    });

    it('displays category icon and name', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      expect(screen.getByText('🔒')).toBeInTheDocument(); // Security icon
      expect(screen.getByText('security')).toBeInTheDocument();
    });

    it('displays severity badge', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);
      // Badge text is lowercase in DOM but displayed as uppercase via CSS
      // Use getAllByText and filter for the one with 'uppercase' class
      const badges = screen.getAllByText(/critical/i);
      const uppercaseBadge = badges.find(el => el.classList.contains('uppercase'));
      expect(uppercaseBadge).toBeDefined();
      expect(uppercaseBadge).toHaveClass('uppercase');
    });
  });

  describe('severity filtering', () => {
    it('renders severity filter dropdown', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      expect(screen.getByTestId('severity-filter')).toBeInTheDocument();
    });

    it('filters findings by critical severity', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      const filterSelect = screen.getByTestId('severity-filter');

      fireEvent.change(filterSelect, { target: { value: 'critical' } });

      // Should only show 1 critical finding
      expect(screen.getByText(/Code Review Findings \(1\)/)).toBeInTheDocument();
    });

    it('filters findings by high severity', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      const filterSelect = screen.getByTestId('severity-filter');

      fireEvent.change(filterSelect, { target: { value: 'high' } });

      // Should show 2 high findings
      expect(screen.getByText(/Code Review Findings \(2\)/)).toBeInTheDocument();
    });

    it('shows all findings when filter is set to "all"', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      const filterSelect = screen.getByTestId('severity-filter');

      // Change to critical first
      fireEvent.change(filterSelect, { target: { value: 'critical' } });

      // Then back to all
      fireEvent.change(filterSelect, { target: { value: 'all' } });

      expect(
        screen.getByText(`Code Review Findings (${mockAllFindings.length})`)
      ).toBeInTheDocument();
    });

    it('displays message when no findings match filter', () => {
      // Render with only low/info findings
      render(
        <ReviewFindings
          findings={[
            { ...mockCriticalSecurityFinding, severity: 'low' as any },
          ]}
        />
      );
      const filterSelect = screen.getByTestId('severity-filter');

      fireEvent.change(filterSelect, { target: { value: 'critical' } });

      expect(
        screen.getByText(/No findings match the selected filter/)
      ).toBeInTheDocument();
    });
  });

  describe('sorting', () => {
    it('renders sort buttons', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      expect(screen.getByTestId('sort-severity')).toBeInTheDocument();
      expect(screen.getByTestId('sort-file-path')).toBeInTheDocument();
    });

    it('highlights active sort button', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      const severityButton = screen.getByTestId('sort-severity');

      // Severity should be active by default
      expect(severityButton).toHaveClass('bg-primary');
    });

    it('sorts by severity by default (ascending)', () => {
      render(<ReviewFindings findings={mockAllFindings} />);

      // First finding should be critical (severity order: 0)
      const findingCards = screen.getAllByTestId(/finding-/);
      const firstCard = findingCards[0];

      // Check that critical finding appears first (text is lowercase, displayed as uppercase via CSS)
      expect(within(firstCard).getByText(/critical/i)).toBeInTheDocument();
    });

    it('toggles sort direction when clicking same sort button', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      const severityButton = screen.getByTestId('sort-severity');

      // Default is ascending (↑)
      expect(severityButton).toHaveTextContent('↑');

      // Click to toggle to descending
      fireEvent.click(severityButton);
      expect(severityButton).toHaveTextContent('↓');

      // Click again to toggle back to ascending
      fireEvent.click(severityButton);
      expect(severityButton).toHaveTextContent('↑');
    });

    it('switches sort field when clicking different sort button', () => {
      render(<ReviewFindings findings={mockAllFindings} />);
      const severityButton = screen.getByTestId('sort-severity');
      const filePathButton = screen.getByTestId('sort-file-path');

      // Initially severity is active
      expect(severityButton).toHaveClass('bg-primary');
      expect(filePathButton).toHaveClass('bg-muted');

      // Click file path button
      fireEvent.click(filePathButton);

      // Now file path should be active
      expect(filePathButton).toHaveClass('bg-primary');
      expect(severityButton).toHaveClass('bg-muted');
    });
  });

  describe('finding click handler', () => {
    it('calls onFindingClick when a finding is clicked', () => {
      const handleClick = jest.fn();
      render(
        <ReviewFindings
          findings={[mockCriticalSecurityFinding]}
          onFindingClick={handleClick}
        />
      );

      const findingCard = screen.getByTestId('finding-critical');
      fireEvent.click(findingCard);

      expect(handleClick).toHaveBeenCalledWith(mockCriticalSecurityFinding);
    });

    it('does not crash if onFindingClick is not provided', () => {
      render(<ReviewFindings findings={[mockCriticalSecurityFinding]} />);

      const findingCard = screen.getByTestId('finding-critical');
      expect(() => fireEvent.click(findingCard)).not.toThrow();
    });
  });

  describe('grouped display', () => {
    it('groups findings by severity level', () => {
      render(<ReviewFindings findings={mockAllFindings} />);

      // Should have severity group headers
      expect(screen.getByText(/critical \(1\)/i)).toBeInTheDocument();
      expect(screen.getByText(/high \(2\)/i)).toBeInTheDocument();
      expect(screen.getByText(/medium \(1\)/i)).toBeInTheDocument();
    });

    it('does not render severity groups with zero findings', () => {
      render(<ReviewFindings findings={mockCriticalOnlyFindings} />);

      // Only critical should be shown
      expect(screen.getByText(/critical \(1\)/i)).toBeInTheDocument();

      // Others should not be shown
      expect(screen.queryByText(/high \(/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/medium \(/i)).not.toBeInTheDocument();
    });
  });
});
