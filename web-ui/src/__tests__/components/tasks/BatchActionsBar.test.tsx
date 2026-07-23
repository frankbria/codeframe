import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BatchActionsBar } from '@/components/tasks/BatchActionsBar';
import type { Task } from '@/types';

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    title: 'Test Task',
    description: 'A test task',
    status: 'READY',
    priority: 1,
    depends_on: [],
    ...overrides,
  };
}

const defaultProps = {
  selectionMode: true,
  onToggleSelectionMode: jest.fn(),
  selectedCount: 0,
  strategy: 'serial' as const,
  onStrategyChange: jest.fn(),
  onExecuteBatch: jest.fn(),
  onClearSelection: jest.fn(),
  isExecuting: false,
  selectedTasks: [] as Task[],
  onStopBatch: jest.fn(),
  onResetBatch: jest.fn(),
  isStoppingBatch: false,
  isResettingBatch: false,
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('BatchActionsBar', () => {
  it('shows Batch button when not in selection mode', () => {
    render(<BatchActionsBar {...defaultProps} selectionMode={false} />);
    expect(screen.getByRole('button', { name: /batch/i })).toBeInTheDocument();
  });

  it('shows Cancel button when in selection mode', () => {
    render(<BatchActionsBar {...defaultProps} selectionMode={true} />);
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('shows Execute button with count when READY tasks are selected', () => {
    const selectedTasks = [
      makeTask({ id: 't1', status: 'READY' }),
      makeTask({ id: 't2', status: 'READY' }),
    ];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={2}
        selectedTasks={selectedTasks}
      />
    );
    expect(screen.getByRole('button', { name: /execute 2/i })).toBeInTheDocument();
  });

  it('shows Stop button with count when IN_PROGRESS tasks are selected', () => {
    const selectedTasks = [
      makeTask({ id: 't1', status: 'IN_PROGRESS' }),
      makeTask({ id: 't2', status: 'IN_PROGRESS' }),
      makeTask({ id: 't3', status: 'READY' }),
    ];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={3}
        selectedTasks={selectedTasks}
      />
    );
    expect(screen.getByRole('button', { name: /stop 2/i })).toBeInTheDocument();
  });

  it('shows Reset button with count when FAILED tasks are selected', () => {
    const selectedTasks = [
      makeTask({ id: 't1', status: 'FAILED' }),
      makeTask({ id: 't2', status: 'FAILED' }),
      makeTask({ id: 't3', status: 'FAILED' }),
    ];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={3}
        selectedTasks={selectedTasks}
      />
    );
    expect(screen.getByRole('button', { name: /reset 3/i })).toBeInTheDocument();
  });

  it('shows multiple action buttons for mixed selection', () => {
    const selectedTasks = [
      makeTask({ id: 't1', status: 'READY' }),
      makeTask({ id: 't2', status: 'IN_PROGRESS' }),
      makeTask({ id: 't3', status: 'FAILED' }),
    ];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={3}
        selectedTasks={selectedTasks}
      />
    );
    expect(screen.getByRole('button', { name: /execute 1/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /stop 1/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset 1/i })).toBeInTheDocument();
  });

  it('calls onStopBatch when Stop button is clicked', async () => {
    const user = userEvent.setup();
    const selectedTasks = [makeTask({ id: 't1', status: 'IN_PROGRESS' })];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={1}
        selectedTasks={selectedTasks}
      />
    );
    await user.click(screen.getByRole('button', { name: /stop 1/i }));
    expect(defaultProps.onStopBatch).toHaveBeenCalledTimes(1);
  });

  it('calls onResetBatch when Reset button is clicked', async () => {
    const user = userEvent.setup();
    const selectedTasks = [makeTask({ id: 't1', status: 'FAILED' })];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={1}
        selectedTasks={selectedTasks}
      />
    );
    await user.click(screen.getByRole('button', { name: /reset 1/i }));
    expect(defaultProps.onResetBatch).toHaveBeenCalledTimes(1);
  });

  it('disables Stop button when isStoppingBatch is true', () => {
    const selectedTasks = [makeTask({ id: 't1', status: 'IN_PROGRESS' })];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={1}
        selectedTasks={selectedTasks}
        isStoppingBatch={true}
      />
    );
    expect(screen.getByRole('button', { name: /stop/i })).toBeDisabled();
  });

  it('disables Reset button when isResettingBatch is true', () => {
    const selectedTasks = [makeTask({ id: 't1', status: 'FAILED' })];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={1}
        selectedTasks={selectedTasks}
        isResettingBatch={true}
      />
    );
    expect(screen.getByRole('button', { name: /reset/i })).toBeDisabled();
  });

  it('shows strategy selector only when READY tasks are selected', () => {
    const selectedTasks = [makeTask({ id: 't1', status: 'IN_PROGRESS' })];
    render(
      <BatchActionsBar
        {...defaultProps}
        selectedCount={1}
        selectedTasks={selectedTasks}
      />
    );
    // Strategy selector should not appear when no READY tasks
    expect(screen.queryByText('Serial')).not.toBeInTheDocument();
  });

  it('hides action buttons when no tasks are selected', () => {
    render(<BatchActionsBar {...defaultProps} selectedCount={0} selectedTasks={[]} />);
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /stop/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reset/i })).not.toBeInTheDocument();
  });
});
