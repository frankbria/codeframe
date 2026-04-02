import { render, screen } from '@testing-library/react';
import { AppSidebar } from '@/components/layout/AppSidebar';

// Mock next/link
jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
    className,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) {
    return (
      <a href={href} className={className}>
        {children}
      </a>
    );
  };
});

// Mock workspace-storage
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
}));

// Mock SWR (used for blocker + session badge counts)
const mockSWRData: Record<string, unknown> = {};
jest.mock('swr', () => ({
  __esModule: true,
  default: (key: string | null) => ({
    data: key ? mockSWRData[key] : undefined,
    isLoading: false,
    error: undefined,
  }),
}));

import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
const mockGetWorkspacePath = getSelectedWorkspacePath as jest.MockedFunction<
  typeof getSelectedWorkspacePath
>;

// Mock usePathname (override the global mock from jest.setup.js)
const mockUsePathname = jest.fn(() => '/');
jest.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

describe('AppSidebar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUsePathname.mockReturnValue('/');
    // Clear SWR mock data to prevent cross-test cache leakage
    Object.keys(mockSWRData).forEach((k) => delete mockSWRData[k]);
  });

  it('renders nothing when no workspace is selected', () => {
    mockGetWorkspacePath.mockReturnValue(null);
    const { container } = render(<AppSidebar />);
    expect(container.firstChild).toBeNull();
  });

  it('renders sidebar when workspace is selected', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    render(<AppSidebar />);
    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('PRD')).toBeInTheDocument();
  });

  it('renders all 8 navigation items', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    render(<AppSidebar />);

    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('PRD')).toBeInTheDocument();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
    expect(screen.getByText('Execution')).toBeInTheDocument();
    expect(screen.getByText('Sessions')).toBeInTheDocument();
    expect(screen.getByText('Blockers')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('Proof')).toBeInTheDocument();
  });

  it('renders enabled items as links', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    render(<AppSidebar />);

    expect(screen.getByRole('link', { name: /workspace/i })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: /prd/i })).toHaveAttribute('href', '/prd');
  });

  it('renders all navigation items as links when enabled', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    render(<AppSidebar />);

    // All nav items are enabled including Review
    expect(screen.getByRole('link', { name: /^tasks$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^execution$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^blockers$/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /^review$/i })).toBeInTheDocument();
  });

  it('highlights the active route', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    mockUsePathname.mockReturnValue('/prd');
    render(<AppSidebar />);

    const prdLink = screen.getByRole('link', { name: /prd/i });
    expect(prdLink.className).toContain('bg-accent');
  });

  it('does not highlight inactive routes', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    mockUsePathname.mockReturnValue('/prd');
    render(<AppSidebar />);

    const workspaceLink = screen.getByRole('link', { name: /workspace/i });
    // Active items have 'bg-accent' without 'hover:' prefix; inactive have 'hover:bg-accent/50'
    expect(workspaceLink.className).not.toMatch(/(?<!\w)bg-accent(?!\/)/);
  });

  // ─── Sessions nav entry tests ──────────────────────────────────────

  it('renders Sessions nav link pointing to /sessions', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    render(<AppSidebar />);
    const sessionsLink = screen.getByRole('link', { name: /sessions/i });
    expect(sessionsLink).toHaveAttribute('href', '/sessions');
  });

  it('shows active session count badge when there are active sessions', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    mockSWRData['/api/v2/sessions?path=%2Fhome%2Fuser%2Fprojects%2Ftest&state=active'] = {
      sessions: [
        { id: 's1', state: 'active' },
        { id: 's2', state: 'active' },
      ],
      total: 2,
    };
    render(<AppSidebar />);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('does not show session badge when count is 0', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    mockSWRData['/api/v2/sessions?path=%2Fhome%2Fuser%2Fprojects%2Ftest&state=active'] = {
      sessions: [],
      total: 0,
    };
    render(<AppSidebar />);
    // With 0 sessions and no blockers, no badge spans should be present
    const sessionsLink = screen.getByRole('link', { name: /sessions/i });
    expect(sessionsLink.querySelector('.bg-muted')).toBeNull();
  });
});
