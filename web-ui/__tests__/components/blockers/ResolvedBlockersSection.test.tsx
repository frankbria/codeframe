import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResolvedBlockersSection } from '@/components/blockers/ResolvedBlockersSection';
import type { Blocker } from '@/types';

// ── Fixtures ──────────────────────────────────────────────────────────

function makeBlocker(overrides: Partial<Blocker> = {}): Blocker {
  return {
    id: 'blocker-1',
    workspace_id: 'ws-1',
    task_id: 'task-1',
    question: 'Which database should we use?',
    answer: 'Use PostgreSQL for persistence.',
    status: 'RESOLVED',
    created_at: '2026-02-19T10:00:00Z',
    answered_at: '2026-02-19T10:05:00Z',
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────

describe('ResolvedBlockersSection', () => {
  it('renders nothing when blockers array is empty', () => {
    const { container } = render(
      <ResolvedBlockersSection blockers={[]} />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders the toggle button with correct count', () => {
    const blockers = [
      makeBlocker({ id: 'b-1' }),
      makeBlocker({ id: 'b-2', question: 'What auth provider?' }),
    ];

    render(<ResolvedBlockersSection blockers={blockers} />);

    const button = screen.getByRole('button', { name: /resolved blockers \(2\)/i });
    expect(button).toBeInTheDocument();
  });

  it('is collapsed by default', () => {
    render(
      <ResolvedBlockersSection blockers={[makeBlocker()]} />
    );

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-expanded', 'false');

    // The list region should be hidden (JSDOM doesn't compute CSS from class names)
    const list = screen.getByTestId('resolved-blockers-list');
    expect(list).toHaveClass('hidden');
  });

  it('expands when toggle button is clicked', async () => {
    const user = userEvent.setup();
    const blocker = makeBlocker();

    render(<ResolvedBlockersSection blockers={[blocker]} />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(button).toHaveAttribute('aria-expanded', 'true');

    const list = screen.getByTestId('resolved-blockers-list');
    expect(list).not.toHaveClass('hidden');
    expect(screen.getByText('Which database should we use?')).toBeInTheDocument();
    expect(screen.getByText('Use PostgreSQL for persistence.')).toBeInTheDocument();
  });

  it('collapses when toggle button is clicked again', async () => {
    const user = userEvent.setup();

    render(<ResolvedBlockersSection blockers={[makeBlocker()]} />);

    const button = screen.getByRole('button');
    await user.click(button); // expand
    expect(button).toHaveAttribute('aria-expanded', 'true');

    await user.click(button); // collapse
    expect(button).toHaveAttribute('aria-expanded', 'false');

    const list = screen.getByTestId('resolved-blockers-list');
    expect(list).toHaveClass('hidden');
  });

  it('shows RESOLVED badge for RESOLVED blockers', async () => {
    const user = userEvent.setup();
    const blocker = makeBlocker({ status: 'RESOLVED' });

    render(<ResolvedBlockersSection blockers={[blocker]} />);
    await user.click(screen.getByRole('button'));

    expect(screen.getByText('RESOLVED')).toBeInTheDocument();
  });

  it('shows ANSWERED badge for ANSWERED blockers', async () => {
    const user = userEvent.setup();
    const blocker = makeBlocker({ status: 'ANSWERED' });

    render(<ResolvedBlockersSection blockers={[blocker]} />);
    await user.click(screen.getByRole('button'));

    expect(screen.getByText('ANSWERED')).toBeInTheDocument();
  });

  it('displays task ID for each blocker', async () => {
    const user = userEvent.setup();
    const blocker = makeBlocker({ task_id: 'task-42' });

    render(<ResolvedBlockersSection blockers={[blocker]} />);
    await user.click(screen.getByRole('button'));

    expect(screen.getByText('task-42')).toBeInTheDocument();
  });

  it('displays relative time from answered_at when available', async () => {
    const user = userEvent.setup();
    // Set answered_at to 2 hours ago
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    const blocker = makeBlocker({ answered_at: twoHoursAgo });

    render(<ResolvedBlockersSection blockers={[blocker]} />);
    await user.click(screen.getByRole('button'));

    expect(screen.getByText('2h ago')).toBeInTheDocument();
  });

  it('falls back to created_at when answered_at is null', async () => {
    const user = userEvent.setup();
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    const blocker = makeBlocker({ answered_at: null, created_at: fiveMinAgo });

    render(<ResolvedBlockersSection blockers={[blocker]} />);
    await user.click(screen.getByRole('button'));

    expect(screen.getByText('5m ago')).toBeInTheDocument();
  });

  it('renders multiple blockers when expanded', async () => {
    const user = userEvent.setup();
    const blockers = [
      makeBlocker({ id: 'b-1', question: 'First question?', answer: 'First answer.' }),
      makeBlocker({ id: 'b-2', question: 'Second question?', answer: 'Second answer.' }),
      makeBlocker({ id: 'b-3', question: 'Third question?', answer: 'Third answer.' }),
    ];

    render(<ResolvedBlockersSection blockers={blockers} />);
    await user.click(screen.getByRole('button'));

    expect(screen.getByText('First question?')).toBeInTheDocument();
    expect(screen.getByText('Second question?')).toBeInTheDocument();
    expect(screen.getByText('Third question?')).toBeInTheDocument();
    expect(screen.getByText('First answer.')).toBeInTheDocument();
    expect(screen.getByText('Second answer.')).toBeInTheDocument();
    expect(screen.getByText('Third answer.')).toBeInTheDocument();
  });

  it('has the correct data-testid on the section', () => {
    render(<ResolvedBlockersSection blockers={[makeBlocker()]} />);

    expect(screen.getByTestId('resolved-blockers-section')).toBeInTheDocument();
  });

  it('has aria-controls on the toggle button pointing to list', () => {
    render(<ResolvedBlockersSection blockers={[makeBlocker()]} />);

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-controls', 'resolved-blockers-list');
  });

  it('renders the answer in a quoted style container', async () => {
    const user = userEvent.setup();
    const blocker = makeBlocker({ answer: 'Use PostgreSQL.' });

    render(<ResolvedBlockersSection blockers={[blocker]} />);
    await user.click(screen.getByRole('button'));

    const answerEl = screen.getByText('Use PostgreSQL.');
    // The answer should be in a container with left border styling
    expect(answerEl.closest('[class*="border-l-2"]')).toBeInTheDocument();
  });
});
