/**
 * Tests for TaskReview Component
 * TDD approach: Tests written before implementation
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TaskReview from '@/components/TaskReview';
import { projectsApi } from '@/lib/api';
import type { Issue, Task, IssuesResponse } from '@/types/api';

// Mock the API module
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getIssues: jest.fn(),
    approveTaskBreakdown: jest.fn(),
  },
}));

// Mock useRouter from next/navigation
const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

describe('TaskReview', () => {
  // Mock data setup
  const mockTasks1: Task[] = [
    {
      id: 'task-1',
      task_number: '1.1.1',
      title: 'Create login form',
      description: 'Build the login form component',
      status: 'pending',
      depends_on: [],
      proposed_by: 'agent',
      created_at: '2025-10-15T10:00:00Z',
      updated_at: '2025-10-16T10:00:00Z',
      completed_at: null,
    },
    {
      id: 'task-2',
      task_number: '1.1.2',
      title: 'Add form validation',
      description: 'Implement input validation',
      status: 'pending',
      depends_on: ['task-1'],
      proposed_by: 'agent',
      created_at: '2025-10-16T10:00:00Z',
      updated_at: '2025-10-17T10:00:00Z',
      completed_at: null,
    },
    {
      id: 'task-3',
      task_number: '1.1.3',
      title: 'Connect to auth API',
      description: 'Integrate with authentication endpoint',
      status: 'pending',
      depends_on: ['task-2'],
      proposed_by: 'human',
      created_at: '2025-10-17T10:00:00Z',
      updated_at: '2025-10-18T10:00:00Z',
      completed_at: null,
    },
  ];

  const mockTasks2: Task[] = [
    {
      id: 'task-4',
      task_number: '1.2.1',
      title: 'Design dashboard layout',
      description: 'Create mockups for dashboard',
      status: 'pending',
      depends_on: [],
      proposed_by: 'agent',
      created_at: '2025-10-18T10:00:00Z',
      updated_at: '2025-10-19T10:00:00Z',
      completed_at: null,
    },
  ];

  const mockIssues: Issue[] = [
    {
      id: 'issue-1',
      issue_number: '1.1',
      title: 'User Authentication',
      description: 'Implement user authentication flow',
      status: 'pending',
      priority: 1,
      depends_on: [],
      proposed_by: 'agent',
      created_at: '2025-10-15T09:00:00Z',
      updated_at: '2025-10-17T09:00:00Z',
      completed_at: null,
      tasks: mockTasks1,
    },
    {
      id: 'issue-2',
      issue_number: '1.2',
      title: 'Dashboard UI',
      description: 'Build main dashboard interface',
      status: 'pending',
      priority: 2,
      depends_on: ['issue-1'],
      proposed_by: 'human',
      created_at: '2025-10-16T09:00:00Z',
      updated_at: '2025-10-17T09:00:00Z',
      completed_at: null,
      tasks: mockTasks2,
    },
  ];

  const mockIssuesResponse: IssuesResponse = {
    issues: mockIssues,
    total_issues: 2,
    total_tasks: 4,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (projectsApi.getIssues as jest.Mock).mockResolvedValue({
      data: mockIssuesResponse,
    });
    (projectsApi.approveTaskBreakdown as jest.Mock).mockResolvedValue({
      data: {
        success: true,
        message: 'Tasks approved successfully',
        approved_count: 4,
        project_phase: 'active',
      },
    });
  });

  describe('Rendering', () => {
    it('should render loading state initially', () => {
      render(<TaskReview projectId={1} />);

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it('should render tree view with issues after loading', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
        expect(screen.getByText('Dashboard UI')).toBeInTheDocument();
      });
    });

    it('should display issue numbers', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/1\.1/)).toBeInTheDocument();
        expect(screen.getByText(/1\.2/)).toBeInTheDocument();
      });
    });

    it('should display task counts for each issue', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/3 tasks/i)).toBeInTheDocument();
        expect(screen.getByText(/1 task/i)).toBeInTheDocument();
      });
    });

    it('should display approval button', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
      });
    });

    it('should render empty state when no issues', async () => {
      (projectsApi.getIssues as jest.Mock).mockResolvedValue({
        data: { issues: [], total_issues: 0, total_tasks: 0 },
      });

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/no tasks/i)).toBeInTheDocument();
      });
    });

    it('should show error state on fetch failure', async () => {
      (projectsApi.getIssues as jest.Mock).mockRejectedValue(new Error('Network error'));

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
      });
    });
  });

  describe('Tree Expansion/Collapse', () => {
    it('should expand issue to show tasks when clicked', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Initially tasks should not be visible
      expect(screen.queryByText('Create login form')).not.toBeInTheDocument();

      // Click to expand the first issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Tasks should now be visible
      expect(screen.getByText('Create login form')).toBeInTheDocument();
      expect(screen.getByText('Add form validation')).toBeInTheDocument();
      expect(screen.getByText('Connect to auth API')).toBeInTheDocument();
    });

    it('should collapse issue when clicked again', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Sprint 1 is auto-expanded, so expand buttons are for issues only
      // Index 0 = User Authentication, Index 1 = Dashboard UI
      const expandButtons = screen.getAllByRole('button', { name: /expand/i });
      await user.click(expandButtons[0]);

      expect(screen.getByText('Create login form')).toBeInTheDocument();

      // Collapse - now we have: [Sprint collapse, Issue collapse]
      const collapseButtons = screen.getAllByRole('button', { name: /collapse/i });
      // The second collapse button (index 1) is the issue collapse
      await user.click(collapseButtons[1]);

      // Tasks should be hidden again
      expect(screen.queryByText('Create login form')).not.toBeInTheDocument();
    });

    it('should show expand/collapse icon indicator', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Sprint 1 is auto-expanded, so expand buttons are for issues only
      // Index 0 = User Authentication expand button
      const expandButtons = screen.getAllByRole('button', { name: /expand/i });
      const issueExpandButton = expandButtons[0];

      // Should show right arrow when collapsed
      expect(issueExpandButton).toHaveTextContent(/[▶►+]/);

      await user.click(issueExpandButton);

      // Should show down arrow when expanded
      const collapseButtons = screen.getAllByRole('button', { name: /collapse/i });
      // Issue collapse button is second one (after sprint collapse)
      expect(collapseButtons[1]).toHaveTextContent(/[▼▾-]/);
    });
  });

  describe('Checkbox Selection', () => {
    it('should render checkboxes for all tasks', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand the issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Should have checkboxes for tasks
      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes.length).toBeGreaterThanOrEqual(3); // At least task checkboxes
    });

    it('should initialize all tasks as selected by default', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand both issues
      const expandButtons = screen.getAllByRole('button', { name: /expand/i });
      await user.click(expandButtons[0]);
      await user.click(expandButtons[1]);

      // All task checkboxes should be checked
      const checkboxes = screen.getAllByRole('checkbox');
      checkboxes.forEach((checkbox) => {
        expect(checkbox).toBeChecked();
      });
    });

    it('should toggle individual task selection', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand the issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Find and uncheck the first task checkbox
      const firstTaskCheckbox = screen.getByRole('checkbox', { name: /create login form/i });
      expect(firstTaskCheckbox).toBeChecked();

      await user.click(firstTaskCheckbox);
      expect(firstTaskCheckbox).not.toBeChecked();

      await user.click(firstTaskCheckbox);
      expect(firstTaskCheckbox).toBeChecked();
    });

    it('should render issue-level checkbox for selecting all tasks', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Issue-level checkbox should be visible without expanding
      const issueCheckbox = screen.getByRole('checkbox', { name: /user authentication/i });
      expect(issueCheckbox).toBeInTheDocument();
    });

    it('should select all tasks in issue when issue checkbox is checked', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand the issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Uncheck the issue checkbox
      const issueCheckbox = screen.getByRole('checkbox', { name: /user authentication/i });
      await user.click(issueCheckbox);

      // All task checkboxes should now be unchecked
      const taskCheckbox1 = screen.getByRole('checkbox', { name: /create login form/i });
      const taskCheckbox2 = screen.getByRole('checkbox', { name: /add form validation/i });
      const taskCheckbox3 = screen.getByRole('checkbox', { name: /connect to auth api/i });

      expect(taskCheckbox1).not.toBeChecked();
      expect(taskCheckbox2).not.toBeChecked();
      expect(taskCheckbox3).not.toBeChecked();

      // Check the issue checkbox again
      await user.click(issueCheckbox);

      // All task checkboxes should be checked
      expect(taskCheckbox1).toBeChecked();
      expect(taskCheckbox2).toBeChecked();
      expect(taskCheckbox3).toBeChecked();
    });

    it('should show indeterminate state when some tasks are selected', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand the issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Uncheck one task
      const firstTaskCheckbox = screen.getByRole('checkbox', { name: /create login form/i });
      await user.click(firstTaskCheckbox);

      // Issue checkbox should be in indeterminate state
      const issueCheckbox = screen.getByRole('checkbox', {
        name: /user authentication/i,
      }) as HTMLInputElement;

      // Check indeterminate property
      expect(issueCheckbox.indeterminate).toBe(true);
    });
  });

  describe('Summary Display', () => {
    it('should display selected task count', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Should show total task count (4 tasks selected by default)
      expect(screen.getByText(/4 tasks selected/i)).toBeInTheDocument();
    });

    it('should update summary when tasks are deselected', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand and deselect one task
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      const firstTaskCheckbox = screen.getByRole('checkbox', { name: /create login form/i });
      await user.click(firstTaskCheckbox);

      // Summary should update
      expect(screen.getByText(/3 tasks selected/i)).toBeInTheDocument();
    });
  });

  describe('Approval Flow', () => {
    it('should call approval API with both selected and all task IDs', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      // The API should receive selectedTaskIds (all selected) AND allTaskIds
      // Since all are selected, both arrays should be identical
      await waitFor(() => {
        expect(projectsApi.approveTaskBreakdown).toHaveBeenCalledWith(
          1,
          expect.arrayContaining(['task-1', 'task-2', 'task-3', 'task-4']),
          expect.arrayContaining(['task-1', 'task-2', 'task-3', 'task-4'])
        );
      });
    });

    it('should pass excluded tasks via the allTaskIds parameter', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand and deselect one task
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      const firstTaskCheckbox = screen.getByRole('checkbox', { name: /create login form/i });
      await user.click(firstTaskCheckbox);

      // Approve
      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      // API should receive:
      // - selectedTaskIds: 3 tasks (task-2, task-3, task-4)
      // - allTaskIds: all 4 tasks (so backend can compute excluded = [task-1])
      await waitFor(() => {
        expect(projectsApi.approveTaskBreakdown).toHaveBeenCalledWith(
          1,
          expect.arrayContaining(['task-2', 'task-3', 'task-4']),
          expect.arrayContaining(['task-1', 'task-2', 'task-3', 'task-4'])
        );

        // Verify task-1 is NOT in selectedTaskIds (first argument after projectId)
        const calls = (projectsApi.approveTaskBreakdown as jest.Mock).mock.calls;
        const selectedTaskIds = calls[0][1];
        expect(selectedTaskIds).not.toContain('task-1');
        expect(selectedTaskIds).toHaveLength(3);
      });
    });

    it('should show loading state during approval', async () => {
      const user = userEvent.setup();

      // Make approval take time
      (projectsApi.approveTaskBreakdown as jest.Mock).mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      // Should show loading state
      expect(screen.getByText(/approving/i)).toBeInTheDocument();
      expect(approveButton).toBeDisabled();
    });

    it('should navigate to project dashboard on success', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith('/projects/1');
      });
    });

    it('should call onApprovalSuccess callback when provided', async () => {
      const user = userEvent.setup();
      const onSuccess = jest.fn();

      render(<TaskReview projectId={1} onApprovalSuccess={onSuccess} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
      });
    });

    it('should show error message on approval failure', async () => {
      const user = userEvent.setup();

      (projectsApi.approveTaskBreakdown as jest.Mock).mockRejectedValue(
        new Error('Approval failed')
      );

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(screen.getByText(/failed to approve/i)).toBeInTheDocument();
      });
    });

    it('should call onApprovalError callback when provided', async () => {
      const user = userEvent.setup();
      const onError = jest.fn();
      const error = new Error('Approval failed');

      (projectsApi.approveTaskBreakdown as jest.Mock).mockRejectedValue(error);

      render(<TaskReview projectId={1} onApprovalError={onError} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(onError).toHaveBeenCalled();
      });
    });

    it('should disable approval button when no tasks selected', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Deselect all by unchecking issue checkboxes
      const issueCheckbox1 = screen.getByRole('checkbox', { name: /user authentication/i });
      const issueCheckbox2 = screen.getByRole('checkbox', { name: /dashboard ui/i });

      await user.click(issueCheckbox1);
      await user.click(issueCheckbox2);

      // Approval button should be disabled
      const approveButton = screen.getByRole('button', { name: /approve/i });
      expect(approveButton).toBeDisabled();
    });
  });

  describe('Accessibility', () => {
    it('should have proper tree structure with ARIA attributes', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Should have tree role
      const tree = screen.getByRole('tree');
      expect(tree).toBeInTheDocument();
    });

    it('should have proper aria-expanded attributes', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Sprint 1 is auto-expanded, so expand buttons are for issues only
      // Index 0 = User Authentication expand button
      const expandButtons = screen.getAllByRole('button', { name: /expand/i });
      const issueExpandButton = expandButtons[0];

      // Initially collapsed
      expect(issueExpandButton).toHaveAttribute('aria-expanded', 'false');

      await user.click(issueExpandButton);

      // Now expanded - get collapse buttons and check the issue one
      const collapseButtons = screen.getAllByRole('button', { name: /collapse/i });
      expect(collapseButtons[1]).toHaveAttribute('aria-expanded', 'true');
    });

    it('should have accessible checkbox labels', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Issue checkboxes should have labels
      expect(screen.getByRole('checkbox', { name: /user authentication/i })).toBeInTheDocument();
      expect(screen.getByRole('checkbox', { name: /dashboard ui/i })).toBeInTheDocument();

      // Expand to check task checkboxes
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      expect(screen.getByRole('checkbox', { name: /create login form/i })).toBeInTheDocument();
    });

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];

      // Should be able to expand with Enter key
      expandButton.focus();
      await user.keyboard('{Enter}');

      expect(screen.getByText('Create login form')).toBeInTheDocument();
    });

    it('should toggle checkbox with Space key', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand to access task checkboxes
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      const taskCheckbox = screen.getByRole('checkbox', { name: /create login form/i });
      taskCheckbox.focus();

      expect(taskCheckbox).toBeChecked();
      await user.keyboard(' ');
      expect(taskCheckbox).not.toBeChecked();
    });
  });

  describe('Edge Cases', () => {
    it('should handle issues without tasks property', async () => {
      const issuesWithoutTasks: Issue[] = [
        {
          ...mockIssues[0],
          tasks: undefined,
        },
      ];

      (projectsApi.getIssues as jest.Mock).mockResolvedValue({
        data: { issues: issuesWithoutTasks, total_issues: 1, total_tasks: 0 },
      });

      render(<TaskReview projectId={1} />);

      // With no tasks, the component shows the empty state
      await waitFor(() => {
        expect(screen.getByText(/no tasks available/i)).toBeInTheDocument();
      });
    });

    it('should handle issues with empty task arrays', async () => {
      const user = userEvent.setup();

      const issuesWithEmptyTasks: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [],
        },
      ];

      (projectsApi.getIssues as jest.Mock).mockResolvedValue({
        data: { issues: issuesWithEmptyTasks, total_issues: 1, total_tasks: 0 },
      });

      render(<TaskReview projectId={1} />);

      // With no tasks, the component shows the empty state
      await waitFor(() => {
        expect(screen.getByText(/no tasks available/i)).toBeInTheDocument();
      });
    });

    it('should handle string projectId', async () => {
      render(<TaskReview projectId="1" />);

      await waitFor(() => {
        expect(projectsApi.getIssues).toHaveBeenCalledWith('1', { include: 'tasks' });
      });
    });

    it('should handle numeric projectId', async () => {
      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getIssues).toHaveBeenCalledWith(1, { include: 'tasks' });
      });
    });

    it('should handle very long task titles', async () => {
      const user = userEvent.setup();

      const longTitleTask: Task = {
        ...mockTasks1[0],
        title: 'A'.repeat(200),
      };

      const issuesWithLongTitle: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [longTitleTask],
        },
      ];

      (projectsApi.getIssues as jest.Mock).mockResolvedValue({
        data: { issues: issuesWithLongTitle, total_issues: 1, total_tasks: 1 },
      });

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand
      const expandButton = screen.getByRole('button', { name: /expand/i });
      await user.click(expandButton);

      // Should render without breaking
      const titleElement = screen.getByText(/A{50}/);
      expect(titleElement).toBeInTheDocument();
    });

    it('should handle rapid selection changes', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });

      // Expand
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Rapidly toggle checkboxes
      const taskCheckbox = screen.getByRole('checkbox', { name: /create login form/i });

      await user.click(taskCheckbox);
      await user.click(taskCheckbox);
      await user.click(taskCheckbox);
      await user.click(taskCheckbox);

      // Should end up checked (even number of clicks)
      expect(taskCheckbox).toBeChecked();
    });
  });

  describe('Retry Functionality', () => {
    it('should allow retry on fetch error', async () => {
      const user = userEvent.setup();

      (projectsApi.getIssues as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
      });

      // Should have retry button
      const retryButton = screen.getByRole('button', { name: /retry/i });

      // Mock successful response for retry
      (projectsApi.getIssues as jest.Mock).mockResolvedValueOnce({
        data: mockIssuesResponse,
      });

      await user.click(retryButton);

      await waitFor(() => {
        expect(screen.getByText('User Authentication')).toBeInTheDocument();
      });
    });
  });

  describe('Sprint Grouping', () => {
    it('should group issues by sprint number', async () => {
      const multiSprintIssues: Issue[] = [
        {
          ...mockIssues[0],
          issue_number: '1.1', // Sprint 1
        },
        {
          ...mockIssues[1],
          issue_number: '2.1', // Sprint 2
        },
      ];

      (projectsApi.getIssues as jest.Mock).mockResolvedValue({
        data: { issues: multiSprintIssues, total_issues: 2, total_tasks: 4 },
      });

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/sprint 1/i)).toBeInTheDocument();
        expect(screen.getByText(/sprint 2/i)).toBeInTheDocument();
      });
    });

    it('should display sprint aggregate statistics', async () => {
      const multiSprintIssues: Issue[] = [
        {
          ...mockIssues[0],
          issue_number: '1.1',
        },
        {
          ...mockIssues[1],
          issue_number: '1.2',
        },
      ];

      (projectsApi.getIssues as jest.Mock).mockResolvedValue({
        data: { issues: multiSprintIssues, total_issues: 2, total_tasks: 4 },
      });

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        // Sprint 1 should show aggregate counts
        expect(screen.getByText(/2 issues/i)).toBeInTheDocument();
      });
    });

    it('should expand/collapse sprint sections', async () => {
      const user = userEvent.setup();

      render(<TaskReview projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/sprint 1/i)).toBeInTheDocument();
      });

      // Sprint should be expandable
      const sprintExpandButton = screen.getAllByRole('button', { name: /expand/i })[0];

      // Initially issues might be collapsed under sprint
      await user.click(sprintExpandButton);

      // Issues should be visible
      expect(screen.getByText('User Authentication')).toBeInTheDocument();
    });
  });
});
