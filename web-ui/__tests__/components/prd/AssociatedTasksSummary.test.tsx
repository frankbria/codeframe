import { render, screen } from '@testing-library/react';
import { AssociatedTasksSummary } from '@/components/prd/AssociatedTasksSummary';
import type { TaskStatusCounts } from '@/types';

describe('AssociatedTasksSummary', () => {
  it('renders nothing when all counts are zero', () => {
    const counts: TaskStatusCounts = {
      BACKLOG: 0, READY: 0, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 0,
    };
    const { container } = render(<AssociatedTasksSummary taskCounts={counts} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders total task count', () => {
    const counts: TaskStatusCounts = {
      BACKLOG: 2, READY: 3, IN_PROGRESS: 1, DONE: 5, BLOCKED: 0, FAILED: 0, MERGED: 0,
    };
    render(<AssociatedTasksSummary taskCounts={counts} />);
    expect(screen.getByText('Tasks (11)')).toBeInTheDocument();
  });

  it('renders badges only for non-zero statuses', () => {
    const counts: TaskStatusCounts = {
      BACKLOG: 0, READY: 3, IN_PROGRESS: 0, DONE: 5, BLOCKED: 0, FAILED: 1, MERGED: 0,
    };
    render(<AssociatedTasksSummary taskCounts={counts} />);

    expect(screen.getByText('Ready: 3')).toBeInTheDocument();
    expect(screen.getByText('Done: 5')).toBeInTheDocument();
    expect(screen.getByText('Failed: 1')).toBeInTheDocument();

    expect(screen.queryByText(/Backlog/)).not.toBeInTheDocument();
    expect(screen.queryByText(/In Progress/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Blocked/)).not.toBeInTheDocument();
  });

  it('renders all status badges when all are non-zero', () => {
    const counts: TaskStatusCounts = {
      BACKLOG: 1, READY: 2, IN_PROGRESS: 3, DONE: 4, BLOCKED: 5, FAILED: 6, MERGED: 0,
    };
    render(<AssociatedTasksSummary taskCounts={counts} />);

    expect(screen.getByText('Backlog: 1')).toBeInTheDocument();
    expect(screen.getByText('Ready: 2')).toBeInTheDocument();
    expect(screen.getByText('In Progress: 3')).toBeInTheDocument();
    expect(screen.getByText('Done: 4')).toBeInTheDocument();
    expect(screen.getByText('Blocked: 5')).toBeInTheDocument();
    expect(screen.getByText('Failed: 6')).toBeInTheDocument();
  });
});
