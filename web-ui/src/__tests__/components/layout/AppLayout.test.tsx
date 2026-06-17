/**
 * AppLayout renders the login page bare — without the sidebar shell or pipeline
 * progress bar (issue #336) — and proactively guards protected routes (#651):
 * - a stored token → render the shell;
 * - no token + backend denies (auth required) → redirect to /login, no shell;
 * - no token + backend allows (auth disabled) → render the shell;
 * an unauthenticated visitor only ever sees a neutral loader, never the shell.
 */
import { render, screen, waitFor } from '@testing-library/react';
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
jest.mock('@/lib/api', () => ({
  checkAuthAccess: jest.fn(),
}));
import { isAuthenticated } from '@/lib/auth';
import { checkAuthAccess } from '@/lib/api';
const mockIsAuthenticated = isAuthenticated as jest.MockedFunction<typeof isAuthenticated>;
const mockCheckAuthAccess = checkAuthAccess as jest.MockedFunction<typeof checkAuthAccess>;

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
    mockCheckAuthAccess.mockResolvedValue('allowed');
  });

  it('renders the sidebar shell on a normal route when authenticated', async () => {
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    expect(await screen.findByTestId('app-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-bar')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
    // A stored token short-circuits the backend probe.
    expect(mockCheckAuthAccess).not.toHaveBeenCalled();
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

  it('redirects to /login without rendering the shell when the backend denies access', async () => {
    mockIsAuthenticated.mockReturnValue(false);
    mockCheckAuthAccess.mockResolvedValue('denied');
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/login'));
    expect(screen.queryByTestId('app-sidebar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('child')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders the shell without a token when auth is disabled (backend allows)', async () => {
    mockIsAuthenticated.mockReturnValue(false);
    mockCheckAuthAccess.mockResolvedValue('allowed');
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    expect(await screen.findByTestId('app-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('fails open (renders the shell) when the backend probe errors', async () => {
    mockIsAuthenticated.mockReturnValue(false);
    mockCheckAuthAccess.mockResolvedValue('error');
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    expect(await screen.findByTestId('app-sidebar')).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
