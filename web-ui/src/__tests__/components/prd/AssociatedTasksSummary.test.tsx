import React from 'react';
import { render, screen } from '@testing-library/react';
import { AssociatedTasksSummary } from '@/components/prd/AssociatedTasksSummary';
import type { TaskStatusCounts } from '@/types';

jest.mock('next/link', () => {
  const MockLink = ({
    href,
    children,
    className,
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

const emptyCounts: TaskStatusCounts = {
  BACKLOG: 0,
  READY: 0,
  IN_PROGRESS: 0,
  BLOCKED: 0,
  FAILED: 0,
  DONE: 0,
  MERGED: 0,
};

describe('AssociatedTasksSummary', () => {
  it('returns null when all counts are zero', () => {
    const { container } = render(
      <AssociatedTasksSummary taskCounts={emptyCounts} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders a link to /tasks', () => {
    const counts: TaskStatusCounts = { ...emptyCounts, READY: 3, DONE: 2 };
    render(<AssociatedTasksSummary taskCounts={counts} />);

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/tasks');
  });

  it('shows total task count', () => {
    const counts: TaskStatusCounts = { ...emptyCounts, READY: 3, DONE: 2 };
    render(<AssociatedTasksSummary taskCounts={counts} />);

    expect(screen.getByText(/Tasks \(5\)/)).toBeInTheDocument();
  });

  it('shows badges only for non-zero statuses', () => {
    const counts: TaskStatusCounts = { ...emptyCounts, READY: 4, BLOCKED: 1 };
    render(<AssociatedTasksSummary taskCounts={counts} />);

    expect(screen.getByText('Ready: 4')).toBeInTheDocument();
    expect(screen.getByText('Blocked: 1')).toBeInTheDocument();
    expect(screen.queryByText(/Backlog/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Done/)).not.toBeInTheDocument();
  });
});
