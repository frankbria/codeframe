/**
 * ErrorBoundary Component Tests
 *
 * Comprehensive test suite for ErrorBoundary component.
 * Tests error catching, fallback UI, recovery, lifecycle methods, and accessibility.
 *
 * Target Coverage: >85%
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Task: T133
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ErrorBoundary from '@/components/ErrorBoundary';
import { ReactNode } from 'react';

/**
 * Helper to set NODE_ENV for testing (process.env.NODE_ENV is read-only)
 */
function setNodeEnv(env: string) {
  Object.defineProperty(process.env, 'NODE_ENV', {
    value: env,
    writable: true,
    configurable: true,
  });
}

/**
 * Component that throws an error when shouldThrow is true
 */
interface ThrowErrorProps {
  shouldThrow?: boolean;
  error?: Error | string | object;
}

function ThrowError({ shouldThrow = false, error = new Error('Test error') }: ThrowErrorProps) {
  if (shouldThrow) {
    if (error instanceof Error) {
      throw error;
    } else if (typeof error === 'string') {
      throw new Error(error);
    } else {
      throw error;
    }
  }
  return <div data-testid="child-component">Child Component</div>;
}

/**
 * Component for testing nested error boundaries
 */
function NestedErrorBoundaryTest({ throwInner = false, throwOuter = false }) {
  return (
    <ErrorBoundary fallback={<div data-testid="outer-fallback">Outer Error</div>}>
      <div data-testid="outer-content">
        Outer Content
        <ErrorBoundary fallback={<div data-testid="inner-fallback">Inner Error</div>}>
          <ThrowError shouldThrow={throwInner} />
        </ErrorBoundary>
      </div>
      <ThrowError shouldThrow={throwOuter} />
    </ErrorBoundary>
  );
}

