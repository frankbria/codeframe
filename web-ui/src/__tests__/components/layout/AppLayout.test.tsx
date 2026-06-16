/**
 * AppLayout renders the login page bare — without the sidebar shell or pipeline
 * progress bar (issue #336) — and proactively guards protected routes: an
 * unauthenticated visitor is redirected to /login and only ever sees a neutral
 * loader, never the shell (issue #651).
 */
import { render, screen } from '@testing-library/react';
import { AppLayout } from '@/components/layout/AppLayout';

let mockPathname = '/tasks';
const mockReplace = jest.fn();
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ replace: mockReplace, push: jest.fn(), prefetch: jest.fn() }),
}));

jest.mock('@/lib/auth', () => ({
  isAuthenticated: jest.fn(),
}));
import { isAuthenticated } from '@/lib/auth';
const mockIsAuthenticated = isAuthenticated as jest.MockedFunction<typeof isAuthenticated>;

jest.mock('@/components/layout/AppSidebar', () => ({
  AppSidebar: () => <aside data-testid="app-sidebar" />,
}));
jest.mock('@/components/layout/PipelineProgressBar', () => ({
  PipelineProgressBar: () => <div data-testid="pipeline-bar" />,
}));

describe('AppLayout', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPathname = '/tasks';
    mockIsAuthenticated.mockReturnValue(true);
  });

  it('renders the sidebar shell on a normal route when authenticated', () => {
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    expect(screen.getByTestId('app-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-bar')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('renders bare (no sidebar/pipeline bar) on /login', () => {
    mockPathname = '/login';
    mockIsAuthenticated.mockReturnValue(false);
    render(
      <AppLayout>
        <div data-testid="child">login</div>
      </AppLayout>
    );
    expect(screen.queryByTestId('app-sidebar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pipeline-bar')).not.toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('redirects an unauthenticated visitor to /login without rendering the shell', () => {
    mockPathname = '/tasks';
    mockIsAuthenticated.mockReturnValue(false);
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    expect(mockReplace).toHaveBeenCalledWith('/login');
    expect(screen.queryByTestId('app-sidebar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('child')).not.toBeInTheDocument();
    // Neutral loader shown instead of the shell (no flicker).
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
