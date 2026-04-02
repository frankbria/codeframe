import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import SessionDetailPage from '@/app/sessions/[id]/page';
import { sessionsApi } from '@/lib/api';
import type { Session } from '@/types';

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('next/navigation', () => ({
  useParams: jest.fn(),
  useRouter: jest.fn(),
}));

jest.mock('swr');

jest.mock('@/lib/api', () => ({
  sessionsApi: {
    getOne: jest.fn(),
    end: jest.fn(),
    getMessages: jest.fn(),
  },
}));

jest.mock('@/components/sessions/AgentChatPanel', () => ({
  AgentChatPanel: ({
    sessionId,
    readOnly,
  }: {
    sessionId: string;
    readOnly?: boolean;
  }) => (
    <div
      data-testid="agent-chat-panel"
      data-session-id={sessionId}
      data-read-only={readOnly ? 'true' : 'false'}
    >
      {!readOnly && <textarea aria-label="Message input" />}
    </div>
  ),
}));

jest.mock('@/components/sessions/AgentTerminal', () => ({
  AgentTerminal: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="agent-terminal" data-session-id={sessionId} />
  ),
}));

jest.mock('@/components/sessions/SplitPane', () => ({
  SplitPane: ({
    left,
    right,
    storageKey,
  }: {
    left: React.ReactNode;
    right: React.ReactNode;
    storageKey?: string;
  }) => (
    <div data-testid="split-pane" data-storage-key={storageKey}>
      <div data-testid="split-pane-left">{left}</div>
      <div data-testid="split-pane-right">{right}</div>
    </div>
  ),
}));

const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockSessApiEnd = sessionsApi.end as jest.MockedFunction<typeof sessionsApi.end>;
const mockSessApiGetMessages = sessionsApi.getMessages as jest.MockedFunction<
  typeof sessionsApi.getMessages
>;

function swrResult(overrides: {
  data?: unknown;
  isLoading?: boolean;
  error?: unknown;
}): ReturnType<typeof useSWR> {
  return {
    data: overrides.data ?? undefined,
    isLoading: overrides.isLoading ?? false,
    error: overrides.error ?? null,
    mutate: jest.fn(),
    isValidating: false,
  } as unknown as ReturnType<typeof useSWR>;
}

const SESSION_ID = 'session-abc123def456';
const SHORT_ID = SESSION_ID.slice(-8);

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: SESSION_ID,
    state: 'active',
    workspace_path: '/home/user/myproject',
    model: 'claude-sonnet-4-6',
    created_at: '2026-04-01T10:00:00Z',
    ended_at: null,
    cost_usd: 0.0123,
    agent_name: null,
    ...overrides,
  };
}

const mockRouterPush = jest.fn();

function setupRouter() {
  mockUseRouter.mockReturnValue({
    push: mockRouterPush,
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
  } as ReturnType<typeof useRouter>);
}

