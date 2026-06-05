/**
 * AppSidebar must expose a Sign out control in its footer that calls
 * auth.logout() (issue #336). The sidebar only renders when a workspace is
 * selected, so we stub workspace storage to return a path.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { AppSidebar } from '@/components/layout/AppSidebar';

jest.mock('next/navigation', () => ({
  usePathname: () => '/tasks',
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: () => '/tmp/ws',
}));

// Avoid real network from SWR fetchers.
jest.mock('swr', () => ({
  __esModule: true,
  default: () => ({ data: undefined }),
}));

jest.mock('@/components/layout/NotificationCenter', () => ({
  NotificationCenter: () => <div data-testid="notification-center" />,
}));

const logoutMock = jest.fn();
jest.mock('@/lib/auth', () => ({
  logout: () => logoutMock(),
}));

beforeEach(() => {
  logoutMock.mockReset();
});

describe('AppSidebar logout control', () => {
  it('renders a Sign out button that calls logout()', () => {
    render(<AppSidebar />);
    const button = screen.getByRole('button', { name: /sign out/i });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);
    expect(logoutMock).toHaveBeenCalledTimes(1);
  });
});
