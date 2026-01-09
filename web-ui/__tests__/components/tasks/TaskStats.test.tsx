/**
 * Unit tests for TaskStats component
 *
 * Tests:
 * - Renders all 4 statistics correctly
 * - Calculates statistics from derived state
 * - Handles empty task arrays
 * - Handles mixed task statuses
 * - Displays correct testids for E2E testing
 *
 * Part of Dashboard Overview tab
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import TaskStats from '../../../src/components/tasks/TaskStats';
import * as useAgentStateModule from '../../../src/hooks/useAgentState';
import type { Task } from '../../../src/types/agentState';

// Mock the useAgentState hook
jest.mock('../../../src/hooks/useAgentState');

const mockUseAgentState = useAgentStateModule.useAgentState as jest.MockedFunction<
  typeof useAgentStateModule.useAgentState
>;

describe('TaskStats', () => {
  // Sample task data for testing
  const createMockTask = (id: number, status: Task['status']): Task => ({
    id,
    project_id: 1,
    title: `Task ${id}`,
    status,
    timestamp: Date.now(),
  });

  const mockTasks: Task[] = [
    createMockTask(1, 'completed'),
    createMockTask(2, 'completed'),
    createMockTask(3, 'in_progress'),
    createMockTask(4, 'in_progress'),
    createMockTask(5, 'in_progress'),
    createMockTask(6, 'blocked'),
    createMockTask(7, 'pending'),
    createMockTask(8, 'pending'),
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('test_renders_all_statistics', () => {
    // ARRANGE
    mockUseAgentState.mockReturnValue({
      tasks: mockTasks,
      completedTasks: mockTasks.filter((t) => t.status === 'completed'),
      blockedTasks: mockTasks.filter((t) => t.status === 'blocked'),
      activeTasks: mockTasks.filter((t) => t.status === 'in_progress'),
      // Mock other required properties
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT: Verify all 4 statistics are rendered
    expect(screen.getByText('Total Tasks')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
    expect(screen.getByText('In Progress')).toBeInTheDocument();
  });

  it('test_calculates_stats_correctly', () => {
    // ARRANGE
    const completedTasks = mockTasks.filter((t) => t.status === 'completed');
    const blockedTasks = mockTasks.filter((t) => t.status === 'blocked');
    const activeTasks = mockTasks.filter((t) => t.status === 'in_progress');

    mockUseAgentState.mockReturnValue({
      tasks: mockTasks,
      completedTasks,
      blockedTasks,
      activeTasks,
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT: Verify correct counts
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('8'); // Total
    expect(screen.getByTestId('completed-tasks')).toHaveTextContent('2'); // Completed
    expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('1'); // Blocked
    expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('3'); // In Progress
  });

  it('test_handles_empty_tasks', () => {
    // ARRANGE
    mockUseAgentState.mockReturnValue({
      tasks: [],
      completedTasks: [],
      blockedTasks: [],
      activeTasks: [],
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT: Verify all counts are 0
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('0');
    expect(screen.getByTestId('completed-tasks')).toHaveTextContent('0');
    expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('0');
    expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('0');
  });

  it('test_handles_all_completed_tasks', () => {
    // ARRANGE
    const allCompletedTasks = [
      createMockTask(1, 'completed'),
      createMockTask(2, 'completed'),
      createMockTask(3, 'completed'),
    ];

    mockUseAgentState.mockReturnValue({
      tasks: allCompletedTasks,
      completedTasks: allCompletedTasks,
      blockedTasks: [],
      activeTasks: [],
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT: All tasks are completed
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('3');
    expect(screen.getByTestId('completed-tasks')).toHaveTextContent('3');
    expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('0');
    expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('0');
  });

  it('test_handles_mixed_statuses', () => {
    // ARRANGE: Equal distribution of statuses
    const mixedTasks = [
      createMockTask(1, 'completed'),
      createMockTask(2, 'completed'),
      createMockTask(3, 'in_progress'),
      createMockTask(4, 'in_progress'),
      createMockTask(5, 'blocked'),
      createMockTask(6, 'blocked'),
      createMockTask(7, 'pending'),
      createMockTask(8, 'pending'),
    ];

    mockUseAgentState.mockReturnValue({
      tasks: mixedTasks,
      completedTasks: mixedTasks.filter((t) => t.status === 'completed'),
      blockedTasks: mixedTasks.filter((t) => t.status === 'blocked'),
      activeTasks: mixedTasks.filter((t) => t.status === 'in_progress'),
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: mixedTasks.filter((t) => t.status === 'pending'),
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT: Even distribution
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('8');
    expect(screen.getByTestId('completed-tasks')).toHaveTextContent('2');
    expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('2');
    expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('2');
  });

  it('test_displays_correct_testids', () => {
    // ARRANGE
    mockUseAgentState.mockReturnValue({
      tasks: mockTasks,
      completedTasks: mockTasks.filter((t) => t.status === 'completed'),
      blockedTasks: mockTasks.filter((t) => t.status === 'blocked'),
      activeTasks: mockTasks.filter((t) => t.status === 'in_progress'),
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT: All testids are present (required for E2E tests)
    expect(screen.getByTestId('total-tasks')).toBeInTheDocument();
    expect(screen.getByTestId('completed-tasks')).toBeInTheDocument();
    expect(screen.getByTestId('blocked-tasks')).toBeInTheDocument();
    expect(screen.getByTestId('in-progress-tasks')).toBeInTheDocument();
  });

  it('test_renders_with_single_task', () => {
    // ARRANGE: Edge case - single task
    const singleTask = [createMockTask(1, 'in_progress')];

    mockUseAgentState.mockReturnValue({
      tasks: singleTask,
      completedTasks: [],
      blockedTasks: [],
      activeTasks: singleTask,
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    });

    // ACT
    render(<TaskStats />);

    // ASSERT
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('1');
    expect(screen.getByTestId('completed-tasks')).toHaveTextContent('0');
    expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('0');
    expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('1');
  });

  // ============================================================
  // Phase-Aware Tests (Late-Joining User Bug Fix)
  // ============================================================
  // These tests verify TaskStats correctly selects data source based on phase:
  // - Planning phase: Uses issuesData prop (REST API data)
  // - Development/Review phase: Uses useAgentState hook (WebSocket data)
  // ============================================================

  describe('Phase-Aware Data Source Selection', () => {
    // Mock issues data structure matching IssuesResponse
    const mockIssuesData = {
      issues: [
        {
          id: '1',
          issue_number: '1',
          title: 'Issue 1',
          description: 'Test issue',
          status: 'pending' as const,
          priority: 1,
          depends_on: [],
          proposed_by: 'agent' as const,
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
          completed_at: null,
          tasks: [
            {
              id: '101',
              task_number: '1.1',
              title: 'Task 1',
              description: 'Test task',
              status: 'pending' as const,
              depends_on: [],
              proposed_by: 'agent' as const,
              created_at: '2025-01-01T00:00:00Z',
              updated_at: '2025-01-01T00:00:00Z',
              completed_at: null,
            },
            {
              id: '102',
              task_number: '1.2',
              title: 'Task 2',
              description: 'Test task',
              status: 'completed' as const,
              depends_on: [],
              proposed_by: 'agent' as const,
              created_at: '2025-01-01T00:00:00Z',
              updated_at: '2025-01-01T00:00:00Z',
              completed_at: '2025-01-01T01:00:00Z',
            },
          ],
        },
        {
          id: '2',
          issue_number: '2',
          title: 'Issue 2',
          description: 'Test issue 2',
          status: 'in_progress' as const,
          priority: 2,
          depends_on: [],
          proposed_by: 'agent' as const,
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
          completed_at: null,
          tasks: [
            {
              id: '201',
              task_number: '2.1',
              title: 'Task 3',
              description: 'Test task',
              status: 'in_progress' as const,
              depends_on: [],
              proposed_by: 'agent' as const,
              created_at: '2025-01-01T00:00:00Z',
              updated_at: '2025-01-01T00:00:00Z',
              completed_at: null,
            },
            {
              id: '202',
              task_number: '2.2',
              title: 'Task 4',
              description: 'Test task',
              status: 'blocked' as const,
              depends_on: [],
              proposed_by: 'agent' as const,
              created_at: '2025-01-01T00:00:00Z',
              updated_at: '2025-01-01T00:00:00Z',
              completed_at: null,
            },
          ],
        },
      ],
      total_issues: 2,
      total_tasks: 4,
    };

    // Empty agent state for planning phase (no agents active yet)
    const emptyAgentState = {
      tasks: [],
      completedTasks: [],
      blockedTasks: [],
      activeTasks: [],
      agents: [],
      activity: [],
      projectProgress: null,
      wsConnected: true,
      lastSyncTimestamp: Date.now(),
      activeAgents: [],
      idleAgents: [],
      pendingTasks: [],
      loadAgents: jest.fn(),
      createAgent: jest.fn(),
      updateAgent: jest.fn(),
      retireAgent: jest.fn(),
      assignTask: jest.fn(),
      updateTaskStatus: jest.fn(),
      blockTask: jest.fn(),
      unblockTask: jest.fn(),
      addActivity: jest.fn(),
      updateProgress: jest.fn(),
      setWSConnected: jest.fn(),
      fullResync: jest.fn(),
    };

    it('test_planning_phase_uses_issues_data', () => {
      // ARRANGE: Planning phase with empty agent state but populated issues data
      mockUseAgentState.mockReturnValue(emptyAgentState);

      // ACT: Render with phase='planning' and issuesData
      render(<TaskStats phase="planning" issuesData={mockIssuesData} />);

      // ASSERT: Should show counts from issuesData, NOT from empty agent state
      // Total: 4 tasks (2 in issue 1 + 2 in issue 2)
      // Completed: 1 (task 1.2)
      // Blocked: 1 (task 2.2)
      // In Progress: 1 (task 2.1)
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('4');
      expect(screen.getByTestId('completed-tasks')).toHaveTextContent('1');
      expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('1');
      expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('1');
    });

    it('test_development_phase_uses_agent_state', () => {
      // ARRANGE: Development phase with agent state data
      const activeTasks = mockTasks.filter((t) => t.status === 'in_progress');
      mockUseAgentState.mockReturnValue({
        ...emptyAgentState,
        tasks: mockTasks,
        completedTasks: mockTasks.filter((t) => t.status === 'completed'),
        blockedTasks: mockTasks.filter((t) => t.status === 'blocked'),
        activeTasks,
      });

      // ACT: Render with phase='development' (should ignore issuesData)
      render(<TaskStats phase="development" issuesData={mockIssuesData} />);

      // ASSERT: Should show counts from agent state, NOT from issuesData
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('8');
      expect(screen.getByTestId('completed-tasks')).toHaveTextContent('2');
      expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('1');
      expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('3');
    });

    it('test_review_phase_uses_agent_state', () => {
      // ARRANGE: Review phase with agent state data
      mockUseAgentState.mockReturnValue({
        ...emptyAgentState,
        tasks: mockTasks,
        completedTasks: mockTasks.filter((t) => t.status === 'completed'),
        blockedTasks: mockTasks.filter((t) => t.status === 'blocked'),
        activeTasks: mockTasks.filter((t) => t.status === 'in_progress'),
      });

      // ACT: Render with phase='review' (should ignore issuesData)
      render(<TaskStats phase="review" issuesData={mockIssuesData} />);

      // ASSERT: Should show counts from agent state
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('8');
    });

    it('test_planning_phase_handles_missing_issues_data', () => {
      // ARRANGE: Planning phase but issuesData not yet loaded
      mockUseAgentState.mockReturnValue(emptyAgentState);

      // ACT: Render with phase='planning' but undefined issuesData
      render(<TaskStats phase="planning" issuesData={undefined} />);

      // ASSERT: Should gracefully show 0 (not crash)
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('0');
      expect(screen.getByTestId('completed-tasks')).toHaveTextContent('0');
      expect(screen.getByTestId('blocked-tasks')).toHaveTextContent('0');
      expect(screen.getByTestId('in-progress-tasks')).toHaveTextContent('0');
    });

    it('test_planning_phase_handles_issues_without_tasks', () => {
      // ARRANGE: Issues exist but have no tasks array
      const issuesWithoutTasks = {
        issues: [
          {
            id: '1',
            issue_number: '1',
            title: 'Issue 1',
            description: 'Test issue',
            status: 'pending' as const,
            priority: 1,
            depends_on: [],
            proposed_by: 'agent' as const,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
            completed_at: null,
            // Note: no tasks array
          },
        ],
        total_issues: 1,
        total_tasks: 0,
      };

      mockUseAgentState.mockReturnValue(emptyAgentState);

      // ACT
      render(<TaskStats phase="planning" issuesData={issuesWithoutTasks} />);

      // ASSERT: Should handle gracefully
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('0');
    });

    it('test_backward_compatible_without_props', () => {
      // ARRANGE: Existing usage without phase/issuesData props
      mockUseAgentState.mockReturnValue({
        ...emptyAgentState,
        tasks: mockTasks,
        completedTasks: mockTasks.filter((t) => t.status === 'completed'),
        blockedTasks: mockTasks.filter((t) => t.status === 'blocked'),
        activeTasks: mockTasks.filter((t) => t.status === 'in_progress'),
      });

      // ACT: Render without props (backward compatibility)
      render(<TaskStats />);

      // ASSERT: Should work as before, using agent state
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('8');
      expect(screen.getByTestId('completed-tasks')).toHaveTextContent('2');
    });

    it('test_phase_transition_switches_data_source', () => {
      // This test simulates what happens when a project transitions from
      // planning to development phase - the data source should switch
      const { rerender } = render(
        <TaskStats phase="planning" issuesData={mockIssuesData} />
      );

      // ARRANGE: Initially empty agent state (planning phase)
      mockUseAgentState.mockReturnValue(emptyAgentState);

      // Verify planning phase uses issuesData
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('4');

      // Simulate phase transition: now agent state has data
      mockUseAgentState.mockReturnValue({
        ...emptyAgentState,
        tasks: mockTasks,
        completedTasks: mockTasks.filter((t) => t.status === 'completed'),
        blockedTasks: mockTasks.filter((t) => t.status === 'blocked'),
        activeTasks: mockTasks.filter((t) => t.status === 'in_progress'),
      });

      // ACT: Rerender with development phase
      rerender(<TaskStats phase="development" issuesData={mockIssuesData} />);

      // ASSERT: Should now use agent state (8 tasks instead of 4)
      expect(screen.getByTestId('total-tasks')).toHaveTextContent('8');
    });

    it('test_total_tasks_matches_api_total_tasks_field', () => {
      // IMPORTANT: This test verifies consistency between TaskStats calculation
      // and the API's total_tasks field. Both should show the same count.
      // The Dashboard tab badge uses issuesData.total_tasks directly,
      // while TaskStats calculates it from nested tasks.

      // ARRANGE: issuesData with total_tasks matching nested task count
      const consistentIssuesData = {
        issues: [
          {
            id: '1',
            issue_number: '1',
            title: 'Issue 1',
            description: 'Test',
            status: 'pending' as const,
            priority: 1,
            depends_on: [],
            proposed_by: 'agent' as const,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
            completed_at: null,
            tasks: [
              {
                id: '101',
                task_number: '1.1',
                title: 'Task 1',
                description: 'Test',
                status: 'pending' as const,
                depends_on: [],
                proposed_by: 'agent' as const,
                created_at: '2025-01-01T00:00:00Z',
                updated_at: '2025-01-01T00:00:00Z',
                completed_at: null,
              },
            ],
          },
          {
            id: '2',
            issue_number: '2',
            title: 'Issue 2',
            description: 'Test',
            status: 'pending' as const,
            priority: 2,
            depends_on: [],
            proposed_by: 'agent' as const,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
            completed_at: null,
            tasks: [
              {
                id: '201',
                task_number: '2.1',
                title: 'Task 2',
                description: 'Test',
                status: 'pending' as const,
                depends_on: [],
                proposed_by: 'agent' as const,
                created_at: '2025-01-01T00:00:00Z',
                updated_at: '2025-01-01T00:00:00Z',
                completed_at: null,
              },
              {
                id: '202',
                task_number: '2.2',
                title: 'Task 3',
                description: 'Test',
                status: 'pending' as const,
                depends_on: [],
                proposed_by: 'agent' as const,
                created_at: '2025-01-01T00:00:00Z',
                updated_at: '2025-01-01T00:00:00Z',
                completed_at: null,
              },
            ],
          },
        ],
        total_issues: 2,
        total_tasks: 3, // API's precomputed total (1 + 2 = 3)
      };

      mockUseAgentState.mockReturnValue(emptyAgentState);

      // ACT
      render(<TaskStats phase="planning" issuesData={consistentIssuesData} />);

      // ASSERT: TaskStats should show the same count as issuesData.total_tasks
      // This ensures tab badge (using total_tasks) and TaskStats are consistent
      expect(screen.getByTestId('total-tasks')).toHaveTextContent(
        String(consistentIssuesData.total_tasks)
      );
    });
  });
});
