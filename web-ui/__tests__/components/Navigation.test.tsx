/**
 * Navigation Component Tests
 *
 * Tests navigation bar including logo link, auth states, and visibility rules.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { usePathname, useRouter } from 'next/navigation';
import Navigation from '@/components/Navigation';
import { useAuth } from '@/contexts/AuthContext';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
  useRouter: jest.fn(),
}));

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}));

describe('Navigation', () => {
  const mockRouter = {
    push: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue(mockRouter);
    (usePathname as jest.Mock).mockReturnValue('/');
  });

  describe('Logo Link', () => {
    it('renders CodeFRAME logo as a link', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      const logo = screen.getByText('CodeFRAME');
      expect(logo).toBeInTheDocument();
    });

    it('logo links to home page (project list)', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      const logoLink = screen.getByRole('link', { name: /CodeFRAME/i });
      expect(logoLink).toHaveAttribute('href', '/');
    });
  });

  describe('Visibility Rules', () => {
    it('does not render on login page', () => {
      (usePathname as jest.Mock).mockReturnValue('/login');
      (useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
        logout: jest.fn(),
      });

      const { container } = render(<Navigation />);

      expect(container.firstChild).toBeNull();
    });

    it('does not render on signup page', () => {
      (usePathname as jest.Mock).mockReturnValue('/signup');
      (useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
        logout: jest.fn(),
      });

      const { container } = render(<Navigation />);

      expect(container.firstChild).toBeNull();
    });

    it('renders on project list page', () => {
      (usePathname as jest.Mock).mockReturnValue('/');
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByRole('navigation')).toBeInTheDocument();
    });

    it('renders on project detail page', () => {
      (usePathname as jest.Mock).mockReturnValue('/projects/123');
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByRole('navigation')).toBeInTheDocument();
    });
  });

  describe('Authenticated State', () => {
    it('shows user menu when logged in', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com', name: 'Test User' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByTestId('user-menu')).toBeInTheDocument();
      expect(screen.getByText('Test User')).toBeInTheDocument();
    });

    it('shows email when name is not available', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByText('test@example.com')).toBeInTheDocument();
    });

    it('shows logout button when logged in', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByTestId('logout-button')).toBeInTheDocument();
    });

    it('calls logout and redirects to login on logout click', async () => {
      const mockLogout = jest.fn().mockResolvedValue(undefined);
      (useAuth as jest.Mock).mockReturnValue({
        user: { email: 'test@example.com' },
        isLoading: false,
        logout: mockLogout,
      });

      render(<Navigation />);

      fireEvent.click(screen.getByTestId('logout-button'));

      expect(mockLogout).toHaveBeenCalled();

      // Wait for async logout handler to complete and verify redirect
      await waitFor(() => {
        expect(mockRouter.push).toHaveBeenCalledWith('/login');
      });
    });
  });

  describe('Unauthenticated State', () => {
    it('shows login and signup links when not logged in', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByRole('link', { name: /Login/i })).toHaveAttribute('href', '/login');
      expect(screen.getByRole('link', { name: /Signup/i })).toHaveAttribute('href', '/signup');
    });

    it('does not show user menu when not logged in', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: false,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.queryByTestId('user-menu')).not.toBeInTheDocument();
    });
  });

  describe('Loading State', () => {
    it('shows loading indicator while auth is loading', () => {
      (useAuth as jest.Mock).mockReturnValue({
        user: null,
        isLoading: true,
        logout: jest.fn(),
      });

      render(<Navigation />);

      expect(screen.getByText(/Loading.../i)).toBeInTheDocument();
    });
  });
});
