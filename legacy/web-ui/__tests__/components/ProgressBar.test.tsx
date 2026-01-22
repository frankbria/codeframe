/**
 * Tests for ProgressBar Component (cf-17.2)
 * Migrated from src/components/__tests__/ProgressBar.test.tsx
 */

import { render, screen } from '@testing-library/react';
import ProgressBar from '@/components/ProgressBar';

describe('ProgressBar Component', () => {
  describe('Rendering and Width', () => {
    it('should render with correct width for percentage', () => {
      const { container } = render(<ProgressBar percentage={75} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveStyle({ width: '75%' });
    });

    it('should render with 0% width', () => {
      const { container } = render(<ProgressBar percentage={0} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveStyle({ width: '0%' });
    });

    it('should render with 100% width', () => {
      const { container } = render(<ProgressBar percentage={100} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveStyle({ width: '100%' });
    });

    it('should handle invalid percentage (negative) by clamping to 0', () => {
      const { container } = render(<ProgressBar percentage={-10} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveStyle({ width: '0%' });
    });

    it('should handle invalid percentage (>100) by clamping to 100', () => {
      const { container } = render(<ProgressBar percentage={150} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveStyle({ width: '100%' });
    });
  });

  describe('Color Coding', () => {
    it('should display green color when percentage > 75', () => {
      const { container } = render(<ProgressBar percentage={80} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveClass('bg-green-500');
    });

    it('should display yellow color when percentage is 25-75', () => {
      const { container } = render(<ProgressBar percentage={50} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveClass('bg-yellow-500');
    });

    it('should display yellow color at exactly 25%', () => {
      const { container } = render(<ProgressBar percentage={25} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveClass('bg-yellow-500');
    });

    it('should display yellow color at exactly 75%', () => {
      const { container } = render(<ProgressBar percentage={75} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveClass('bg-yellow-500');
    });

    it('should display red color when percentage < 25', () => {
      const { container } = render(<ProgressBar percentage={20} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toHaveClass('bg-red-500');
    });
  });

  describe('Percentage Text Display', () => {
    it('should display percentage text when showPercentage is true', () => {
      render(<ProgressBar percentage={65} showPercentage={true} />);

      expect(screen.getByText('65%')).toBeInTheDocument();
    });

    it('should not display percentage text when showPercentage is false', () => {
      render(<ProgressBar percentage={65} showPercentage={false} />);

      expect(screen.queryByText('65%')).not.toBeInTheDocument();
    });

    it('should not display percentage text by default (showPercentage undefined)', () => {
      render(<ProgressBar percentage={65} />);

      expect(screen.queryByText('65%')).not.toBeInTheDocument();
    });

    it('should display 0% when showPercentage is true and percentage is 0', () => {
      render(<ProgressBar percentage={0} showPercentage={true} />);

      expect(screen.getByText('0%')).toBeInTheDocument();
    });

    it('should display 100% when showPercentage is true and percentage is 100', () => {
      render(<ProgressBar percentage={100} showPercentage={true} />);

      expect(screen.getByText('100%')).toBeInTheDocument();
    });
  });

  describe('Label Display', () => {
    it('should display label when provided', () => {
      render(<ProgressBar percentage={50} label="Discovery Progress" />);

      expect(screen.getByText('Discovery Progress')).toBeInTheDocument();
    });

    it('should not display label when not provided', () => {
      const { container } = render(<ProgressBar percentage={50} />);

      const labelElement = container.querySelector('[data-testid="progress-bar-label"]');
      expect(labelElement).not.toBeInTheDocument();
    });

    it('should display both label and percentage when both provided', () => {
      render(<ProgressBar percentage={75} label="Task Completion" showPercentage={true} />);

      expect(screen.getByText('Task Completion')).toBeInTheDocument();
      expect(screen.getByText('75%')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA role', () => {
      render(<ProgressBar percentage={50} />);

      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toBeInTheDocument();
    });

    it('should have aria-valuenow attribute', () => {
      render(<ProgressBar percentage={65} />);

      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '65');
    });

    it('should have aria-valuemin attribute set to 0', () => {
      render(<ProgressBar percentage={50} />);

      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuemin', '0');
    });

    it('should have aria-valuemax attribute set to 100', () => {
      render(<ProgressBar percentage={50} />);

      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuemax', '100');
    });

    it('should have aria-label when label is provided', () => {
      render(<ProgressBar percentage={50} label="Loading" />);

      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-label', 'Loading');
    });

    it('should have default aria-label when no label provided', () => {
      render(<ProgressBar percentage={50} />);

      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-label', 'Progress');
    });
  });

  describe('Responsive Design', () => {
    it('should render with full width container', () => {
      const { container } = render(<ProgressBar percentage={50} />);

      const containerElement = container.querySelector('[data-testid="progress-bar-container"]');
      expect(containerElement).toHaveClass('w-full');
    });

    it('should maintain structure with small percentages on mobile', () => {
      const { container } = render(<ProgressBar percentage={5} />);

      const filledBar = container.querySelector('[data-testid="progress-bar-filled"]');
      expect(filledBar).toBeInTheDocument();
      expect(filledBar).toHaveStyle({ width: '5%' });
    });
  });
});
