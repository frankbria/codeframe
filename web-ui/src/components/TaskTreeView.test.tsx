/**
 * Tests for TaskTreeView Component
 * TDD: RED phase - These tests should fail initially
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TaskTreeView from './TaskTreeView';
import type { Issue, Task } from '@/types/api';

// Mock QualityGateStatus component to avoid async issues in tests
jest.mock('./quality-gates/QualityGateStatus', () => {
  return function QualityGateStatus() {
    return 'Quality Gate Status Mock';
  };
});

describe('TaskTreeView', () => {
  const mockTasks: Task[] = [
    {
      id: 'task-1',
      task_number: 'T-001',
      title: 'Implement authentication',
      description: 'Add user authentication system',
      status: 'completed',
      depends_on: [],
      proposed_by: 'agent',
      created_at: '2025-10-15T10:00:00Z',
      updated_at: '2025-10-16T10:00:00Z',
      completed_at: '2025-10-16T10:00:00Z',
    },
    {
      id: 'task-2',
      task_number: 'T-002',
      title: 'Add login UI',
      description: 'Create login form component',
      status: 'in_progress',
      depends_on: ['task-1'],
      proposed_by: 'human',
      created_at: '2025-10-16T10:00:00Z',
      updated_at: '2025-10-17T10:00:00Z',
      completed_at: null,
    },
  ];

  const mockIssues: Issue[] = [
    {
      id: 'issue-1',
      issue_number: 'I-001',
      title: 'User Authentication Feature',
      description: 'Implement complete user authentication',
      status: 'in_progress',
      priority: 1,
      depends_on: [],
      proposed_by: 'agent',
      created_at: '2025-10-15T09:00:00Z',
      updated_at: '2025-10-17T09:00:00Z',
      completed_at: null,
      tasks: mockTasks,
    },
    {
      id: 'issue-2',
      issue_number: 'I-002',
      title: 'Dashboard UI',
      description: 'Build dashboard interface',
      status: 'pending',
      priority: 2,
      depends_on: ['issue-1'],
      proposed_by: 'human',
      created_at: '2025-10-16T09:00:00Z',
      updated_at: '2025-10-17T09:00:00Z',
      completed_at: null,
      tasks: [],
    },
  ];

  describe('Rendering', () => {
    it('should render tree view with issues', () => {
      render(<TaskTreeView issues={mockIssues} />);

      expect(screen.getByText('User Authentication Feature')).toBeInTheDocument();
      expect(screen.getByText('Dashboard UI')).toBeInTheDocument();
    });

    it('should display issue numbers', () => {
      render(<TaskTreeView issues={mockIssues} />);

      expect(screen.getByText(/I-001/i)).toBeInTheDocument();
      expect(screen.getByText(/I-002/i)).toBeInTheDocument();
    });

    it('should display issue status badges', () => {
      render(<TaskTreeView issues={mockIssues} />);

      expect(screen.getByText(/in_progress/i)).toBeInTheDocument();
      expect(screen.getByText(/pending/i)).toBeInTheDocument();
    });

    it('should display priority indicators', () => {
      render(<TaskTreeView issues={mockIssues} />);

      // Priority 1 should be visible
      const priority1Elements = screen.getAllByText(/Priority:.*1/i);
      expect(priority1Elements.length).toBeGreaterThan(0);
    });

    it('should display provenance indicators (agent vs human)', () => {
      render(<TaskTreeView issues={mockIssues} />);

      // Check for agent/human badges or icons
      expect(screen.getByText(/🤖/)).toBeInTheDocument(); // Agent emoji
      expect(screen.getByText(/👤/)).toBeInTheDocument(); // Human emoji
    });

    it('should render empty state when no issues', () => {
      render(<TaskTreeView issues={[]} />);

      expect(screen.getByText(/no issues/i)).toBeInTheDocument();
    });

    it('should initially render with collapsed tasks', () => {
      render(<TaskTreeView issues={mockIssues} />);

      // Tasks should not be visible initially
      expect(screen.queryByText('Implement authentication')).not.toBeInTheDocument();
      expect(screen.queryByText('Add login UI')).not.toBeInTheDocument();
    });
  });

  describe('Tree Expansion/Collapse', () => {
    it('should expand issue to show tasks when clicked', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      // Initially tasks should not be visible
      expect(screen.queryByText('Implement authentication')).not.toBeInTheDocument();

      // Click to expand the first issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Tasks should now be visible
      expect(screen.getByText('Implement authentication')).toBeInTheDocument();
      expect(screen.getByText('Add login UI')).toBeInTheDocument();
    });

    it('should collapse issue when clicked again', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      // Expand
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      expect(screen.getByText('Implement authentication')).toBeInTheDocument();

      // Collapse
      const collapseButton = screen.getByRole('button', { name: /collapse/i });
      await user.click(collapseButton);

      // Tasks should be hidden again
      expect(screen.queryByText('Implement authentication')).not.toBeInTheDocument();
    });

    it('should show expand/collapse icon indicator', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];

      // Should show right arrow or plus when collapsed
      expect(expandButton).toHaveTextContent(/[▶►+]/);

      await user.click(expandButton);

      // Should show down arrow or minus when expanded
      const collapseButton = screen.getByRole('button', { name: /collapse/i });
      expect(collapseButton).toHaveTextContent(/[▼▾-]/);
    });

    it('should handle issues with no tasks gracefully', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      // Click on issue without tasks (issue-2)
      const expandButtons = screen.getAllByRole('button', { name: /expand/i });
      const issue2Button = expandButtons[1];
      await user.click(issue2Button);

      // Should show "no tasks" message
      expect(screen.getByText(/no tasks/i)).toBeInTheDocument();
    });
  });

  describe('Task Display', () => {
    it('should display task numbers', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Use getAllByText since task numbers appear multiple times
      const task001Elements = screen.getAllByText(/T-001/i);
      expect(task001Elements.length).toBeGreaterThan(0);
      
      const task002Elements = screen.getAllByText(/T-002/i);
      expect(task002Elements.length).toBeGreaterThan(0);
    });

    it('should display task status badges', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Use getAllByText since there can be multiple status badges
      const completedBadges = screen.getAllByText(/completed/i);
      expect(completedBadges.length).toBeGreaterThan(0);

      const inProgressBadges = screen.getAllByText(/in_progress/i);
      expect(inProgressBadges.length).toBeGreaterThan(0);
    });

    it('should display task provenance (agent vs human)', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Should have multiple provenance indicators
      const agentBadges = screen.getAllByText(/🤖/);
      const humanBadges = screen.getAllByText(/👤/);

      expect(agentBadges.length).toBeGreaterThan(1); // Issue + Task
      expect(humanBadges.length).toBeGreaterThan(0); // Task
    });

    it('should display task dependencies', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Task 2 depends on task-1 - use getAllByText since "depends on" might appear multiple times
      const dependsElements = screen.getAllByText(/depends on.*task-1/i);
      expect(dependsElements.length).toBeGreaterThan(0);
    });

    it('should handle tasks with no dependencies', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Task 1 has no dependencies - should not show dependency text for it
      const task1Area = screen.getByText('Implement authentication').closest('div');
      expect(task1Area).not.toHaveTextContent(/depends on/i);
    });
  });

  describe('Status Colors', () => {
    it('should apply different colors for different statuses', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Check for status badges with appropriate colors - use getAllByText
      const completedBadges = screen.getAllByText(/completed/i);
      expect(completedBadges[0]).toHaveClass('bg-secondary');

      const inProgressBadges = screen.getAllByText(/in_progress/i);
      expect(inProgressBadges[0]).toHaveClass('bg-primary/10');
    });

    it('should apply color to pending status', () => {
      render(<TaskTreeView issues={mockIssues} />);

      const pendingBadge = screen.getByText(/pending/i);
      expect(pendingBadge).toHaveClass('bg-muted');
    });
  });

  describe('Accessibility', () => {
    it('should have proper tree structure with ARIA attributes', () => {
      render(<TaskTreeView issues={mockIssues} />);

      // Should have tree role
      const tree = screen.getByRole('tree');
      expect(tree).toBeInTheDocument();
    });

    it('should have proper aria-expanded attributes', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];

      // Initially collapsed
      expect(expandButton).toHaveAttribute('aria-expanded', 'false');

      await user.click(expandButton);

      // Now expanded
      const collapseButton = screen.getByRole('button', { name: /collapse/i });
      expect(collapseButton).toHaveAttribute('aria-expanded', 'true');
    });

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];

      // Should be able to expand with Enter key
      expandButton.focus();
      await user.keyboard('{Enter}');

      expect(screen.getByText('Implement authentication')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('should handle issues with empty task arrays', () => {
      const issuesWithEmptyTasks: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [],
        },
      ];

      render(<TaskTreeView issues={issuesWithEmptyTasks} />);

      expect(screen.getByText('User Authentication Feature')).toBeInTheDocument();
    });

    it('should handle issues without tasks property', () => {
      const issuesWithoutTasks: Issue[] = [
        {
          ...mockIssues[0],
          tasks: undefined,
        },
      ];

      render(<TaskTreeView issues={issuesWithoutTasks} />);

      expect(screen.getByText('User Authentication Feature')).toBeInTheDocument();
    });

    it('should handle very long issue/task titles', () => {
      const longTitleIssue: Issue[] = [
        {
          ...mockIssues[0],
          title: 'A'.repeat(200),
        },
      ];

      render(<TaskTreeView issues={longTitleIssue} />);

      const titleElement = screen.getByText(/A{200}/);
      expect(titleElement).toBeInTheDocument();
    });

    it('should handle multiple dependencies correctly', async () => {
      const user = userEvent.setup();

      const multiDepTask: Task = {
        ...mockTasks[1],
        depends_on: ['task-1', 'task-3', 'task-5'],
      };

      const issueWithMultiDep: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [multiDepTask],
        },
      ];

      render(<TaskTreeView issues={issueWithMultiDep} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Use getAllByText since "depends on" text might appear multiple times
      const multiDepElements = screen.getAllByText(/depends on.*task-1.*task-3.*task-5/i);
      expect(multiDepElements.length).toBeGreaterThan(0);
    });
  });

  describe('Task Status Variations', () => {
    it('should display failed status correctly', async () => {
      const user = userEvent.setup();

      const failedTask: Task = {
        ...mockTasks[0],
        status: 'failed',
      };

      const issueWithFailedTask: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [failedTask],
        },
      ];

      render(<TaskTreeView issues={issueWithFailedTask} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      const failedBadge = screen.getByText(/failed/i);
      expect(failedBadge).toHaveClass('bg-destructive/10');
      expect(failedBadge).toHaveClass('text-destructive-foreground');
    });

    it('should display assigned status correctly', async () => {
      const user = userEvent.setup();

      const assignedTask: Task = {
        ...mockTasks[0],
        status: 'assigned',
      };

      const issueWithAssignedTask: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [assignedTask],
        },
      ];

      render(<TaskTreeView issues={issueWithAssignedTask} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      const assignedBadge = screen.getByText(/assigned/i);
      expect(assignedBadge).toHaveClass('bg-primary/20');
      expect(assignedBadge).toHaveClass('text-foreground');
    });

    it('should display blocked status correctly', async () => {
      const user = userEvent.setup();

      const blockedTask: Task = {
        ...mockTasks[0],
        status: 'blocked',
      };

      const issueWithBlockedTask: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [blockedTask],
        },
      ];

      render(<TaskTreeView issues={issueWithBlockedTask} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      const blockedBadge = screen.getByText(/blocked/i);
      expect(blockedBadge).toHaveClass('bg-destructive/10');
      expect(blockedBadge).toHaveClass('text-destructive-foreground');
    });
  });

  describe('Priority Variations', () => {
    it('should display priority 2 correctly', () => {
      render(<TaskTreeView issues={mockIssues} />);

      const priority2Badge = screen.getByText(/Priority:.*2/i);
      expect(priority2Badge).toHaveClass('bg-destructive/80');
      expect(priority2Badge).toHaveClass('text-destructive-foreground');
    });

    it('should display priority 3 correctly', () => {
      const priority3Issue: Issue[] = [
        {
          ...mockIssues[0],
          priority: 3,
        },
      ];

      render(<TaskTreeView issues={priority3Issue} />);

      const priority3Badge = screen.getByText(/Priority:.*3/i);
      expect(priority3Badge).toHaveClass('bg-primary/20');
      expect(priority3Badge).toHaveClass('text-foreground');
    });

    it('should display priority 4+ correctly', () => {
      const priority4Issue: Issue[] = [
        {
          ...mockIssues[0],
          priority: 4,
        },
      ];

      render(<TaskTreeView issues={priority4Issue} />);

      const priority4Badge = screen.getByText(/Priority:.*4/i);
      expect(priority4Badge).toHaveClass('bg-muted');
      expect(priority4Badge).toHaveClass('text-foreground');
    });
  });

  describe('Quality Gates', () => {
    it('should show quality gates section for completed tasks', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Wait for tasks to be visible
      await waitFor(() => {
        expect(screen.getByText('Implement authentication')).toBeInTheDocument();
      });

      // Quality gates section should be visible for completed task
      const qualityGatesButtons = screen.getAllByText(/Quality Gates/i);
      expect(qualityGatesButtons.length).toBeGreaterThan(0);
    });

    it('should toggle quality gates section when clicked', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      // Expand issue
      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Wait for tasks to be visible
      await waitFor(() => {
        expect(screen.getByText('Implement authentication')).toBeInTheDocument();
      });

      // Click quality gates button
      const qualityGatesButton = screen.getAllByText(/Quality Gates/i)[0];
      await user.click(qualityGatesButton);

      // QualityGateStatus component should be rendered (mocked)
      await waitFor(() => {
        expect(screen.queryByText(/Quality Gate Status Mock/i)).toBeInTheDocument();
      });
    });

    it('should not show quality gates for pending tasks', async () => {
      const user = userEvent.setup();

      const pendingTask: Task = {
        ...mockTasks[0],
        status: 'pending',
      };

      const issueWithPendingTask: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [pendingTask],
        },
      ];

      render(<TaskTreeView issues={issueWithPendingTask} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Quality gates should not be visible for pending task
      expect(screen.queryByText(/Quality Gates/i)).not.toBeInTheDocument();
    });
  });

  describe('Task Dependencies and Blocking', () => {
    it('should show dependency indicator for tasks with dependencies', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Task 2 has dependencies - should show link emoji
      const linkEmojis = screen.getAllByText('🔗');
      expect(linkEmojis.length).toBeGreaterThan(0);
    });

    it('should show dependency count for tasks with dependencies', async () => {
      const user = userEvent.setup();

      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Should show dependency text
      const depText = screen.getByText(/depends on.*task-1/i);
      expect(depText).toBeInTheDocument();
    });

    it('should mark task as blocked when dependencies are not completed', async () => {
      const user = userEvent.setup();

      const incompleteDep: Task = {
        id: 'task-1',
        task_number: 'T-001',
        title: 'Implement authentication',
        description: 'Add user authentication system',
        status: 'in_progress', // Not completed
        depends_on: [],
        proposed_by: 'agent',
        created_at: '2025-10-15T10:00:00Z',
        updated_at: '2025-10-16T10:00:00Z',
        completed_at: null,
      };

      const blockedTask: Task = {
        id: 'task-2',
        task_number: 'T-002',
        title: 'Add login UI',
        description: 'Create login form component',
        status: 'pending', // Blocked status
        depends_on: ['task-1'],
        proposed_by: 'human',
        created_at: '2025-10-16T10:00:00Z',
        updated_at: '2025-10-17T10:00:00Z',
        completed_at: null,
      };

      const issueWithBlockedTask: Issue[] = [
        {
          ...mockIssues[0],
          tasks: [incompleteDep, blockedTask],
        },
      ];

      render(<TaskTreeView issues={issueWithBlockedTask} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Should show blocked badge
      const blockedBadge = screen.getByText(/🚫 Blocked/i);
      expect(blockedBadge).toBeInTheDocument();
      expect(blockedBadge).toHaveClass('bg-destructive/10');
    });

    it('should not mark task as blocked when dependencies are completed', async () => {
      const user = userEvent.setup();

      // Task 1 is completed in mockTasks
      render(<TaskTreeView issues={mockIssues} />);

      const expandButton = screen.getAllByRole('button', { name: /expand/i })[0];
      await user.click(expandButton);

      // Task 2 depends on completed task-1, so should not show blocked badge
      const blockedBadges = screen.queryAllByText(/🚫 Blocked/i);
      expect(blockedBadges.length).toBe(0);
    });
  });
});