import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SessionCard } from '@/components/sessions/SessionCard';
import type { Session } from '@/types';

// ─── Fixtures ───────────────────────────────────────────────────────

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1234',
    state: 'active',
    workspace_path: '/home/user/projects/my-app',
    model: 'claude-sonnet-4-6',
    created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // 5 min ago
    ended_at: null,
    cost_usd: 0.012,
    agent_name: null,
    ...overrides,
  };
}

const defaultHandlers = {
  onEnd: jest.fn(),
};

function renderCard(sessionOverrides: Partial<Session> = {}, props: Partial<Parameters<typeof SessionCard>[0]> = {}) {
  const session = makeSession(sessionOverrides);
  return render(
    <SessionCard
      session={session}
      {...defaultHandlers}
      {...props}
    />
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Tests ──────────────────────────────────────────────────────────

describe('SessionCard', () => {
  it('renders the session short ID (last 8 chars)', () => {
    renderCard();
    expect(screen.getByText('eeee1234')).toBeInTheDocument();
  });

  it('renders the workspace basename', () => {
    renderCard();
    expect(screen.getByText('my-app')).toBeInTheDocument();
  });

  it('renders the model name', () => {
    renderCard();
    expect(screen.getByText('claude-sonnet-4-6')).toBeInTheDocument();
  });

  it('renders cost formatted as dollar amount', () => {
    renderCard({ cost_usd: 0.012 });
    expect(screen.getByText('$0.0120')).toBeInTheDocument();
  });

  it('shows green state dot for active sessions', () => {
    renderCard({ state: 'active' });
    const dot = screen.getByTestId('session-state-dot');
    expect(dot).toHaveClass('bg-green-500');
  });

  it('shows gray state dot for ended sessions', () => {
    renderCard({ state: 'ended' });
    const dot = screen.getByTestId('session-state-dot');
    expect(dot).toHaveClass('bg-gray-400');
  });

  it('shows gray state dot for paused sessions', () => {
    renderCard({ state: 'paused' });
    const dot = screen.getByTestId('session-state-dot');
    expect(dot).toHaveClass('bg-gray-400');
  });

  it('shows Resume button for active sessions', () => {
    renderCard({ state: 'active' });
    expect(screen.getByRole('link', { name: /resume/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /^view$/i })).not.toBeInTheDocument();
  });

  it('shows View button for ended sessions', () => {
    renderCard({ state: 'ended' });
    expect(screen.getByRole('link', { name: /view/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /resume/i })).not.toBeInTheDocument();
  });

  it('shows End button for active sessions', () => {
    renderCard({ state: 'active' });
    expect(screen.getByRole('button', { name: /end/i })).toBeInTheDocument();
  });

  it('hides End button for ended sessions', () => {
    renderCard({ state: 'ended' });
    expect(screen.queryByRole('button', { name: /end/i })).not.toBeInTheDocument();
  });

  it('opens a confirmation dialog before ending (does not call onEnd immediately)', async () => {
    const user = userEvent.setup();
    renderCard({ state: 'active' });
    await user.click(screen.getByRole('button', { name: /end/i }));
    // Dialog is open; onEnd must not fire until the user confirms.
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(defaultHandlers.onEnd).not.toHaveBeenCalled();
  });

  it('calls onEnd when the End action is confirmed in the dialog', async () => {
    const user = userEvent.setup();
    renderCard({ state: 'active' });
    await user.click(screen.getByRole('button', { name: /end/i }));
    const dialog = screen.getByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: /end session/i }));
    expect(defaultHandlers.onEnd).toHaveBeenCalledWith('aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1234');
  });

  it('does not call onEnd when the dialog is cancelled', async () => {
    const user = userEvent.setup();
    renderCard({ state: 'active' });
    await user.click(screen.getByRole('button', { name: /end/i }));
    const dialog = screen.getByRole('alertdialog');
    await user.click(within(dialog).getByRole('button', { name: /^keep$/i }));
    expect(defaultHandlers.onEnd).not.toHaveBeenCalled();
  });

  it('renders relative time for created_at', () => {
    renderCard();
    // date-fns formatDistanceToNow will produce something like "5 minutes ago"
    expect(screen.getByText(/minutes? ago/i)).toBeInTheDocument();
  });

  it('links Resume button to /sessions/[id]', () => {
    renderCard({ state: 'active' });
    const link = screen.getByRole('link', { name: /resume/i });
    expect(link).toHaveAttribute('href', '/sessions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1234');
  });

  it('links View button to /sessions/[id]', () => {
    renderCard({ state: 'ended' });
    const link = screen.getByRole('link', { name: /view/i });
    expect(link).toHaveAttribute('href', '/sessions/aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1234');
  });
});
