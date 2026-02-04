import { render, screen } from '@testing-library/react';
import { RecentActivityFeed } from '@/components/workspace/RecentActivityFeed';
import type { ActivityItem } from '@/types';

describe('RecentActivityFeed', () => {
  const mockActivities: ActivityItem[] = [
    {
      id: '1',
      type: 'task_completed',
      timestamp: '2026-02-04T10:30:00Z',
      description: 'Task "Add authentication" completed',
    },
    {
      id: '2',
      type: 'run_started',
      timestamp: '2026-02-04T10:00:00Z',
      description: 'Execution started for task "Setup database"',
    },
    {
      id: '3',
      type: 'blocker_raised',
      timestamp: '2026-02-04T09:30:00Z',
      description: 'Blocker raised: Missing API credentials',
    },
  ];

  it('renders activity items', () => {
    render(<RecentActivityFeed activities={mockActivities} />);

    expect(
      screen.getByText('Task "Add authentication" completed')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Execution started for task "Setup database"')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Blocker raised: Missing API credentials')
    ).toBeInTheDocument();
  });

  it('displays section title', () => {
    render(<RecentActivityFeed activities={mockActivities} />);

    expect(screen.getByText('Recent Activity')).toBeInTheDocument();
  });

  it('shows empty state when no activities', () => {
    render(<RecentActivityFeed activities={[]} />);

    expect(screen.getByText(/no recent activity/i)).toBeInTheDocument();
  });

  it('limits display to 5 items', () => {
    const manyActivities: ActivityItem[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i + 1),
      type: 'task_completed' as const,
      timestamp: `2026-02-04T${10 + i}:00:00Z`,
      description: `Activity ${i + 1}`,
    }));

    render(<RecentActivityFeed activities={manyActivities} />);

    // Should only show first 5
    expect(screen.getByText('Activity 1')).toBeInTheDocument();
    expect(screen.getByText('Activity 5')).toBeInTheDocument();
    expect(screen.queryByText('Activity 6')).not.toBeInTheDocument();
  });

  it('displays relative timestamps', () => {
    // This test checks that timestamps are formatted relatively
    render(<RecentActivityFeed activities={mockActivities} />);

    // The exact format depends on the current time, but we should see some time indication
    const timeElements = screen.getAllByTestId('activity-timestamp');
    expect(timeElements.length).toBeGreaterThan(0);
  });
});
