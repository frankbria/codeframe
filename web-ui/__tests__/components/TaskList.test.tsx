/**
 * Tests for TaskList Component
 * TDD: Tests written first to define expected behavior
 *
 * TaskList displays tasks during the development phase with:
 * - Flat list view (simpler than TaskTreeView)
 * - Real-time updates via useAgentState hook
 * - Status filtering
 * - Agent assignment display
 * - Progress indicators
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TaskList from '@/components/TaskList';
import type { Task, TaskStatus } from '@/types/agentState';

// Mock the useAgentState hook
const mockTasks: Task[] = [
  {
    id: 1,
    project_id: 1,
    title: 'Implement authentication',
    status: 'completed',
    agent_id: 'backend-worker-1',
    progress: 100,
    timestamp: Date.now() - 3600000,
  },
  {
    id: 2,
    project_id: 1,
    title: 'Add login UI',
    status: 'in_progress',
    agent_id: 'frontend-specialist-1',
    progress: 60,
    timestamp: Date.now() - 1800000,
  },
  {
    id: 3,
    project_id: 1,
    title: 'Write integration tests',
    status: 'blocked',
    agent_id: 'test-engineer-1',
    blocked_by: [1, 2],
    progress: 0,
    timestamp: Date.now() - 900000,
  },
  {
    id: 4,
    project_id: 1,
    title: 'Setup CI/CD pipeline',
    status: 'pending',
    progress: 0,
    timestamp: Date.now(),
  },
];

jest.mock('@/hooks/useAgentState', () => ({
  useAgentState: () => ({
    tasks: mockTasks,
    agents: [
      { id: 'backend-worker-1', type: 'backend-worker', status: 'idle' },
      { id: 'frontend-specialist-1', type: 'frontend-specialist', status: 'working' },
      { id: 'test-engineer-1', type: 'test-engineer', status: 'blocked' },
    ],
    activity: [],
    projectProgress: { completed_tasks: 1, total_tasks: 4, percentage: 25 },
    wsConnected: true,
  }),
}));

// Mock QualityGateStatus to avoid async issues (default export)
jest.mock('@/components/quality-gates/QualityGateStatus', () => {
  return function MockQualityGateStatus() {
    return <div data-testid="quality-gate-status">Quality Gate Status Mock</div>;
  };
});

describe('TaskList', () => {
  const defaultProps = {
    projectId: 1,
  };

  describe('Rendering', () => {
    it('should render the task list with all tasks', () => {
      render(<TaskList {...defaultProps} />);

      expect(screen.getByText('Implement authentication')).toBeInTheDocument();
      expect(screen.getByText('Add login UI')).toBeInTheDocument();
      expect(screen.getByText('Write integration tests')).toBeInTheDocument();
      expect(screen.getByText('Setup CI/CD pipeline')).toBeInTheDocument();
    });

    it('should display task status badges', () => {
      render(<TaskList {...defaultProps} />);

      // Get all task cards and check their status badges
      const taskCards = screen.getAllByTestId('task-card');
      expect(taskCards.length).toBe(4);

      // Status badges are inside task cards as span elements
      const completedCard = screen.getByText('Implement authentication').closest('[data-testid="task-card"]');
      expect(completedCard).toHaveTextContent(/completed/i);

      const inProgressCard = screen.getByText('Add login UI').closest('[data-testid="task-card"]');
      expect(inProgressCard).toHaveTextContent(/in progress/i);

      const blockedCard = screen.getByText('Write integration tests').closest('[data-testid="task-card"]');
      expect(blockedCard).toHaveTextContent(/blocked/i);

      const pendingCard = screen.getByText('Setup CI/CD pipeline').closest('[data-testid="task-card"]');
      expect(pendingCard).toHaveTextContent(/pending/i);
    });

    it('should display assigned agent for tasks', () => {
      render(<TaskList {...defaultProps} />);

      expect(screen.getByText(/backend-worker-1/i)).toBeInTheDocument();
      expect(screen.getByText(/frontend-specialist-1/i)).toBeInTheDocument();
      expect(screen.getByText(/test-engineer-1/i)).toBeInTheDocument();
    });

    it('should display progress percentage for in-progress tasks', () => {
      render(<TaskList {...defaultProps} />);

      expect(screen.getByText(/60%/)).toBeInTheDocument();
    });

    it('should show "Unassigned" for tasks without agent', () => {
      render(<TaskList {...defaultProps} />);

      expect(screen.getByText(/unassigned/i)).toBeInTheDocument();
    });

    it('should render empty state when no tasks for different project', () => {
      render(<TaskList projectId={999} />);

      // Project 999 has no tasks (all mockTasks have project_id: 1)
      expect(screen.getByText(/no tasks/i)).toBeInTheDocument();
    });
  });

  describe('Status Filtering', () => {
    it('should show filter buttons for each status', () => {
      render(<TaskList {...defaultProps} />);

      // Look for buttons with specific text patterns (including count)
      const buttons = screen.getAllByRole('button');
      const filterButtons = buttons.filter(
        (btn) => btn.textContent?.match(/All|Pending|In Progress|Blocked|Completed/i)
      );
      expect(filterButtons.length).toBeGreaterThanOrEqual(5);
    });

    it('should filter to show only in-progress tasks when filter selected', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      // Find the In Progress filter button
      const inProgressButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.includes('In Progress')
      );
      expect(inProgressButton).toBeInTheDocument();
      await user.click(inProgressButton!);

      expect(screen.getByText('Add login UI')).toBeInTheDocument();
      expect(screen.queryByText('Implement authentication')).not.toBeInTheDocument();
      expect(screen.queryByText('Write integration tests')).not.toBeInTheDocument();
      expect(screen.queryByText('Setup CI/CD pipeline')).not.toBeInTheDocument();
    });

    it('should filter to show only blocked tasks when filter selected', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      // Find the Blocked filter button
      const blockedButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.includes('Blocked')
      );
      await user.click(blockedButton!);

      expect(screen.getByText('Write integration tests')).toBeInTheDocument();
      expect(screen.queryByText('Add login UI')).not.toBeInTheDocument();
    });

    it('should filter to show only completed tasks when filter selected', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      // Find the Completed filter button
      const completedButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.includes('Completed')
      );
      await user.click(completedButton!);

      expect(screen.getByText('Implement authentication')).toBeInTheDocument();
      expect(screen.queryByText('Add login UI')).not.toBeInTheDocument();
    });

    it('should show all tasks when "All" filter is selected', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      // First filter to in_progress
      const inProgressButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.includes('In Progress')
      );
      await user.click(inProgressButton!);
      expect(screen.queryByText('Implement authentication')).not.toBeInTheDocument();

      // Then click All
      const allButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.match(/^All/i)
      );
      await user.click(allButton!);

      expect(screen.getByText('Implement authentication')).toBeInTheDocument();
      expect(screen.getByText('Add login UI')).toBeInTheDocument();
      expect(screen.getByText('Write integration tests')).toBeInTheDocument();
      expect(screen.getByText('Setup CI/CD pipeline')).toBeInTheDocument();
    });

    it('should highlight the active filter button', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      const inProgressButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.includes('In Progress')
      );
      await user.click(inProgressButton!);

      // Active filter should have different styling (bg-primary)
      expect(inProgressButton).toHaveClass('bg-primary');
    });

    it('should show task count in filter buttons', () => {
      render(<TaskList {...defaultProps} />);

      // Filter buttons should show counts in format "Label (N)"
      expect(screen.getByText(/All \(4\)/)).toBeInTheDocument();
      expect(screen.getByText(/Pending \(1\)/)).toBeInTheDocument();
      expect(screen.getByText(/In Progress \(1\)/)).toBeInTheDocument();
      expect(screen.getByText(/Blocked \(1\)/)).toBeInTheDocument();
      expect(screen.getByText(/Completed \(1\)/)).toBeInTheDocument();
    });

    it('should filter to show only pending tasks when filter selected', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      // Find the Pending filter button
      const pendingButton = screen.getAllByRole('button').find(
        (btn) => btn.textContent?.includes('Pending')
      );
      await user.click(pendingButton!);

      expect(screen.getByText('Setup CI/CD pipeline')).toBeInTheDocument();
      expect(screen.queryByText('Implement authentication')).not.toBeInTheDocument();
      expect(screen.queryByText('Add login UI')).not.toBeInTheDocument();
      expect(screen.queryByText('Write integration tests')).not.toBeInTheDocument();
    });
  });

  describe('Task Status Styling', () => {
    it('should apply correct styling for completed status', () => {
      render(<TaskList {...defaultProps} />);

      // Find the status badge inside the completed task card
      const completedCard = screen.getByText('Implement authentication').closest('[data-testid="task-card"]');
      const statusBadge = completedCard?.querySelector('span.inline-flex');
      expect(statusBadge).toHaveClass('bg-secondary/10');
    });

    it('should apply correct styling for in_progress status', () => {
      render(<TaskList {...defaultProps} />);

      // Find the status badge inside the in-progress task card
      const inProgressCard = screen.getByText('Add login UI').closest('[data-testid="task-card"]');
      const statusBadge = inProgressCard?.querySelector('span.inline-flex');
      expect(statusBadge).toHaveClass('bg-primary/10');
    });

    it('should apply correct styling for blocked status', () => {
      render(<TaskList {...defaultProps} />);

      // Find the status badge inside the blocked task card
      const blockedCard = screen.getByText('Write integration tests').closest('[data-testid="task-card"]');
      const statusBadge = blockedCard?.querySelector('span.inline-flex');
      expect(statusBadge).toHaveClass('bg-destructive/10');
    });

    it('should apply correct styling for pending status', () => {
      render(<TaskList {...defaultProps} />);

      // Find the status badge inside the pending task card
      const pendingCard = screen.getByText('Setup CI/CD pipeline').closest('[data-testid="task-card"]');
      const statusBadge = pendingCard?.querySelector('span.inline-flex');
      expect(statusBadge).toHaveClass('bg-muted');
    });
  });

  describe('Progress Display', () => {
    it('should show progress bar for in-progress tasks', () => {
      render(<TaskList {...defaultProps} />);

      const progressBars = screen.getAllByRole('progressbar');
      expect(progressBars.length).toBeGreaterThan(0);
    });

    it('should display correct progress value', () => {
      render(<TaskList {...defaultProps} />);

      const progressBar = screen.getAllByRole('progressbar').find(
        (bar) => bar.getAttribute('aria-valuenow') === '60'
      );
      expect(progressBar).toBeInTheDocument();
    });

    it('should not show progress bar for pending tasks', () => {
      render(<TaskList {...defaultProps} />);

      // Find the task card for Setup CI/CD pipeline (pending task)
      const pendingTaskCard = screen.getByText('Setup CI/CD pipeline').closest('[data-testid="task-card"]');
      const progressBar = pendingTaskCard?.querySelector('[role="progressbar"]');
      expect(progressBar).toBeNull();
    });
  });

  describe('Blocked Tasks', () => {
    it('should show blocked-by information for blocked tasks', () => {
      render(<TaskList {...defaultProps} />);

      // Blocked task should show the blocked by message
      const blockedCard = screen.getByText('Write integration tests').closest('[data-testid="task-card"]');
      expect(blockedCard).toHaveTextContent(/Blocked by/i);
    });

    it('should display blocking task count', () => {
      render(<TaskList {...defaultProps} />);

      // Task 3 is blocked by tasks 1 and 2 (2 tasks)
      const blockedCard = screen.getByText('Write integration tests').closest('[data-testid="task-card"]');
      expect(blockedCard).toHaveTextContent(/2 tasks/i);
    });
  });

  describe('Quality Gates', () => {
    it('should show quality gates button for completed tasks', () => {
      render(<TaskList {...defaultProps} />);

      // Find the completed task card
      const completedTaskCard = screen.getByText('Implement authentication').closest('[data-testid="task-card"]');
      const qualityGatesButton = completedTaskCard?.querySelector('[data-testid="quality-gates-button"]');
      expect(qualityGatesButton).toBeInTheDocument();
    });

    it('should toggle quality gates panel when button clicked', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      const qualityGatesButton = screen.getAllByTestId('quality-gates-button')[0];
      await user.click(qualityGatesButton);

      // After clicking, the Quality Gate Status mock should be visible
      await waitFor(() => {
        expect(screen.getByText('Quality Gate Status Mock')).toBeInTheDocument();
      });
    });

    it('should not show quality gates button for non-completed tasks', () => {
      render(<TaskList {...defaultProps} />);

      // Find the in-progress task card
      const inProgressTaskCard = screen.getByText('Add login UI').closest('[data-testid="task-card"]');
      const qualityGatesButton = inProgressTaskCard?.querySelector('[data-testid="quality-gates-button"]');
      expect(qualityGatesButton).toBeNull();
    });
  });

  describe('Accessibility', () => {
    it('should have proper list structure with ARIA attributes', () => {
      render(<TaskList {...defaultProps} />);

      const list = screen.getByRole('list');
      expect(list).toBeInTheDocument();
    });

    it('should have proper list item roles', () => {
      render(<TaskList {...defaultProps} />);

      const listItems = screen.getAllByRole('listitem');
      expect(listItems.length).toBe(4);
    });

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup();
      render(<TaskList {...defaultProps} />);

      const filterButtons = screen.getAllByRole('button');
      filterButtons[0].focus();

      await user.keyboard('{Tab}');
      expect(filterButtons[1]).toHaveFocus();
    });

    it('should have descriptive aria-labels', () => {
      render(<TaskList {...defaultProps} />);

      expect(screen.getByLabelText(/task list/i)).toBeInTheDocument();
    });
  });

  describe('Real-time Updates', () => {
    it('should filter tasks by projectId', () => {
      render(<TaskList projectId={1} />);

      // All mock tasks have project_id: 1
      expect(screen.getByText('Implement authentication')).toBeInTheDocument();
    });

    it('should display connection status indicator', () => {
      render(<TaskList {...defaultProps} />);

      // Should show connected status since wsConnected is true
      expect(screen.getByTestId('connection-status')).toBeInTheDocument();
    });
  });

  describe('Responsive Design', () => {
    it('should have responsive grid layout', () => {
      render(<TaskList {...defaultProps} />);

      const taskList = screen.getByRole('list');
      expect(taskList).toHaveClass('grid');
    });

    it('should stack cards on mobile', () => {
      render(<TaskList {...defaultProps} />);

      const taskList = screen.getByRole('list');
      expect(taskList).toHaveClass('grid-cols-1');
    });
  });

  describe('Edge Cases', () => {
    it('should handle tasks with zero or missing progress gracefully', () => {
      // Render with standard mock - includes tasks with progress: 0 (blocked task)
      // Component handles undefined/null progress via conditional: typeof task.progress === 'number'
      render(<TaskList {...defaultProps} />);

      // Should render without crashing
      expect(screen.getByTestId('task-list')).toBeInTheDocument();

      // Tasks with progress: 0 should not show progress bar (only in_progress with progress > 0 shows bar)
      const blockedTaskCard = screen.getByText('Write integration tests').closest('[data-testid="task-card"]');
      const progressBar = blockedTaskCard?.querySelector('[role="progressbar"]');
      expect(progressBar).toBeNull();
    });

    it('should handle very long task titles with truncation', () => {
      render(<TaskList {...defaultProps} />);

      // Titles should be truncated with CSS
      const taskTitle = screen.getByText('Implement authentication');
      expect(taskTitle).toHaveClass('truncate');
    });
  });
});
