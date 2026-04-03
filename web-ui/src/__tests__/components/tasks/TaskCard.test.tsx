import React from 'react';
import { render, screen } from '@testing-library/react';
import { TaskCard } from '@/components/tasks/TaskCard';
import { STATUS_INFO } from '@/lib/taskStatusInfo';
import type { Task } from '@/types';

jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

// Radix UI tooltips use portals and pointer events that don't work in jsdom.
// Replace with a simple always-visible version to test content.
jest.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => (
    <div role="tooltip">{children}</div>
  ),
}));

const baseTask: Task = {
  id: 'task-1',
  title: 'Test Task',
  description: 'A test task description',
  status: 'BACKLOG',
  priority: 0,
  depends_on: [],
};

const defaultProps = {
  task: baseTask,
  selectionMode: false,
  selected: false,
  onToggleSelect: jest.fn(),
  onClick: jest.fn(),
  onExecute: jest.fn(),
  onMarkReady: jest.fn(),
};

describe('TaskCard status badge tooltip', () => {
  it('renders the status badge label', () => {
    render(<TaskCard {...defaultProps} />);
    expect(screen.getByText('Backlog')).toBeInTheDocument();
  });

  it('renders tooltip with BACKLOG meaning', () => {
    render(<TaskCard {...defaultProps} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.BACKLOG.meaning);
  });

  it('renders tooltip with BACKLOG next steps', () => {
    render(<TaskCard {...defaultProps} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.BACKLOG.nextSteps);
  });

  it('renders tooltip with READY meaning', () => {
    const task = { ...baseTask, status: 'READY' as const };
    render(<TaskCard {...defaultProps} task={task} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.READY.meaning);
  });

  it('renders tooltip with FAILED meaning', () => {
    const task = { ...baseTask, status: 'FAILED' as const };
    render(<TaskCard {...defaultProps} task={task} onReset={jest.fn()} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.FAILED.meaning);
  });

  it('renders tooltip with IN_PROGRESS meaning', () => {
    const task = { ...baseTask, status: 'IN_PROGRESS' as const };
    render(<TaskCard {...defaultProps} task={task} onStop={jest.fn()} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.IN_PROGRESS.meaning);
  });

  it('renders tooltip with DONE meaning', () => {
    const task = { ...baseTask, status: 'DONE' as const };
    render(<TaskCard {...defaultProps} task={task} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.DONE.meaning);
  });

  it('renders tooltip with BLOCKED meaning', () => {
    const task = { ...baseTask, status: 'BLOCKED' as const };
    render(<TaskCard {...defaultProps} task={task} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.BLOCKED.meaning);
  });

  it('renders tooltip with MERGED meaning', () => {
    const task = { ...baseTask, status: 'MERGED' as const };
    render(<TaskCard {...defaultProps} task={task} />);
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.MERGED.meaning);
  });
});