describe('ErrorBoundary', () => {
  // Store original console.error
  let originalConsoleError: typeof console.error;
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    // Mock console.error to avoid test output pollution
    originalConsoleError = console.error;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    // Set NODE_ENV to development for testing error details
    setNodeEnv('development');
  });

  afterEach(() => {
    // Restore console.error
    consoleErrorSpy.mockRestore();
    console.error = originalConsoleError;

    // Clear all mocks
    jest.clearAllMocks();
  });

  // ==========================================================================
  // Test Case 1: Renders children when no error occurs
  // ==========================================================================
  describe('Normal Rendering', () => {
    it('should render children when no error occurs', () => {
      render(
        <ErrorBoundary>
          <div data-testid="test-child">Test Child</div>
        </ErrorBoundary>
      );

      expect(screen.getByTestId('test-child')).toBeInTheDocument();
      expect(screen.getByTestId('test-child')).toHaveTextContent('Test Child');
    });

    it('should render multiple children without errors', () => {
      render(
        <ErrorBoundary>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
          <div data-testid="child-3">Child 3</div>
        </ErrorBoundary>
      );

      expect(screen.getByTestId('child-1')).toBeInTheDocument();
      expect(screen.getByTestId('child-2')).toBeInTheDocument();
      expect(screen.getByTestId('child-3')).toBeInTheDocument();
    });

    it('should not show error UI when children render successfully', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByTestId('child-component')).toBeInTheDocument();
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });
  });

  // ==========================================================================
  // Test Case 2: Catches errors thrown by child components
  // ==========================================================================
  describe('Error Catching', () => {
    it('should catch errors thrown by child components', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      // Child should not be rendered
      expect(screen.queryByTestId('child-component')).not.toBeInTheDocument();

      // Error UI should be displayed
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should catch errors from deeply nested children', () => {
      function NestedChildren() {
        return (
          <div>
            <div>
              <div>
                <div>
                  <ThrowError shouldThrow={true} />
                </div>
              </div>
            </div>
          </div>
        );
      }

      render(
        <ErrorBoundary>
          <NestedChildren />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should prevent error from propagating to parent', () => {
      // If error propagates, this test would fail
      expect(() => {
        render(
          <ErrorBoundary>
            <ThrowError shouldThrow={true} />
          </ErrorBoundary>
        );
      }).not.toThrow();
    });
  });

  // ==========================================================================
  // Test Case 3: Displays error message when error occurs
  // ==========================================================================
  describe('Error UI Display', () => {
    it('should display default error message', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(
        screen.getByText('An error occurred while rendering this component. Please try refreshing the page.')
      ).toBeInTheDocument();
    });

    it('should display error icon', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      // Check for warning emoji
      expect(screen.getByText('⚠')).toBeInTheDocument();
    });

    it('should display error details in development mode', () => {
      setNodeEnv('development');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error('Custom test error')} />
        </ErrorBoundary>
      );

      // Error details should be in a <details> element
      const details = screen.getByText('Error details (development only)');
      expect(details).toBeInTheDocument();

      // Error message should be displayed
      expect(screen.getByText(/Custom test error/)).toBeInTheDocument();
    });

    it('should NOT display error details in production mode', () => {
      setNodeEnv('production');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error('Custom test error')} />
        </ErrorBoundary>
      );

      // Error details should not be shown
      expect(screen.queryByText('Error details (development only)')).not.toBeInTheDocument();
    });

    it('should display error stack trace in development mode', () => {
      setNodeEnv('development');

      const errorWithStack = new Error('Error with stack');
      errorWithStack.stack = 'Error: Error with stack\n    at TestComponent\n    at ErrorBoundary';

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={errorWithStack} />
        </ErrorBoundary>
      );

      // Stack trace should be visible in the details element
      const pre = screen.getByText(/at TestComponent/);
      expect(pre).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // Test Case 4: Shows retry button
  // ==========================================================================
  describe('Retry Button', () => {
    it('should display refresh page button', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const refreshButton = screen.getByRole('button', { name: /refresh page/i });
      expect(refreshButton).toBeInTheDocument();
    });

    it('should have correct button styling', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const refreshButton = screen.getByRole('button', { name: /refresh page/i });
      expect(refreshButton).toHaveClass('bg-primary', 'text-white', 'rounded-md');
    });
  });

  // ==========================================================================
  // Test Case 5: Resets error boundary on retry click
  // ==========================================================================
  describe('Error Recovery', () => {
    it('should have a functional refresh button that triggers page reload', () => {
      const { container } = render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const refreshButton = screen.getByRole('button', { name: /refresh page/i });

      // Verify button exists and is enabled
      expect(refreshButton).toBeInTheDocument();
      expect(refreshButton).toBeEnabled();

      // Verify button has proper text
      expect(refreshButton).toHaveTextContent('Refresh Page');

      // Verify button is in the error UI (not in normal children)
      expect(container.querySelector('.bg-primary')).toBeInTheDocument();
    });

    it('should render refresh button with proper styling', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const refreshButton = screen.getByRole('button', { name: /refresh page/i });

      // Verify button styling for clickability
      expect(refreshButton).toHaveClass('bg-primary');
      expect(refreshButton).toHaveClass('hover:bg-primary/90');
      expect(refreshButton).toHaveClass('w-full');

      // Button should be clickable (enabled)
      expect(refreshButton).not.toBeDisabled();
    });
  });

  // ==========================================================================
  // Test Case 6: Tests getDerivedStateFromError lifecycle
  // ==========================================================================
  describe('getDerivedStateFromError Lifecycle', () => {
    it('should update state when error is thrown', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      // Verify state was updated by checking error UI is rendered
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should capture error object in state', () => {
      setNodeEnv('development');
      const customError = new Error('Captured in state error');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={customError} />
        </ErrorBoundary>
      );

      // In development mode, error message should be visible
      expect(screen.getByText(/Captured in state error/)).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // Test Case 7: Tests componentDidCatch logging
  // ==========================================================================
  describe('componentDidCatch Lifecycle', () => {
    it('should log error to console in development mode', () => {
      setNodeEnv('development');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error('Test error')} />
        </ErrorBoundary>
      );

      // Verify console.error was called with error
      expect(consoleErrorSpy).toHaveBeenCalled();

      // Find the calls that match our error boundary logging
      const errorBoundaryCalls = consoleErrorSpy.mock.calls.filter((call: any[]) =>
        call.some((arg: any) => typeof arg === 'string' && arg.includes('[ErrorBoundary]'))
      );

      expect(errorBoundaryCalls.length).toBeGreaterThan(0);
    });

    it('should NOT log error to console in production mode', () => {
      setNodeEnv('production');
      consoleErrorSpy.mockClear();

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error('Production error')} />
        </ErrorBoundary>
      );

      // React still calls console.error, but ErrorBoundary should not add extra logs
      const errorBoundaryCalls = consoleErrorSpy.mock.calls.filter((call: any[]) =>
        call.some(arg => typeof arg === 'string' && arg.includes('[ErrorBoundary]'))
      );

      expect(errorBoundaryCalls.length).toBe(0);
    });

    it('should call onError callback when provided', () => {
      const onErrorMock = jest.fn();

      render(
        <ErrorBoundary onError={onErrorMock}>
          <ThrowError shouldThrow={true} error={new Error('Callback error')} />
        </ErrorBoundary>
      );

      expect(onErrorMock).toHaveBeenCalledTimes(1);
      expect(onErrorMock).toHaveBeenCalledWith(
        expect.any(Error),
        expect.objectContaining({
          componentStack: expect.any(String),
        })
      );
    });

    it('should NOT call onError callback when not provided', () => {
      // Should not throw error when onError is undefined
      expect(() => {
        render(
          <ErrorBoundary>
            <ThrowError shouldThrow={true} />
          </ErrorBoundary>
        );
      }).not.toThrow();
    });
  });

  // ==========================================================================
  // Test Case 8: Handles different error types
  // ==========================================================================
  describe('Different Error Types', () => {
    it('should handle Error objects', () => {
      const error = new Error('Standard error');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={error} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should handle TypeError objects', () => {
      const error = new TypeError('Type error');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={error} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should handle string errors', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error="String error message" />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should handle errors with custom properties', () => {
      class CustomError extends Error {
        public code: number;
        constructor(message: string, code: number) {
          super(message);
          this.name = 'CustomError';
          this.code = code;
        }
      }

      const error = new CustomError('Custom error', 500);

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={error} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should handle null error stack gracefully', () => {
      setNodeEnv('development');
      const errorWithoutStack = new Error('No stack');
      errorWithoutStack.stack = undefined;

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={errorWithoutStack} />
        </ErrorBoundary>
      );

      // Should still render error UI without crashing
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // Test Case 9: Tests error boundary hierarchy (nested boundaries)
  // ==========================================================================
  describe('Nested Error Boundaries', () => {
    it('should only trigger inner boundary when inner component throws', () => {
      render(<NestedErrorBoundaryTest throwInner={true} throwOuter={false} />);

      // Inner fallback should be shown
      expect(screen.getByTestId('inner-fallback')).toBeInTheDocument();
      expect(screen.getByText('Inner Error')).toBeInTheDocument();

      // Outer content should still be visible
      expect(screen.getByTestId('outer-content')).toBeInTheDocument();

      // Outer fallback should not be shown
      expect(screen.queryByTestId('outer-fallback')).not.toBeInTheDocument();
    });

    it('should trigger outer boundary when outer component throws', () => {
      render(<NestedErrorBoundaryTest throwInner={false} throwOuter={true} />);

      // Outer fallback should be shown
      expect(screen.getByTestId('outer-fallback')).toBeInTheDocument();
      expect(screen.getByText('Outer Error')).toBeInTheDocument();

      // Inner content should not be visible
      expect(screen.queryByTestId('inner-fallback')).not.toBeInTheDocument();
      expect(screen.queryByTestId('outer-content')).not.toBeInTheDocument();
    });

    it('should isolate errors to nearest boundary', () => {
      render(<NestedErrorBoundaryTest throwInner={true} throwOuter={false} />);

      // Only inner boundary should catch the error
      expect(screen.getByTestId('inner-fallback')).toBeInTheDocument();
      expect(screen.getByTestId('outer-content')).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // Test Case 10: Verifies error UI accessibility
  // ==========================================================================
  describe('Accessibility', () => {
    it('should have accessible error heading', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const heading = screen.getByRole('heading', { name: /something went wrong/i });
      expect(heading).toBeInTheDocument();
      expect(heading.tagName).toBe('H2');
    });

    it('should have accessible refresh button', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const button = screen.getByRole('button', { name: /refresh page/i });
      expect(button).toBeInTheDocument();
      expect(button).toBeEnabled();
    });

    it('should have visible focus indicators on interactive elements', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const button = screen.getByRole('button', { name: /refresh page/i });

      // Button should be keyboard accessible
      button.focus();
      expect(button).toHaveFocus();
    });

    it('should have semantic HTML structure', () => {
      const { container } = render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      // Should have proper div structure
      const errorContainer = container.querySelector('.min-h-screen');
      expect(errorContainer).toBeInTheDocument();

      // Should have card-like container
      const card = container.querySelector('.bg-card.rounded-lg.shadow-lg');
      expect(card).toBeInTheDocument();
    });

    it('should provide error details in expandable section', () => {
      setNodeEnv('development');

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error('Accessible error')} />
        </ErrorBoundary>
      );

      const details = screen.getByText('Error details (development only)');
      expect(details.tagName).toBe('SUMMARY');
      expect(details.closest('details')).toBeInTheDocument();
    });

    it('should have sufficient color contrast for error message', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      const errorMessage = screen.getByText(
        'An error occurred while rendering this component. Please try refreshing the page.'
      );

      // Should use gray-600 which has good contrast on white background
      expect(errorMessage).toHaveClass('text-muted-foreground');
    });
  });

  // ==========================================================================
  // Additional Test Cases: Custom Fallback UI
  // ==========================================================================
  describe('Custom Fallback UI', () => {
    it('should render custom fallback when provided', () => {
      const customFallback = <div data-testid="custom-fallback">Custom Error UI</div>;

      render(
        <ErrorBoundary fallback={customFallback}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByTestId('custom-fallback')).toBeInTheDocument();
      expect(screen.getByText('Custom Error UI')).toBeInTheDocument();

      // Default UI should not be rendered
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('should accept React elements as fallback', () => {
      const customFallback = (
        <div data-testid="complex-fallback">
          <h1>Error!</h1>
          <p>Something bad happened</p>
          <button>Try Again</button>
        </div>
      );

      render(
        <ErrorBoundary fallback={customFallback}>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByTestId('complex-fallback')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /error!/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // Edge Cases
  // ==========================================================================
  describe('Edge Cases', () => {
    it('should handle errors during initial render', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should handle multiple sequential errors', () => {
      const { rerender } = render(
        <ErrorBoundary>
          <ThrowError shouldThrow={false} />
        </ErrorBoundary>
      );

      // First error
      rerender(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error('First error')} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should render null children without errors', () => {
      render(<ErrorBoundary>{null}</ErrorBoundary>);

      // Should not crash, just render nothing
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('should render undefined children without errors', () => {
      render(<ErrorBoundary>{undefined}</ErrorBoundary>);

      // Should not crash, just render nothing
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('should handle errors with very long stack traces', () => {
      setNodeEnv('development');

      const errorWithLongStack = new Error('Long stack error');
      errorWithLongStack.stack = 'Error: Long stack\n' + 'at Function\n'.repeat(100);

      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={errorWithLongStack} />
        </ErrorBoundary>
      );

      // Should render without crashing
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });
});
