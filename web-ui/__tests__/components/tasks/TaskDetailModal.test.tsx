import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { tasksApi } from '@/lib/api';
import type { Task } from '@/types';

// ─── Mocks ──────────────────────────────────────────────────────────

jest.mock('@/lib/api', () => ({
  tasksApi: {
    getOne: jest.fn(),
    updateStatus: jest.fn(),
  },
}));

const mockGetOne = tasksApi.getOne as jest.Mock;
const mockUpdateStatus = tasksApi.updateStatus as jest.Mock;

// ─── Fixtures ───────────────────────────────────────────────────────

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    title: 'Implement login',
    description: 'Build the user login form with validation.',
    status: 'READY',
    priority: 2,
    depends_on: [],
    estimated_hours: 4,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

const defaultProps = {
  taskId: 'task-1',
  workspacePath: '/test',
  open: true,
  onClose: jest.fn(),
  onExecute: jest.fn(),
  onStatusChange: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Tests ──────────────────────────────────────────────────────────

describe('TaskDetailModal', () => {
  it('shows loading spinner while fetching task', async () => {
    // Never resolve the API call
    mockGetOne.mockReturnValue(new Promise(() => {}));
    render(<TaskDetailModal {...defaultProps} />);

    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows error message when fetch fails', async () => {
    mockGetOne.mockRejectedValue({ detail: 'Task not found' });
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Task not found')).toBeInTheDocument();
    });
  });

  it('renders task title, description, and status badge', async () => {
    mockGetOne.mockResolvedValue(makeTask());
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Implement login')).toBeInTheDocument();
    });
    expect(screen.getByText('Build the user login form with validation.')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('shows priority when > 0', async () => {
    mockGetOne.mockResolvedValue(makeTask({ priority: 3 }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Priority 3')).toBeInTheDocument();
    });
  });

  it('shows dependency count when task has dependencies', async () => {
    mockGetOne.mockResolvedValue(makeTask({ depends_on: ['dep-1', 'dep-2'] }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText(/2 dependencies/)).toBeInTheDocument();
    });
  });

  it('shows estimated hours when present', async () => {
    mockGetOne.mockResolvedValue(makeTask({ estimated_hours: 8 }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('8h estimated')).toBeInTheDocument();
    });
  });

  it('shows "No description." for tasks without description', async () => {
    mockGetOne.mockResolvedValue(makeTask({ description: '' }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('No description.')).toBeInTheDocument();
    });
  });

  it('shows Execute button for READY tasks', async () => {
    mockGetOne.mockResolvedValue(makeTask({ status: 'READY' }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /execute/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /mark ready/i })).not.toBeInTheDocument();
  });

  it('shows Mark Ready button for BACKLOG tasks', async () => {
    mockGetOne.mockResolvedValue(makeTask({ status: 'BACKLOG' }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /mark ready/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
  });

  it('hides action buttons for non-actionable statuses', async () => {
    mockGetOne.mockResolvedValue(makeTask({ status: 'DONE' }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Implement login')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /mark ready/i })).not.toBeInTheDocument();
  });

  it('calls onExecute when Execute button is clicked', async () => {
    const user = userEvent.setup();
    mockGetOne.mockResolvedValue(makeTask({ status: 'READY' }));
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /execute/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /execute/i }));
    expect(defaultProps.onExecute).toHaveBeenCalledWith('task-1');
  });

  it('calls updateStatus and onStatusChange when Mark Ready is clicked', async () => {
    const user = userEvent.setup();
    const updatedTask = makeTask({ status: 'READY' });
    mockGetOne.mockResolvedValue(makeTask({ status: 'BACKLOG' }));
    mockUpdateStatus.mockResolvedValue(updatedTask);
    render(<TaskDetailModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /mark ready/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /mark ready/i }));

    expect(mockUpdateStatus).toHaveBeenCalledWith('/test', 'task-1', 'READY');
    await waitFor(() => {
      expect(defaultProps.onStatusChange).toHaveBeenCalled();
    });
  });

  it('does not fetch when closed', () => {
    render(<TaskDetailModal {...defaultProps} open={false} />);
    expect(mockGetOne).not.toHaveBeenCalled();
  });

  it('does not fetch when taskId is null', () => {
    render(<TaskDetailModal {...defaultProps} taskId={null} />);
    expect(mockGetOne).not.toHaveBeenCalled();
  });

  it('cleans up on unmount (no stale state updates)', async () => {
    // Start a fetch that will resolve after unmount
    let resolvePromise: (task: Task) => void;
    mockGetOne.mockReturnValue(
      new Promise<Task>((resolve) => { resolvePromise = resolve; })
    );

    const { unmount } = render(<TaskDetailModal {...defaultProps} />);
    unmount();

    // Resolve after unmount — should not throw
    await act(async () => {
      resolvePromise!(makeTask());
    });
    // If we get here without errors, cleanup worked
  });
});
