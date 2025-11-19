/**
 * Tests for Spinner Component
 * Feature: 011-project-creation-flow (User Story 5)
 * Sprint: 9.5 - Critical UX Fixes
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { Spinner } from '../Spinner';

describe('Spinner', () => {
  test('renders with default medium size', () => {
    render(<Spinner />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toBeInTheDocument();
    expect(spinner).toHaveClass('w-8', 'h-8', 'border-4');
  });

  test('renders with small size', () => {
    render(<Spinner size="sm" />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveClass('w-4', 'h-4', 'border-2');
  });

  test('renders with large size', () => {
    render(<Spinner size="lg" />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveClass('w-12', 'h-12', 'border-4');
  });

  test('defaults to medium size for invalid size values', () => {
    // @ts-expect-error - Testing runtime fallback for invalid size
    render(<Spinner size="invalid" />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveClass('w-8', 'h-8', 'border-4');
  });

  test('has correct accessibility attributes', () => {
    render(<Spinner />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveAttribute('role', 'status');
    expect(spinner).toHaveAttribute('aria-label', 'Loading');
  });

  test('has spinning animation class', () => {
    render(<Spinner />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveClass('animate-spin');
  });

  test('has correct color classes', () => {
    render(<Spinner />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveClass('border-blue-600', 'border-t-transparent');
  });

  test('has rounded-full class', () => {
    render(<Spinner />);

    const spinner = screen.getByTestId('spinner');
    expect(spinner).toHaveClass('rounded-full');
  });
});
