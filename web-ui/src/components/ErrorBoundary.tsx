/**
 * ErrorBoundary Component (T133)
 * Catches React errors in child components and displays fallback UI
 *
 * Used to wrap AgentStateProvider to handle state management failures gracefully
 */

'use client';

import React, { Component, ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error boundary component that catches and handles React errors
 *
 * @example
 * ```tsx
 * <ErrorBoundary fallback={<div>Error occurred</div>}>
 *   <MyComponent />
 * </ErrorBoundary>
 * ```
 */
class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error to console in development
    if (process.env.NODE_ENV === 'development') {
      console.error('[ErrorBoundary] Caught error:', error);
      console.error('[ErrorBoundary] Error info:', errorInfo);
    }

    // Call optional onError callback
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback UI if provided
      if (this.props.fallback) {
        // Clone fallback element and inject error prop
        return (
          <div data-testid="error-boundary">
            {React.cloneElement(this.props.fallback as React.ReactElement, {
              error: this.state.error,
            })}
          </div>
        );
      }

      // Default fallback UI
      return (
        <div className="min-h-screen bg-muted flex items-center justify-center p-4" data-testid="error-boundary">
          <div className="max-w-md w-full bg-card rounded-lg shadow-lg p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-destructive/10 rounded-full flex items-center justify-center">
                <span className="text-2xl text-destructive">⚠</span>
              </div>
              <h2 className="text-xl font-semibold text-foreground">
                Something went wrong
              </h2>
            </div>

            <p className="text-muted-foreground mb-4">
              An error occurred while rendering this component. Please try refreshing the page.
            </p>

            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="mb-4">
                <summary className="cursor-pointer text-sm font-medium text-foreground mb-2">
                  Error details (development only)
                </summary>
                <pre className="text-xs bg-muted p-3 rounded border border-border overflow-auto">
                  {this.state.error.toString()}
                  {this.state.error.stack && `\n\n${this.state.error.stack}`}
                </pre>
              </details>
            )}

            <button
              onClick={() => window.location.reload()}
              className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
            >
              Refresh Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
