import { render, screen } from '@testing-library/react';
import { QuickActions } from '@/components/workspace/QuickActions';

// Mock next/link
jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) {
    return <a href={href}>{children}</a>;
  };
});

const zeroCounts = { BACKLOG: 0, READY: 0, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 0 };

describe('QuickActions', () => {
  it('renders section title', () => {
    render(<QuickActions />);
    expect(screen.getByText('Quick Actions')).toBeInTheDocument();
  });

  it('shows Create PRD and Import PRD when no tasks exist', () => {
    render(<QuickActions taskCounts={{ ...zeroCounts }} />);
    expect(screen.getByRole('link', { name: /create prd/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /import prd/i })).toBeInTheDocument();
  });

  it('shows Execute Tasks and Manage Tasks when tasks are READY', () => {
    render(<QuickActions taskCounts={{ ...zeroCounts, READY: 3 }} />);
    expect(screen.getByRole('link', { name: /execute tasks/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /manage tasks/i })).toBeInTheDocument();
  });

  it('shows View Running Tasks when tasks are IN_PROGRESS', () => {
    render(<QuickActions taskCounts={{ ...zeroCounts, IN_PROGRESS: 1 }} />);
    expect(screen.getByRole('link', { name: /view running tasks/i })).toBeInTheDocument();
  });

  it('shows View Proof Gates and Review Changes when all tasks are DONE', () => {
    render(<QuickActions taskCounts={{ ...zeroCounts, DONE: 5 }} />);
    expect(screen.getByRole('link', { name: /view proof gates/i })).toHaveAttribute('href', '/proof');
    expect(screen.getByRole('link', { name: /review changes/i })).toHaveAttribute('href', '/review');
  });

  it('shows View PRD, Manage Tasks, Review Changes in mixed state', () => {
    // mixed = has tasks, none IN_PROGRESS/READY, and no DONE tasks yet
    render(<QuickActions taskCounts={{ ...zeroCounts, BACKLOG: 2 }} />);
    expect(screen.getByRole('link', { name: /view prd/i })).toHaveAttribute('href', '/prd');
    expect(screen.getByRole('link', { name: /manage tasks/i })).toHaveAttribute('href', '/tasks');
    expect(screen.getByRole('link', { name: /review changes/i })).toHaveAttribute('href', '/review');
  });

  it('defaults to no_tasks state when taskCounts is undefined', () => {
    render(<QuickActions />);
    expect(screen.getByRole('link', { name: /create prd/i })).toBeInTheDocument();
  });
});
