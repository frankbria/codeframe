import { render, screen } from '@testing-library/react';
import { WorkspaceStatsCards } from '@/components/workspace/WorkspaceStatsCards';
import type { TaskStatusCounts } from '@/types';

describe('WorkspaceStatsCards', () => {
  const mockTaskCounts: TaskStatusCounts = {
    BACKLOG: 5,
    READY: 3,
    IN_PROGRESS: 2,
    DONE: 10,
    BLOCKED: 1,
    FAILED: 0,
  };

  describe('TechStackCard', () => {
    it('displays detected tech stack', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python with FastAPI"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      expect(screen.getByText('Tech Stack')).toBeInTheDocument();
      expect(screen.getByText('Python with FastAPI')).toBeInTheDocument();
    });

    it('displays placeholder when tech stack is not detected', () => {
      render(
        <WorkspaceStatsCards
          techStack={null}
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      expect(screen.getByText(/not detected/i)).toBeInTheDocument();
    });
  });

  describe('TaskStatsCard', () => {
    it('displays task counts by status with badges', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      expect(screen.getByText('Tasks')).toBeInTheDocument();
      // Check status badges - format is "N status"
      expect(screen.getByText(/3 ready/)).toBeInTheDocument();
      expect(screen.getByText(/2 in progress/)).toBeInTheDocument();
      expect(screen.getByText(/10 done/)).toBeInTheDocument();
    });

    it('displays total task count', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      // Total: 5 + 3 + 2 + 10 + 1 + 0 = 21
      expect(screen.getByText('21 total')).toBeInTheDocument();
    });

    it('renders status badge colors correctly', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      // Check that badges with correct variants exist
      const readyBadge = screen.getByTestId('badge-ready');
      const inProgressBadge = screen.getByTestId('badge-in-progress');
      const doneBadge = screen.getByTestId('badge-done');

      expect(readyBadge).toHaveClass('bg-blue-100');
      expect(inProgressBadge).toHaveClass('bg-amber-100');
      expect(doneBadge).toHaveClass('bg-green-100');
    });
  });

  describe('ActiveRunsCard', () => {
    it('displays active run count', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={2}
        />
      );

      expect(screen.getByText('Active Runs')).toBeInTheDocument();
      expect(screen.getByTestId('active-run-count')).toHaveTextContent('2');
    });

    it('shows "View Execution" link when there are active runs', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={1}
        />
      );

      expect(
        screen.getByRole('link', { name: /view execution/i })
      ).toBeInTheDocument();
    });

    it('does not show "View Execution" link when no active runs', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      expect(
        screen.queryByRole('link', { name: /view execution/i })
      ).not.toBeInTheDocument();
    });

    it('displays muted styling when count is zero', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      const countElement = screen.getByTestId('active-run-count');
      expect(countElement).toHaveClass('text-muted-foreground');
    });
  });

  describe('responsive layout', () => {
    it('renders all three cards', () => {
      render(
        <WorkspaceStatsCards
          techStack="Python"
          taskCounts={mockTaskCounts}
          activeRunCount={0}
        />
      );

      expect(screen.getByText('Tech Stack')).toBeInTheDocument();
      expect(screen.getByText('Tasks')).toBeInTheDocument();
      expect(screen.getByText('Active Runs')).toBeInTheDocument();
    });
  });
});
