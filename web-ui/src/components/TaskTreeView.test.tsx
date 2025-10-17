/**
 * Tests for TaskTreeView Component
 * TDD: RED phase - These tests should fail initially
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TaskTreeView from './TaskTreeView';
import type { Issue, Task } from '@/types/api';

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

      expect(screen.getByText(/T-001/i)).toBeInTheDocument();
      expect(screen.getByText(/T-002/i)).toBeInTheDocument();
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

      // Task 2 depends on task-1
      expect(screen.getByText(/depends on.*task-1/i)).toBeInTheDocument();
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
      expect(completedBadges[0]).toHaveClass('bg-green-100');

      const inProgressBadges = screen.getAllByText(/in_progress/i);
      expect(inProgressBadges[0]).toHaveClass('bg-blue-100');
    });

    it('should apply color to pending status', () => {
      render(<TaskTreeView issues={mockIssues} />);

      const pendingBadge = screen.getByText(/pending/i);
      expect(pendingBadge).toHaveClass(/gray/);
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

      expect(screen.getByText(/depends on.*task-1.*task-3.*task-5/i)).toBeInTheDocument();
    });
  });
});
