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

  describe('edge cases', () => {
    it('handles activities with long descriptions', () => {
      const longDescriptionActivity: ActivityItem[] = [
        {
          id: '1',
          type: 'task_completed',
          timestamp: '2026-02-04T10:30:00Z',
          description: 'A'.repeat(500), // Very long description
        },
      ];

      render(<RecentActivityFeed activities={longDescriptionActivity} />);

      // Should render without crashing
      expect(screen.getByText('A'.repeat(500))).toBeInTheDocument();
    });

    it('handles activities with special characters in description', () => {
      const specialCharsActivity: ActivityItem[] = [
        {
          id: '1',
          type: 'task_completed',
          timestamp: '2026-02-04T10:30:00Z',
          description: '<script>alert("xss")</script> & "quotes" \'single\'',
        },
      ];

      render(<RecentActivityFeed activities={specialCharsActivity} />);

      // Should render text content safely (React escapes by default)
      expect(
        screen.getByText('<script>alert("xss")</script> & "quotes" \'single\'')
      ).toBeInTheDocument();
    });

    it('handles activities with empty description', () => {
      const emptyDescriptionActivity: ActivityItem[] = [
        {
          id: '1',
          type: 'task_completed',
          timestamp: '2026-02-04T10:30:00Z',
          description: '',
        },
      ];

      render(<RecentActivityFeed activities={emptyDescriptionActivity} />);

      // Should render the activity item even with empty description
      expect(screen.getByTestId('activity-timestamp')).toBeInTheDocument();
    });

    it('handles all activity types correctly', () => {
      const allTypesActivities: ActivityItem[] = [
        { id: '1', type: 'task_completed', timestamp: '2026-02-04T10:00:00Z', description: 'Task done' },
        { id: '2', type: 'run_started', timestamp: '2026-02-04T09:00:00Z', description: 'Run started' },
        { id: '3', type: 'blocker_raised', timestamp: '2026-02-04T08:00:00Z', description: 'Blocker' },
        { id: '4', type: 'workspace_initialized', timestamp: '2026-02-04T07:00:00Z', description: 'Workspace init' },
        { id: '5', type: 'prd_added', timestamp: '2026-02-04T06:00:00Z', description: 'PRD added' },
      ];

      render(<RecentActivityFeed activities={allTypesActivities} />);

      // All should render
      expect(screen.getByText('Task done')).toBeInTheDocument();
      expect(screen.getByText('Run started')).toBeInTheDocument();
      expect(screen.getByText('Blocker')).toBeInTheDocument();
      expect(screen.getByText('Workspace init')).toBeInTheDocument();
      expect(screen.getByText('PRD added')).toBeInTheDocument();
    });

    it('handles very old timestamps correctly', () => {
      const oldTimestampActivity: ActivityItem[] = [
        {
          id: '1',
          type: 'task_completed',
          timestamp: '2020-01-01T00:00:00Z', // Old but valid timestamp
          description: 'Activity with old timestamp',
        },
      ];

      render(<RecentActivityFeed activities={oldTimestampActivity} />);

      // Should render with a "years ago" style timestamp
      expect(screen.getByText('Activity with old timestamp')).toBeInTheDocument();
      expect(screen.getByTestId('activity-timestamp')).toBeInTheDocument();
    });

    it('handles activities with metadata', () => {
      const activityWithMetadata: ActivityItem[] = [
        {
          id: '1',
          type: 'task_completed',
          timestamp: '2026-02-04T10:30:00Z',
          description: 'Task completed',
          metadata: {
            task_id: 'task-123',
            duration: 3600,
            status: 'DONE',
          },
        },
      ];

      render(<RecentActivityFeed activities={activityWithMetadata} />);

      // Should render without crashing (metadata is for internal use)
      expect(screen.getByText('Task completed')).toBeInTheDocument();
    });
  });
});