function setupParams(id = SESSION_ID) {
  mockUseParams.mockReturnValue({ id });
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('SessionDetailPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupParams();
    setupRouter();
  });

  // ── Loading state ────────────────────────────────────────────────────

  it('shows loading skeleton while session data is fetching', () => {
    mockUseSWR.mockReturnValue(swrResult({ isLoading: true }));
    render(<SessionDetailPage />);
    expect(screen.getByTestId('session-detail-skeleton')).toBeInTheDocument();
  });

  // ── Active session ───────────────────────────────────────────────────

  it('renders header with back link for active session', () => {
    const session = makeSession();
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByRole('link', { name: /sessions/i })).toHaveAttribute('href', '/sessions');
  });

  it('renders session short ID in header', () => {
    const session = makeSession();
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByText(new RegExp(SHORT_ID))).toBeInTheDocument();
  });

  it('renders active state badge for active session', () => {
    const session = makeSession({ state: 'active' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('renders SplitPane with AgentChatPanel and AgentTerminal for active session', () => {
    const session = makeSession({ state: 'active' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByTestId('split-pane')).toBeInTheDocument();
    expect(screen.getByTestId('agent-chat-panel')).toBeInTheDocument();
    expect(screen.getByTestId('agent-terminal')).toBeInTheDocument();
  });

  it('passes session-specific storageKey to SplitPane', () => {
    const session = makeSession();
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByTestId('split-pane')).toHaveAttribute(
      'data-storage-key',
      `session-split-${SESSION_ID}`
    );
  });

  it('passes sessionId to AgentChatPanel and AgentTerminal', () => {
    const session = makeSession();
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByTestId('agent-chat-panel')).toHaveAttribute('data-session-id', SESSION_ID);
    expect(screen.getByTestId('agent-terminal')).toHaveAttribute('data-session-id', SESSION_ID);
  });

  it('renders input bar for active session (not read-only)', () => {
    const session = makeSession({ state: 'active' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(screen.getByTestId('agent-chat-panel')).toHaveAttribute('data-read-only', 'false');
  });

  // ── End Session ──────────────────────────────────────────────────────

  it('renders enabled End Session button for active session', () => {
    const session = makeSession({ state: 'active' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    const btn = screen.getByRole('button', { name: /end session/i });
    expect(btn).toBeEnabled();
  });

  it('calls sessionsApi.end and redirects to /sessions on End Session click', async () => {
    mockSessApiEnd.mockResolvedValue(undefined);
    const session = makeSession({ state: 'active' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    fireEvent.click(screen.getByRole('button', { name: /end session/i }));
    await waitFor(() => {
      expect(mockSessApiEnd).toHaveBeenCalledWith(SESSION_ID);
      expect(mockRouterPush).toHaveBeenCalledWith('/sessions');
    });
  });

  it('shows error message and re-enables button when sessionsApi.end rejects', async () => {
    mockSessApiEnd.mockRejectedValue(new Error('Network error'));
    const session = makeSession({ state: 'active' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    fireEvent.click(screen.getByRole('button', { name: /end session/i }));
    await waitFor(() => {
      expect(mockRouterPush).not.toHaveBeenCalled();
      expect(screen.getByText(/failed to end session/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /end session/i })).toBeEnabled();
    });
  });

  // ── Ended session ────────────────────────────────────────────────────

  it('renders ended state for ended session', () => {
    const session = makeSession({ state: 'ended', ended_at: '2026-04-01T11:00:00Z' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    mockSessApiGetMessages.mockResolvedValue([]);
    render(<SessionDetailPage />);
    // The badge shows the state and the banner also mentions 'ended'
    expect(screen.getAllByText(/ended/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders "session ended" banner for ended session', () => {
    const session = makeSession({ state: 'ended', ended_at: '2026-04-01T11:00:00Z' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    mockSessApiGetMessages.mockResolvedValue([]);
    render(<SessionDetailPage />);
    expect(screen.getByText(/this session has ended/i)).toBeInTheDocument();
  });

  it('does not render AgentTerminal for ended session', () => {
    const session = makeSession({ state: 'ended', ended_at: '2026-04-01T11:00:00Z' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    mockSessApiGetMessages.mockResolvedValue([]);
    render(<SessionDetailPage />);
    expect(screen.queryByTestId('agent-terminal')).not.toBeInTheDocument();
  });

  it('renders AgentChatPanel in read-only mode for ended session', () => {
    const session = makeSession({ state: 'ended', ended_at: '2026-04-01T11:00:00Z' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    mockSessApiGetMessages.mockResolvedValue([]);
    render(<SessionDetailPage />);
    expect(screen.getByTestId('agent-chat-panel')).toHaveAttribute('data-read-only', 'true');
  });

  it('renders disabled End Session button for ended session', () => {
    const session = makeSession({ state: 'ended', ended_at: '2026-04-01T11:00:00Z' });
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    mockSessApiGetMessages.mockResolvedValue([]);
    render(<SessionDetailPage />);
    const btn = screen.getByRole('button', { name: /end session/i });
    expect(btn).toBeDisabled();
  });

  // ── Error state ──────────────────────────────────────────────────────

  it('renders "Session not found" error when fetch returns 404-like error', () => {
    mockUseSWR.mockReturnValue(
      swrResult({ error: { status: 404, detail: 'Session not found' } })
    );
    render(<SessionDetailPage />);
    expect(screen.getByText(/session not found/i)).toBeInTheDocument();
    // Multiple back links exist (header + error body) — all point to /sessions
    const links = screen.getAllByRole('link', { name: /back to sessions/i });
    expect(links.length).toBeGreaterThanOrEqual(1);
    links.forEach((link) => expect(link).toHaveAttribute('href', '/sessions'));
  });

  it('renders generic error state for non-404 errors', () => {
    mockUseSWR.mockReturnValue(
      swrResult({ error: { status: 500, detail: 'Internal server error' } })
    );
    render(<SessionDetailPage />);
    expect(screen.getByText(/failed to load session/i)).toBeInTheDocument();
  });

  // ── Page title ───────────────────────────────────────────────────────

  it('includes session short ID in document title', () => {
    const session = makeSession();
    mockUseSWR.mockReturnValue(swrResult({ data: session }));
    render(<SessionDetailPage />);
    expect(document.title).toContain(SHORT_ID);
  });
});
