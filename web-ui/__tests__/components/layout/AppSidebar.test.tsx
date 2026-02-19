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

// Mock SWR (used for blocker badge count)
jest.mock('swr', () => ({
  __esModule: true,
  default: () => ({ data: undefined, isLoading: false, error: undefined }),
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

  it('renders all 6 navigation items', () => {
    mockGetWorkspacePath.mockReturnValue('/home/user/projects/test');
    render(<AppSidebar />);

    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('PRD')).toBeInTheDocument();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
    expect(screen.getByText('Execution')).toBeInTheDocument();
    expect(screen.getByText('Blockers')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
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
});
