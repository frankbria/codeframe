import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TaskCard } from '@/components/tasks/TaskCard';
import type { Task } from '@/types';

// ─── Fixtures ───────────────────────────────────────────────────────

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    title: 'Implement login',
    description: 'Build the user login form with validation.',
    status: 'READY',
    priority: 1,
    depends_on: [],
    estimated_hours: 4,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

const defaultHandlers = {
  onToggleSelect: jest.fn(),
  onClick: jest.fn(),
  onExecute: jest.fn(),
  onMarkReady: jest.fn(),
  onStop: jest.fn(),
  onReset: jest.fn(),
};

function renderCard(taskOverrides: Partial<Task> = {}, props: Partial<Parameters<typeof TaskCard>[0]> = {}) {
  const task = makeTask(taskOverrides);
  return render(
    <TaskCard
      task={task}
      selectionMode={false}
      selected={false}
      {...defaultHandlers}
      {...props}
    />
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Tests ──────────────────────────────────────────────────────────

describe('TaskCard', () => {
  it('renders task title and description', () => {
    renderCard();
    expect(screen.getByText('Implement login')).toBeInTheDocument();
    expect(screen.getByText('Build the user login form with validation.')).toBeInTheDocument();
  });

  it('renders status badge with correct label', () => {
    renderCard({ status: 'IN_PROGRESS' });
    expect(screen.getByText('In Progress')).toBeInTheDocument();
  });

  it('shows Execute button for READY tasks', () => {
    renderCard({ status: 'READY' });
    expect(screen.getByRole('button', { name: /execute/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /mark ready/i })).not.toBeInTheDocument();
  });

  it('shows Mark Ready button for BACKLOG tasks', () => {
    renderCard({ status: 'BACKLOG' });
    expect(screen.getByRole('button', { name: /mark ready/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
  });

  it('hides action buttons for non-actionable statuses', () => {
    renderCard({ status: 'DONE' });
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /mark ready/i })).not.toBeInTheDocument();
  });

  it('shows dependency indicator when task has dependencies', () => {
    renderCard({ depends_on: ['dep-1', 'dep-2'] });
    expect(screen.getByTitle('Depends on 2 task(s)')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('hides dependency indicator when task has no dependencies', () => {
    renderCard({ depends_on: [] });
    expect(screen.queryByTitle(/depends on/i)).not.toBeInTheDocument();
  });

  it('shows checkbox in selection mode', () => {
    renderCard({}, { selectionMode: true });
    expect(screen.getByRole('checkbox', { name: /select implement login/i })).toBeInTheDocument();
  });

  it('hides checkbox when not in selection mode', () => {
    renderCard({}, { selectionMode: false });
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('calls onClick when card is clicked', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(screen.getByText('Implement login'));
    expect(defaultHandlers.onClick).toHaveBeenCalledWith('task-1');
  });

  it('calls onExecute without triggering onClick', async () => {
    const user = userEvent.setup();
    renderCard({ status: 'READY' });
    await user.click(screen.getByRole('button', { name: /execute/i }));
    expect(defaultHandlers.onExecute).toHaveBeenCalledWith('task-1');
    expect(defaultHandlers.onClick).not.toHaveBeenCalled();
  });

  it('calls onMarkReady without triggering onClick', async () => {
    const user = userEvent.setup();
    renderCard({ status: 'BACKLOG' });
    await user.click(screen.getByRole('button', { name: /mark ready/i }));
    expect(defaultHandlers.onMarkReady).toHaveBeenCalledWith('task-1');
    expect(defaultHandlers.onClick).not.toHaveBeenCalled();
  });

  it('has accessible role, tabindex, and aria-label', () => {
    renderCard();
    const card = screen.getByRole('button', { name: /view details for implement login/i });
    expect(card).toBeInTheDocument();
    expect(card).toHaveAttribute('tabindex', '0');
  });

  it('triggers onClick on Enter key press', async () => {
    const user = userEvent.setup();
    renderCard();
    const card = screen.getByRole('button', { name: /view details for implement login/i });
    card.focus();
    await user.keyboard('{Enter}');
    expect(defaultHandlers.onClick).toHaveBeenCalledWith('task-1');
  });

  it('triggers onClick on Space key press', async () => {
    const user = userEvent.setup();
    renderCard();
    const card = screen.getByRole('button', { name: /view details for implement login/i });
    card.focus();
    await user.keyboard(' ');
    expect(defaultHandlers.onClick).toHaveBeenCalledWith('task-1');
  });

  it('renders all status variants correctly', () => {
    const statuses = ['BACKLOG', 'READY', 'IN_PROGRESS', 'DONE', 'BLOCKED', 'FAILED'] as const;
    const labels = ['Backlog', 'Ready', 'In Progress', 'Done', 'Blocked', 'Failed'];

    statuses.forEach((status, i) => {
      const { unmount } = renderCard({ status });
      expect(screen.getByText(labels[i])).toBeInTheDocument();
      unmount();
    });
  });

  // ─── Stop / Reset action tests ──────────────────────────────────────

  it('shows Stop button for IN_PROGRESS tasks', () => {
    renderCard({ status: 'IN_PROGRESS' });
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });

  it('does not show Stop button for non-IN_PROGRESS tasks', () => {
    renderCard({ status: 'READY' });
    expect(screen.queryByRole('button', { name: /stop/i })).not.toBeInTheDocument();
  });

  it('calls onStop without triggering onClick', async () => {
    const user = userEvent.setup();
    renderCard({ status: 'IN_PROGRESS' });
    await user.click(screen.getByRole('button', { name: /stop/i }));
    expect(defaultHandlers.onStop).toHaveBeenCalledWith('task-1');
    expect(defaultHandlers.onClick).not.toHaveBeenCalled();
  });

  it('shows Reset button for FAILED tasks', () => {
    renderCard({ status: 'FAILED' });
    expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument();
  });

  it('does not show Reset button for non-FAILED tasks', () => {
    renderCard({ status: 'READY' });
    expect(screen.queryByRole('button', { name: /reset/i })).not.toBeInTheDocument();
  });

  it('calls onReset without triggering onClick', async () => {
    const user = userEvent.setup();
    renderCard({ status: 'FAILED' });
    await user.click(screen.getByRole('button', { name: /reset/i }));
    expect(defaultHandlers.onReset).toHaveBeenCalledWith('task-1');
    expect(defaultHandlers.onClick).not.toHaveBeenCalled();
  });

  it('Stop button has destructive ghost styling', () => {
    renderCard({ status: 'IN_PROGRESS' });
    const stopBtn = screen.getByRole('button', { name: /stop/i });
    expect(stopBtn).toHaveClass('text-destructive');
  });

  // ─── Loading state tests ──────────────────────────────────────────

  it('shows loading spinner instead of action button when isLoading', () => {
    renderCard({ status: 'IN_PROGRESS' }, { isLoading: true });
    // Should show spinner, not the Stop button
    expect(screen.queryByRole('button', { name: /stop/i })).not.toBeInTheDocument();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  it('shows action buttons when isLoading is false', () => {
    renderCard({ status: 'IN_PROGRESS' }, { isLoading: false });
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });

  it('shows loading spinner for READY task when isLoading', () => {
    renderCard({ status: 'READY' }, { isLoading: true });
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  it('shows loading spinner for FAILED task when isLoading', () => {
    renderCard({ status: 'FAILED' }, { isLoading: true });
    expect(screen.queryByRole('button', { name: /reset/i })).not.toBeInTheDocument();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });
});
