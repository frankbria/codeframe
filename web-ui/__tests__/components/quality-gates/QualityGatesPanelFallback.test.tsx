/**
 * Test suite for QualityGatesPanelFallback component
 * Target: 85%+ code coverage
 *
 * Tests error display, retry mechanism, dismiss functionality, and accessibility
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import QualityGatesPanelFallback from '@/components/quality-gates/QualityGatesPanelFallback';

describe('QualityGatesPanelFallback', () => {
  const mockError = new Error('Test error message');
  const mockOnRetry = jest.fn();
  const mockOnDismiss = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render error panel with heading', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByText('Quality Gates Panel Unavailable')).toBeInTheDocument();
    });

    it('should render warning icon', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByText('⚠️')).toBeInTheDocument();
    });

    it('should render descriptive error message', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(
        screen.getByText(/An error occurred while loading the Quality Gates panel/i)
      ).toBeInTheDocument();
    });

    it('should render with data-testid for testing', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByTestId('quality-gates-panel-fallback')).toBeInTheDocument();
    });
  });

  describe('Retry Button', () => {
    it('should render Retry button', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('should call onRetry when Retry button is clicked', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const retryButton = screen.getByRole('button', { name: /retry/i });
      fireEvent.click(retryButton);

      expect(mockOnRetry).toHaveBeenCalledTimes(1);
    });

    it('should call onRetry only once per click', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const retryButton = screen.getByRole('button', { name: /retry/i });
      fireEvent.click(retryButton);
      fireEvent.click(retryButton);
      fireEvent.click(retryButton);

      expect(mockOnRetry).toHaveBeenCalledTimes(3);
    });
  });

  describe('Dismiss Button', () => {
    it('should render Dismiss button when onDismiss is provided', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByRole('button', { name: /continue without quality gates/i })).toBeInTheDocument();
    });

    it('should not render Dismiss button when onDismiss is not provided', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
        />
      );

      expect(screen.queryByRole('button', { name: /continue without quality gates/i })).not.toBeInTheDocument();
    });

    it('should call onDismiss when Dismiss button is clicked', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const dismissButton = screen.getByRole('button', { name: /continue without quality gates/i });
      fireEvent.click(dismissButton);

      expect(mockOnDismiss).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error Details Display', () => {
    it('should display error message when error is provided', () => {
      const customError = new Error('Custom error message for testing');
      render(
        <QualityGatesPanelFallback
          error={customError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByText(/Custom error message for testing/i)).toBeInTheDocument();
    });

    it('should display default message when error is not provided', () => {
      render(
        <QualityGatesPanelFallback
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByText(/Unknown error/i)).toBeInTheDocument();
    });

    it('should display error stack in development mode', () => {
      // Mock NODE_ENV for this test
      const originalEnv = process.env.NODE_ENV;
      Object.defineProperty(process.env, 'NODE_ENV', {
        value: 'development',
        writable: true,
        configurable: true
      });

      const errorWithStack = new Error('Error with stack');
      errorWithStack.stack = 'Error: Error with stack\n  at TestFile:10:15';

      render(
        <QualityGatesPanelFallback
          error={errorWithStack}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      // Should have a details element for error stack
      const detailsElement = screen.getByText(/error details/i).closest('details');
      expect(detailsElement).toBeInTheDocument();

      // Restore NODE_ENV
      Object.defineProperty(process.env, 'NODE_ENV', {
        value: originalEnv,
        writable: true,
        configurable: true
      });
    });

    it('should not display error stack in production mode', () => {
      // Mock NODE_ENV for this test
      const originalEnv = process.env.NODE_ENV;
      Object.defineProperty(process.env, 'NODE_ENV', {
        value: 'production',
        writable: true,
        configurable: true
      });

      const errorWithStack = new Error('Error with stack');
      errorWithStack.stack = 'Error: Error with stack\n  at TestFile:10:15';

      render(
        <QualityGatesPanelFallback
          error={errorWithStack}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      // Should not have a details element for error stack
      expect(screen.queryByText(/error details/i)).not.toBeInTheDocument();

      // Restore NODE_ENV
      Object.defineProperty(process.env, 'NODE_ENV', {
        value: originalEnv,
        writable: true,
        configurable: true
      });
    });
  });

  describe('Accessibility', () => {
    it('should have appropriate ARIA role for error alert', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const alertElement = screen.getByRole('alert');
      expect(alertElement).toBeInTheDocument();
    });

    it('should have accessible button labels', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /continue without quality gates/i })).toBeInTheDocument();
    });

    it('should allow keyboard navigation to buttons', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const retryButton = screen.getByRole('button', { name: /retry/i });
      const dismissButton = screen.getByRole('button', { name: /continue without quality gates/i });

      expect(retryButton).not.toHaveAttribute('disabled');
      expect(dismissButton).not.toHaveAttribute('disabled');
    });
  });

  describe('Visual Design', () => {
    it('should apply error-themed color classes', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const container = screen.getByTestId('quality-gates-panel-fallback');
      expect(container).toHaveClass('bg-destructive/10', 'border-destructive/30');
    });

    it('should apply primary button styling to Retry button', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const retryButton = screen.getByRole('button', { name: /retry/i });
      expect(retryButton).toHaveClass('bg-primary', 'hover:bg-primary/90');
    });

    it('should apply secondary button styling to Dismiss button', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const dismissButton = screen.getByRole('button', { name: /continue without quality gates/i });
      expect(dismissButton).toHaveClass('bg-secondary', 'hover:bg-secondary/80');
    });
  });

  describe('Edge Cases', () => {
    it('should handle error without message', () => {
      const errorWithoutMessage = new Error();
      render(
        <QualityGatesPanelFallback
          error={errorWithoutMessage}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      // Should still render without crashing
      expect(screen.getByTestId('quality-gates-panel-fallback')).toBeInTheDocument();
    });

    it('should handle undefined error gracefully', () => {
      render(
        <QualityGatesPanelFallback
          error={undefined}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      expect(screen.getByText(/Unknown error/i)).toBeInTheDocument();
    });

    it('should handle rapid retry clicks without breaking', () => {
      render(
        <QualityGatesPanelFallback
          error={mockError}
          onRetry={mockOnRetry}
          onDismiss={mockOnDismiss}
        />
      );

      const retryButton = screen.getByRole('button', { name: /retry/i });

      // Simulate rapid clicking
      for (let i = 0; i < 10; i++) {
        fireEvent.click(retryButton);
      }

      expect(mockOnRetry).toHaveBeenCalledTimes(10);
    });
  });
});
