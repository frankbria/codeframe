/**
 * Home Page Unit Tests
 *
 * Tests the home page component which displays the project list
 * and requires authentication via ProtectedRoute.
 */

import { render, screen } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import HomePage from '@/app/page';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Mock ProtectedRoute to pass through children when authenticated
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="protected-route">{children}</div>
  ),
}));

// Mock ProjectList component
jest.mock('@/components/ProjectList', () => ({
  __esModule: true,
  default: () => <div data-testid="project-list">ProjectList Component</div>,
}));

describe('HomePage', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
  });

  describe('Rendering', () => {
    it('renders the page wrapped in ProtectedRoute', () => {
      render(<HomePage />);

      expect(screen.getByTestId('protected-route')).toBeInTheDocument();
    });

    it('displays page header with title', () => {
      render(<HomePage />);

      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Your Projects');
    });

    it('displays page subtitle', () => {
      render(<HomePage />);

      expect(screen.getByText(/AI coding agents that work autonomously/i)).toBeInTheDocument();
    });

    it('renders the ProjectList component', () => {
      render(<HomePage />);

      expect(screen.getByTestId('project-list')).toBeInTheDocument();
    });
  });

  describe('Layout', () => {
    it('uses background color from design system', () => {
      render(<HomePage />);

      const main = screen.getByRole('main');
      expect(main).toHaveClass('bg-background');
    });

    it('has responsive container with max width', () => {
      render(<HomePage />);

      const container = screen.getByRole('main').firstChild;
      expect(container).toHaveClass('max-w-7xl');
    });
  });

  describe('Accessibility', () => {
    it('has proper heading hierarchy', () => {
      render(<HomePage />);

      const h1 = screen.getByRole('heading', { level: 1 });
      expect(h1).toBeInTheDocument();
    });

    it('has semantic main element', () => {
      render(<HomePage />);

      expect(screen.getByRole('main')).toBeInTheDocument();
    });
  });
});
