import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TaskColumn } from '@/components/tasks/TaskColumn';
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

const defaultHandlers = {
  onTaskClick: jest.fn(),
  onToggleSelect: jest.fn(),
  onExecute: jest.fn(),
  onMarkReady: jest.fn(),
  onStop: jest.fn(),
  onReset: jest.fn(),
  onSelectAll: jest.fn(),
  onDeselectAll: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('TaskColumn - Select All', () => {
  const tasks = [
    makeTask({ id: 't1', title: 'Task 1', status: 'READY' }),
    makeTask({ id: 't2', title: 'Task 2', status: 'READY' }),
    makeTask({ id: 't3', title: 'Task 3', status: 'READY' }),
  ];

  it('does not show select-all checkbox when not in selection mode', () => {
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={false}
        selectedTaskIds={new Set()}
        {...defaultHandlers}
      />
    );
    // Only column header and task cards - no checkbox in header
    expect(screen.queryByRole('checkbox', { name: /select all/i })).not.toBeInTheDocument();
  });

  it('shows unchecked select-all checkbox when no tasks are selected', () => {
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={true}
        selectedTaskIds={new Set()}
        {...defaultHandlers}
      />
    );
    const selectAll = screen.getByRole('checkbox', { name: /select all ready/i });
    expect(selectAll).toBeInTheDocument();
    expect(selectAll).not.toBeChecked();
  });

  it('shows checked select-all checkbox when all tasks are selected', () => {
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={true}
        selectedTaskIds={new Set(['t1', 't2', 't3'])}
        {...defaultHandlers}
      />
    );
    const selectAll = screen.getByRole('checkbox', { name: /select all ready/i });
    expect(selectAll).toBeChecked();
  });

  it('shows indeterminate select-all checkbox when some tasks are selected', () => {
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={true}
        selectedTaskIds={new Set(['t1'])}
        {...defaultHandlers}
      />
    );
    const selectAll = screen.getByRole('checkbox', { name: /select all ready/i });
    expect(selectAll).toHaveAttribute('data-state', 'indeterminate');
  });

  it('calls onSelectAll with task IDs when clicking unchecked select-all', async () => {
    const user = userEvent.setup();
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={true}
        selectedTaskIds={new Set()}
        {...defaultHandlers}
      />
    );
    await user.click(screen.getByRole('checkbox', { name: /select all ready/i }));
    expect(defaultHandlers.onSelectAll).toHaveBeenCalledWith(['t1', 't2', 't3']);
  });

  it('calls onDeselectAll with task IDs when clicking checked select-all', async () => {
    const user = userEvent.setup();
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={true}
        selectedTaskIds={new Set(['t1', 't2', 't3'])}
        {...defaultHandlers}
      />
    );
    await user.click(screen.getByRole('checkbox', { name: /select all ready/i }));
    expect(defaultHandlers.onDeselectAll).toHaveBeenCalledWith(['t1', 't2', 't3']);
  });

  it('calls onSelectAll when clicking indeterminate select-all (selects remaining)', async () => {
    const user = userEvent.setup();
    render(
      <TaskColumn
        status="READY"
        tasks={tasks}
        selectionMode={true}
        selectedTaskIds={new Set(['t1'])}
        {...defaultHandlers}
      />
    );
    await user.click(screen.getByRole('checkbox', { name: /select all ready/i }));
    expect(defaultHandlers.onSelectAll).toHaveBeenCalledWith(['t1', 't2', 't3']);
  });

  it('does not show select-all checkbox when column is empty', () => {
    render(
      <TaskColumn
        status="READY"
        tasks={[]}
        selectionMode={true}
        selectedTaskIds={new Set()}
        {...defaultHandlers}
      />
    );
    expect(screen.queryByRole('checkbox', { name: /select all/i })).not.toBeInTheDocument();
  });
});
