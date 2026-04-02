import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SessionListView } from '@/components/sessions/SessionListView';
import type { SessionListResponse } from '@/types';

// ─── Mocks ──────────────────────────────────────────────────────────

jest.mock('swr', () => {
  const actual = jest.requireActual('swr');
  return {
    ...actual,
    __esModule: true,
    default: jest.fn(),
  };
});

jest.mock('@/lib/api', () => ({
  sessionsApi: {
    getAll: jest.fn(),
    create: jest.fn(),
    end: jest.fn(),
  },
}));

const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

import useSWR from 'swr';
const mockUseSWR = useSWR as jest.Mock;

// ─── Fixtures ───────────────────────────────────────────────────────

const mockSessions: SessionListResponse = {
  sessions: [
    {
      id: 'aaaa-1111-active',
      state: 'active',
      workspace_path: '/home/user/projects/my-app',
      model: 'claude-sonnet-4-6',
      created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      ended_at: null,
      cost_usd: 0.05,
      agent_name: null,
    },
    {
      id: 'bbbb-2222-ended',
      state: 'ended',
      workspace_path: '/home/user/projects/my-app',
      model: 'claude-opus-4-6',
      created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
      ended_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      cost_usd: 1.23,
      agent_name: null,
    },
  ],
  total: 2,
};

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Tests ──────────────────────────────────────────────────────────

describe('SessionListView', () => {
  it('shows loading skeletons while data is loading', () => {
    mockUseSWR.mockReturnValue({ data: undefined, isLoading: true, error: undefined, mutate: jest.fn() });
    render(<SessionListView workspacePath="/test" />);
    const skeletons = screen.getAllByTestId('session-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(2);
  });

  it('shows empty state when no sessions exist', () => {
    mockUseSWR.mockReturnValue({
      data: { sessions: [], total: 0 },
      isLoading: false,
      error: undefined,
      mutate: jest.fn(),
    });
    render(<SessionListView workspacePath="/test" />);
    expect(screen.getByText(/no sessions yet/i)).toBeInTheDocument();
  });

  it('renders session cards for each session', () => {
    mockUseSWR.mockReturnValue({
      data: mockSessions,
      isLoading: false,
      error: undefined,
      mutate: jest.fn(),
    });
    render(<SessionListView workspacePath="/test" />);
    // Short IDs (last 8 chars) from our fixtures
    expect(screen.getByText('1-active')).toBeInTheDocument();
    expect(screen.getByText('22-ended')).toBeInTheDocument();
  });

  it('sorts active sessions before ended sessions', () => {
    const reversedSessions: SessionListResponse = {
      sessions: [...mockSessions.sessions].reverse(),
      total: 2,
    };
    mockUseSWR.mockReturnValue({
      data: reversedSessions,
      isLoading: false,
      error: undefined,
      mutate: jest.fn(),
    });
    render(<SessionListView workspacePath="/test" />);
    // Active card should appear first regardless of input order
    const shortIds = screen.getAllByText(/1-active|22-ended/);
    expect(shortIds[0]).toHaveTextContent('1-active');
  });

  it('filters sessions by search query matching ID', async () => {
    const user = userEvent.setup();
    mockUseSWR.mockReturnValue({
      data: mockSessions,
      isLoading: false,
      error: undefined,
      mutate: jest.fn(),
    });
    render(<SessionListView workspacePath="/test" />);
    const searchInput = screen.getByPlaceholderText(/search/i);
    await user.type(searchInput, 'active');
    expect(screen.getByText('1-active')).toBeInTheDocument();
    expect(screen.queryByText('22-ended')).not.toBeInTheDocument();
  });

  it('shows + New Session button', () => {
    mockUseSWR.mockReturnValue({
      data: mockSessions,
      isLoading: false,
      error: undefined,
      mutate: jest.fn(),
    });
    render(<SessionListView workspacePath="/test" />);
    expect(screen.getByRole('button', { name: /new session/i })).toBeInTheDocument();
  });

  it('shows error state with retry button', () => {
    const mutate = jest.fn();
    mockUseSWR.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: { detail: 'Failed to fetch' },
      mutate,
    });
    render(<SessionListView workspacePath="/test" />);
    expect(screen.getByText(/failed to fetch/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
