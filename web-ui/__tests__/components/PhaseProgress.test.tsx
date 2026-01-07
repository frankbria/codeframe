/**
 * PhaseProgress Component Tests
 * Tests for phase visualization with icons, step counters, and progress bars
 * TDD: Tests written before implementation
 */

import { render, screen } from '@testing-library/react';
import PhaseProgress from '@/components/PhaseProgress';

describe('PhaseProgress', () => {
  describe('phase icons', () => {
    it('displays 🔍 for discovery phase', () => {
      render(<PhaseProgress phase="discovery" currentStep={1} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('🔍');
    });

    it('displays 📋 for planning phase', () => {
      render(<PhaseProgress phase="planning" currentStep={1} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('📋');
    });

    it('displays 🔨 for development phase', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('🔨');
    });

    it('displays ✅ for review phase', () => {
      render(<PhaseProgress phase="review" currentStep={10} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('✅');
    });

    it('displays 🎉 for complete phase', () => {
      render(<PhaseProgress phase="complete" currentStep={15} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('🎉');
    });

    it('displays 🚀 for shipped phase', () => {
      render(<PhaseProgress phase="shipped" currentStep={15} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('🚀');
    });
  });

  describe('phase labels', () => {
    it('displays correct label for discovery phase', () => {
      render(<PhaseProgress phase="discovery" currentStep={1} totalSteps={15} />);
      expect(screen.getByText('Discovery Phase')).toBeInTheDocument();
    });

    it('displays correct label for planning phase', () => {
      render(<PhaseProgress phase="planning" currentStep={2} totalSteps={15} />);
      expect(screen.getByText('Planning Phase')).toBeInTheDocument();
    });

    it('displays correct label for development phase', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      expect(screen.getByText('Development Phase')).toBeInTheDocument();
    });

    it('displays correct label for review phase', () => {
      render(<PhaseProgress phase="review" currentStep={10} totalSteps={15} />);
      expect(screen.getByText('Review Phase')).toBeInTheDocument();
    });

    it('displays correct label for complete phase', () => {
      render(<PhaseProgress phase="complete" currentStep={15} totalSteps={15} />);
      expect(screen.getByText('Complete')).toBeInTheDocument();
    });

    it('displays correct label for shipped phase', () => {
      render(<PhaseProgress phase="shipped" currentStep={15} totalSteps={15} />);
      expect(screen.getByText('Shipped')).toBeInTheDocument();
    });
  });

  describe('step counter', () => {
    it('displays "Step 5 of 15"', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 5 of 15');
    });

    it('displays "Step 1 of 15" at start', () => {
      render(<PhaseProgress phase="discovery" currentStep={1} totalSteps={15} />);
      expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 1 of 15');
    });

    it('displays "Step 15 of 15" at completion', () => {
      render(<PhaseProgress phase="complete" currentStep={15} totalSteps={15} />);
      expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 15 of 15');
    });

    it('handles custom total steps', () => {
      render(<PhaseProgress phase="development" currentStep={3} totalSteps={10} />);
      expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 3 of 10');
    });
  });

  describe('progress bar', () => {
    it('shows correct percentage at 33%', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '33');
    });

    it('shows 0% at step 0', () => {
      render(<PhaseProgress phase="discovery" currentStep={0} totalSteps={15} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '0');
    });

    it('shows 100% at completion', () => {
      render(<PhaseProgress phase="complete" currentStep={15} totalSteps={15} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '100');
    });

    it('caps at 100% when step exceeds total', () => {
      render(<PhaseProgress phase="complete" currentStep={20} totalSteps={15} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '100');
    });

    it('has proper accessibility attributes', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuemin', '0');
      expect(progressBar).toHaveAttribute('aria-valuemax', '100');
      expect(progressBar).toHaveAttribute('aria-label', expect.stringContaining('Progress'));
    });
  });

  describe('next action hint', () => {
    it('displays next action hint when provided', () => {
      render(
        <PhaseProgress
          phase="development"
          currentStep={5}
          totalSteps={15}
          nextAction="Implement user authentication"
        />
      );
      expect(screen.getByTestId('next-action-hint')).toHaveTextContent(
        'Implement user authentication'
      );
    });

    it('displays lightbulb emoji with next action', () => {
      render(
        <PhaseProgress
          phase="development"
          currentStep={5}
          totalSteps={15}
          nextAction="Implement feature"
        />
      );
      const hint = screen.getByTestId('next-action-hint');
      expect(hint).toHaveTextContent('💡');
    });

    it('hides next action hint when not provided', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      expect(screen.queryByTestId('next-action-hint')).not.toBeInTheDocument();
    });

    it('hides next action hint when undefined', () => {
      render(
        <PhaseProgress
          phase="development"
          currentStep={5}
          totalSteps={15}
          nextAction={undefined}
        />
      );
      expect(screen.queryByTestId('next-action-hint')).not.toBeInTheDocument();
    });

    it('hides next action hint when empty string', () => {
      render(
        <PhaseProgress phase="development" currentStep={5} totalSteps={15} nextAction="" />
      );
      expect(screen.queryByTestId('next-action-hint')).not.toBeInTheDocument();
    });
  });

  describe('phase-specific styling', () => {
    // Tests verify light mode classes; dark mode classes are also present
    it('applies blue theme for discovery phase', () => {
      const { container } = render(
        <PhaseProgress phase="discovery" currentStep={1} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      expect(progressContainer).toHaveClass('bg-blue-50');
      expect(progressContainer).toHaveClass('text-blue-700');
      expect(progressContainer).toHaveClass('border-blue-200');
    });

    it('applies purple theme for planning phase', () => {
      const { container } = render(
        <PhaseProgress phase="planning" currentStep={2} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      expect(progressContainer).toHaveClass('bg-purple-50');
      expect(progressContainer).toHaveClass('text-purple-700');
      expect(progressContainer).toHaveClass('border-purple-200');
    });

    it('applies green theme for development phase', () => {
      const { container } = render(
        <PhaseProgress phase="development" currentStep={5} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      expect(progressContainer).toHaveClass('bg-green-50');
      expect(progressContainer).toHaveClass('text-green-700');
      expect(progressContainer).toHaveClass('border-green-200');
    });

    it('applies yellow theme for review phase', () => {
      const { container } = render(
        <PhaseProgress phase="review" currentStep={10} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      expect(progressContainer).toHaveClass('bg-yellow-50');
      expect(progressContainer).toHaveClass('text-yellow-700');
      expect(progressContainer).toHaveClass('border-yellow-200');
    });

    it('applies muted theme for complete phase', () => {
      const { container } = render(
        <PhaseProgress phase="complete" currentStep={15} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      // Complete uses Nova semantic colors
      expect(progressContainer).toHaveClass('bg-muted');
      expect(progressContainer).toHaveClass('text-muted-foreground');
      expect(progressContainer).toHaveClass('border-border');
    });

    it('applies indigo theme for shipped phase', () => {
      const { container } = render(
        <PhaseProgress phase="shipped" currentStep={15} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      expect(progressContainer).toHaveClass('bg-indigo-50');
      expect(progressContainer).toHaveClass('text-indigo-700');
      expect(progressContainer).toHaveClass('border-indigo-200');
    });
  });

  describe('edge cases', () => {
    it('handles step 0 correctly', () => {
      render(<PhaseProgress phase="discovery" currentStep={0} totalSteps={15} />);
      expect(screen.getByTestId('step-counter')).toHaveTextContent('Step 0 of 15');
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '0');
    });

    it('handles unknown phase with default styling', () => {
      const { container } = render(
        <PhaseProgress phase="unknown" currentStep={5} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      // Should fallback to muted theme (Nova semantic default)
      expect(progressContainer).toHaveClass('bg-muted');
      expect(progressContainer).toHaveClass('text-muted-foreground');
      expect(progressContainer).toHaveClass('border-border');
    });

    it('handles unknown phase with default label', () => {
      render(<PhaseProgress phase="unknown" currentStep={5} totalSteps={15} />);
      expect(screen.getByText('Unknown Phase')).toBeInTheDocument();
    });

    it('handles empty phase string', () => {
      const { container } = render(<PhaseProgress phase="" currentStep={5} totalSteps={15} />);
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      // Should fallback to muted theme (Nova semantic default)
      expect(progressContainer).toHaveClass('bg-muted');
    });

    it('normalizes phase name to lowercase', () => {
      render(<PhaseProgress phase="DEVELOPMENT" currentStep={5} totalSteps={15} />);
      expect(screen.getByText('Development Phase')).toBeInTheDocument();
      expect(screen.getByTestId('phase-icon')).toHaveTextContent('🔨');
    });

    it('handles totalSteps of 0 without division error', () => {
      render(<PhaseProgress phase="discovery" currentStep={0} totalSteps={0} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '0');
    });
  });

  describe('accessibility', () => {
    it('has proper ARIA labels', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-label');
    });

    it('progress bar has role="progressbar"', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('main container has appropriate test ID', () => {
      const { container } = render(
        <PhaseProgress phase="development" currentStep={5} totalSteps={15} />
      );
      expect(container.querySelector('[data-testid="phase-progress"]')).toBeInTheDocument();
    });
  });

  describe('rendering', () => {
    it('renders the component with all required props', () => {
      render(<PhaseProgress phase="development" currentStep={5} totalSteps={15} />);
      expect(screen.getByTestId('phase-icon')).toBeInTheDocument();
      expect(screen.getByTestId('step-counter')).toBeInTheDocument();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('renders within a bordered container', () => {
      const { container } = render(
        <PhaseProgress phase="development" currentStep={5} totalSteps={15} />
      );
      const progressContainer = container.querySelector('[data-testid="phase-progress"]');
      expect(progressContainer).toHaveClass('border');
    });
  });
});
