/**
 * Tests for HomePage Component
 * Feature: 011-project-creation-flow
 *
 * Tests the home page which displays the project list.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import HomePage from '../page';

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Mock ProtectedRoute to pass through children
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="protected-route">{children}</div>
  ),
}));

// Mock ProjectList component
jest.mock('@/components/ProjectList', () => {
  return function MockProjectList() {
    return <div data-testid="project-list">ProjectList Component</div>;
  };
});

describe('HomePage', () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    mockPush.mockClear();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });
  });

  describe('Page Structure', () => {
    test('renders wrapped in ProtectedRoute', () => {
      render(<HomePage />);

      expect(screen.getByTestId('protected-route')).toBeInTheDocument();
    });

    test('renders page heading', () => {
      render(<HomePage />);

      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Your Projects');
    });

    test('renders tagline', () => {
      render(<HomePage />);

      expect(screen.getByText(/ai coding agents that work autonomously while you sleep/i)).toBeInTheDocument();
    });

    test('renders ProjectList component', () => {
      render(<HomePage />);

      expect(screen.getByTestId('project-list')).toBeInTheDocument();
    });
  });

  describe('Responsive Layout', () => {
    test('has responsive container classes', () => {
      const { container } = render(<HomePage />);

      const mainElement = container.querySelector('main');
      expect(mainElement).toHaveClass('min-h-screen', 'bg-background');
    });

    test('has max-width container', () => {
      const { container } = render(<HomePage />);

      const contentDiv = container.querySelector('.max-w-7xl');
      expect(contentDiv).toBeInTheDocument();
    });
  });
});
