/**
 * Tests for PhaseIndicator Component (cf-17.2)
 * TDD RED Phase - Write tests first
 */

import { render, screen } from '@testing-library/react';
import PhaseIndicator from '../PhaseIndicator';

describe('PhaseIndicator Component', () => {
  describe('Phase Text Display', () => {
    it('should render "Discovery" for discovery phase', () => {
      render(<PhaseIndicator phase="discovery" />);

      expect(screen.getByText('Discovery')).toBeInTheDocument();
    });

    it('should render "Planning" for planning phase', () => {
      render(<PhaseIndicator phase="planning" />);

      expect(screen.getByText('Planning')).toBeInTheDocument();
    });

    it('should render "Active" for active phase', () => {
      render(<PhaseIndicator phase="active" />);

      expect(screen.getByText('Active')).toBeInTheDocument();
    });

    it('should render "Review" for review phase', () => {
      render(<PhaseIndicator phase="review" />);

      expect(screen.getByText('Review')).toBeInTheDocument();
    });

    it('should render "Complete" for complete phase', () => {
      render(<PhaseIndicator phase="complete" />);

      expect(screen.getByText('Complete')).toBeInTheDocument();
    });
  });

  describe('Phase Color Coding', () => {
    it('should display blue background for discovery phase', () => {
      const { container } = render(<PhaseIndicator phase="discovery" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('bg-blue-100');
      expect(badge).toHaveClass('text-blue-800');
    });

    it('should display purple background for planning phase', () => {
      const { container } = render(<PhaseIndicator phase="planning" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('bg-purple-100');
      expect(badge).toHaveClass('text-purple-800');
    });

    it('should display green background for active phase', () => {
      const { container } = render(<PhaseIndicator phase="active" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('bg-green-100');
      expect(badge).toHaveClass('text-green-800');
    });

    it('should display yellow background for review phase', () => {
      const { container } = render(<PhaseIndicator phase="review" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('bg-yellow-100');
      expect(badge).toHaveClass('text-yellow-800');
    });

    it('should display gray background for complete phase', () => {
      const { container } = render(<PhaseIndicator phase="complete" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('bg-gray-100');
      expect(badge).toHaveClass('text-gray-800');
    });
  });

  describe('Invalid Phase Handling', () => {
    it('should render "Unknown" for invalid phase', () => {
      // @ts-expect-error Testing invalid phase
      render(<PhaseIndicator phase="invalid" />);

      expect(screen.getByText('Unknown')).toBeInTheDocument();
    });

    it('should display gray color for invalid phase', () => {
      // @ts-expect-error Testing invalid phase
      const { container } = render(<PhaseIndicator phase="invalid" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('bg-gray-100');
      expect(badge).toHaveClass('text-gray-800');
    });

    it('should handle empty string phase', () => {
      // @ts-expect-error Testing empty phase
      render(<PhaseIndicator phase="" />);

      expect(screen.getByText('Unknown')).toBeInTheDocument();
    });
  });

  describe('Styling and Layout', () => {
    it('should render as an inline badge/pill', () => {
      const { container } = render(<PhaseIndicator phase="discovery" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('inline-flex');
      expect(badge).toHaveClass('items-center');
    });

    it('should have rounded corners (pill shape)', () => {
      const { container } = render(<PhaseIndicator phase="planning" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('rounded-full');
    });

    it('should have appropriate padding', () => {
      const { container } = render(<PhaseIndicator phase="active" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('px-2.5');
      expect(badge).toHaveClass('py-0.5');
    });

    it('should have small font size', () => {
      const { container } = render(<PhaseIndicator phase="review" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('text-xs');
    });

    it('should have medium font weight', () => {
      const { container } = render(<PhaseIndicator phase="complete" />);

      const badge = container.querySelector('[data-testid="phase-badge"]');
      expect(badge).toHaveClass('font-medium');
    });
  });

  describe('Accessibility', () => {
    it('should have status role for screen readers', () => {
      render(<PhaseIndicator phase="discovery" />);

      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
    });

    it('should have aria-label with phase information', () => {
      render(<PhaseIndicator phase="planning" />);

      const badge = screen.getByRole('status');
      expect(badge).toHaveAttribute('aria-label', 'Project phase: Planning');
    });

    it('should have aria-label for all valid phases', () => {
      const phases: Array<'discovery' | 'planning' | 'active' | 'review' | 'complete'> = [
        'discovery',
        'planning',
        'active',
        'review',
        'complete',
      ];

      phases.forEach((phase) => {
        const { unmount } = render(<PhaseIndicator phase={phase} />);
        const badge = screen.getByRole('status');
        const expectedLabel = `Project phase: ${phase.charAt(0).toUpperCase() + phase.slice(1)}`;
        expect(badge).toHaveAttribute('aria-label', expectedLabel);
        unmount();
      });
    });

    it('should have aria-label for unknown phase', () => {
      // @ts-expect-error Testing invalid phase
      render(<PhaseIndicator phase="invalid" />);

      const badge = screen.getByRole('status');
      expect(badge).toHaveAttribute('aria-label', 'Project phase: Unknown');
    });
  });

  describe('Case Sensitivity', () => {
    it('should handle lowercase phase names', () => {
      render(<PhaseIndicator phase="discovery" />);

      expect(screen.getByText('Discovery')).toBeInTheDocument();
    });

    it('should handle uppercase phase names (if converted)', () => {
      // Component should handle and normalize case
      // @ts-expect-error Testing case handling
      render(<PhaseIndicator phase="DISCOVERY" />);

      // Should still display properly capitalized
      const badge = screen.getByRole('status');
      expect(badge).toBeInTheDocument();
    });
  });
});
