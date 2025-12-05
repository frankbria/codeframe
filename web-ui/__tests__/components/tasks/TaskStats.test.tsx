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
});
