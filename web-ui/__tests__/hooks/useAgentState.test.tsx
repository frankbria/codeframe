/**
 * useAgentState Hook Tests
 *
 * Tests for the custom hook that consumes agent state from Context.
 * Verifies state access, derived state, and action wrappers.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Tasks: T038, T039, T040
 */

import { renderHook, act } from '@testing-library/react';
import { ReactNode } from 'react';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import { useAgentState } from '@/hooks/useAgentState';
import {
  createMockAgent,
  createMockTask,
  createMockActivityItem,
  createMockProjectProgress,
} from '../../test-utils/agentState.fixture';

// Mock SWR
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  })),
}));

// Mock API modules
jest.mock('@/lib/api', () => ({
  agentsApi: { list: jest.fn() },
  tasksApi: { list: jest.fn() },
  activityApi: { list: jest.fn() },
}));

/**
 * Wrapper component for testing hook
 */
function wrapper({ children }: { children: ReactNode }) {
  return <AgentStateProvider projectId={1}>{children}</AgentStateProvider>;
}

describe('useAgentState', () => {
  // ==========================================================================
  // T038: Hook returns state values
  // ==========================================================================
  describe('State Access', () => {
    it('should return initial state values', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      expect(result.current.agents).toEqual([]);
      expect(result.current.tasks).toEqual([]);
      expect(result.current.activity).toEqual([]);
      expect(result.current.projectProgress).toBeNull();
      expect(result.current.wsConnected).toBe(false);
      expect(result.current.lastSyncTimestamp).toBe(0);
    });

    it('should return updated state after dispatch', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const newAgent = createMockAgent({ id: 'test-agent' });

      act(() => {
        result.current.createAgent(newAgent);
      });

      expect(result.current.agents).toHaveLength(1);
      expect(result.current.agents[0]).toEqual(newAgent);
    });

    it('should reflect state changes from multiple actions', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.createAgent(createMockAgent({ id: 'agent-1' }));
        result.current.createAgent(createMockAgent({ id: 'agent-2' }));
        result.current.setWSConnected(true);
      });

      expect(result.current.agents).toHaveLength(2);
      expect(result.current.wsConnected).toBe(true);
    });
  });

  // ==========================================================================
  // T039: Derived state (activeAgents, idleAgents)
  // ==========================================================================
  describe('Derived State', () => {
    it('should compute activeAgents correctly', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.createAgent(
          createMockAgent({ id: 'agent-1', status: 'working' })
        );
        result.current.createAgent(
          createMockAgent({ id: 'agent-2', status: 'idle' })
        );
        result.current.createAgent(
          createMockAgent({ id: 'agent-3', status: 'blocked' })
        );
      });

      // activeAgents = working + blocked
      expect(result.current.activeAgents).toHaveLength(2);
      expect(result.current.activeAgents[0].id).toBe('agent-1');
      expect(result.current.activeAgents[1].id).toBe('agent-3');
    });

    it('should compute idleAgents correctly', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.createAgent(
          createMockAgent({ id: 'agent-1', status: 'working' })
        );
        result.current.createAgent(
          createMockAgent({ id: 'agent-2', status: 'idle' })
        );
        result.current.createAgent(
          createMockAgent({ id: 'agent-3', status: 'idle' })
        );
      });

      expect(result.current.idleAgents).toHaveLength(2);
      expect(result.current.idleAgents[0].id).toBe('agent-2');
      expect(result.current.idleAgents[1].id).toBe('agent-3');
    });

    it('should compute activeTasks correctly', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [
            createMockTask({ id: 1, status: 'in_progress' }),
            createMockTask({ id: 2, status: 'pending' }),
            createMockTask({ id: 3, status: 'in_progress' }),
          ],
          activity: [],
          timestamp: Date.now(),
        });
      });

      expect(result.current.activeTasks).toHaveLength(2);
      expect(result.current.activeTasks[0].id).toBe(1);
      expect(result.current.activeTasks[1].id).toBe(3);
    });

    it('should compute blockedTasks correctly', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [
            createMockTask({ id: 1, status: 'blocked' }),
            createMockTask({ id: 2, status: 'pending' }),
            createMockTask({ id: 3, status: 'blocked' }),
          ],
          activity: [],
          timestamp: Date.now(),
        });
      });

      expect(result.current.blockedTasks).toHaveLength(2);
      expect(result.current.blockedTasks[0].status).toBe('blocked');
    });

    it('should compute pendingTasks correctly', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [
            createMockTask({ id: 1, status: 'pending' }),
            createMockTask({ id: 2, status: 'in_progress' }),
            createMockTask({ id: 3, status: 'pending' }),
          ],
          activity: [],
          timestamp: Date.now(),
        });
      });

      expect(result.current.pendingTasks).toHaveLength(2);
    });

    it('should compute completedTasks correctly', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [
            createMockTask({ id: 1, status: 'completed' }),
            createMockTask({ id: 2, status: 'in_progress' }),
            createMockTask({ id: 3, status: 'completed' }),
          ],
          activity: [],
          timestamp: Date.now(),
        });
      });

      expect(result.current.completedTasks).toHaveLength(2);
    });

    it('should update derived state when underlying state changes', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      // Initially no active agents
      expect(result.current.activeAgents).toHaveLength(0);

      // Add idle agent
      act(() => {
        result.current.createAgent(
          createMockAgent({ id: 'agent-1', status: 'idle', timestamp: 1000 })
        );
      });

      expect(result.current.activeAgents).toHaveLength(0);
      expect(result.current.idleAgents).toHaveLength(1);

      // Update agent to working
      act(() => {
        result.current.updateAgent('agent-1', { status: 'working' }, 2000);
      });

      // Derived state should update
      expect(result.current.activeAgents).toHaveLength(1);
      expect(result.current.idleAgents).toHaveLength(0);
    });
  });

  // ==========================================================================
  // T040: Action wrappers dispatch correctly
  // ==========================================================================
  describe('Action Wrappers', () => {
    it('should dispatch loadAgents action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const agents = [
        createMockAgent({ id: 'agent-1' }),
        createMockAgent({ id: 'agent-2' }),
      ];

      act(() => {
        result.current.loadAgents(agents);
      });

      expect(result.current.agents).toEqual(agents);
    });

    it('should dispatch createAgent action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const newAgent = createMockAgent({ id: 'new-agent' });

      act(() => {
        result.current.createAgent(newAgent);
      });

      expect(result.current.agents).toHaveLength(1);
      expect(result.current.agents[0]).toEqual(newAgent);
    });

    it('should dispatch updateAgent action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.createAgent(
          createMockAgent({ id: 'agent-1', status: 'idle', timestamp: 1000 })
        );
      });

      act(() => {
        result.current.updateAgent('agent-1', { status: 'working' }, 2000);
      });

      expect(result.current.agents[0].status).toBe('working');
    });

    it('should dispatch retireAgent action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.createAgent(createMockAgent({ id: 'agent-1' }));
        result.current.createAgent(createMockAgent({ id: 'agent-2' }));
      });

      expect(result.current.agents).toHaveLength(2);

      act(() => {
        result.current.retireAgent('agent-1', Date.now());
      });

      expect(result.current.agents).toHaveLength(1);
      expect(result.current.agents[0].id).toBe('agent-2');
    });

    it('should dispatch assignTask action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const agent = createMockAgent({ id: 'agent-1', status: 'idle' });
      const task = createMockTask({ id: 1, status: 'pending' });

      act(() => {
        result.current.fullResync({
          agents: [agent],
          tasks: [task],
          activity: [],
          timestamp: Date.now(),
        });
      });

      act(() => {
        result.current.assignTask(1, 'agent-1', 1, 'Test Task', Date.now());
      });

      expect(result.current.agents[0].status).toBe('working');
      expect(result.current.agents[0].current_task).toEqual({
        id: 1,
        title: 'Test Task',
      });
      expect(result.current.tasks[0].status).toBe('in_progress');
      expect(result.current.tasks[0].agent_id).toBe('agent-1');
    });

    it('should dispatch updateTaskStatus action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [createMockTask({ id: 1, status: 'pending' })],
          activity: [],
          timestamp: Date.now(),
        });
      });

      act(() => {
        result.current.updateTaskStatus(1, 'in_progress', 50, Date.now());
      });

      expect(result.current.tasks[0].status).toBe('in_progress');
      expect(result.current.tasks[0].progress).toBe(50);
    });

    it('should dispatch blockTask action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [createMockTask({ id: 2, status: 'pending' })],
          activity: [],
          timestamp: Date.now(),
        });
      });

      act(() => {
        result.current.blockTask(2, [1], Date.now());
      });

      expect(result.current.tasks[0].status).toBe('blocked');
      expect(result.current.tasks[0].blocked_by).toEqual([1]);
    });

    it('should dispatch unblockTask action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      act(() => {
        result.current.fullResync({
          agents: [],
          tasks: [createMockTask({ id: 1, status: 'blocked', blocked_by: [2] })],
          activity: [],
          timestamp: Date.now(),
        });
      });

      act(() => {
        result.current.unblockTask(1, Date.now());
      });

      expect(result.current.tasks[0].status).toBe('pending');
      expect(result.current.tasks[0].blocked_by).toBeUndefined();
    });

    it('should dispatch addActivity action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const activityItem = createMockActivityItem();

      act(() => {
        result.current.addActivity(activityItem);
      });

      expect(result.current.activity).toHaveLength(1);
      expect(result.current.activity[0]).toEqual(activityItem);
    });

    it('should dispatch updateProgress action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const progress = createMockProjectProgress({
        completed_tasks: 5,
        total_tasks: 10,
        percentage: 50,
      });

      act(() => {
        result.current.updateProgress(progress);
      });

      expect(result.current.projectProgress).toEqual(progress);
    });

    it('should dispatch setWSConnected action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      expect(result.current.wsConnected).toBe(false);

      act(() => {
        result.current.setWSConnected(true);
      });

      expect(result.current.wsConnected).toBe(true);
    });

    it('should dispatch fullResync action', () => {
      const { result } = renderHook(() => useAgentState(), { wrapper });

      const syncPayload = {
        agents: [createMockAgent({ id: 'agent-1' })],
        tasks: [createMockTask({ id: 1 })],
        activity: [createMockActivityItem()],
        timestamp: Date.now(),
      };

      act(() => {
        result.current.fullResync(syncPayload);
      });

      expect(result.current.agents).toEqual(syncPayload.agents);
      expect(result.current.tasks).toEqual(syncPayload.tasks);
      expect(result.current.activity).toEqual(syncPayload.activity);
      expect(result.current.wsConnected).toBe(true);
    });
  });

  // ==========================================================================
  // Error Handling
  // ==========================================================================
  describe('Error Handling', () => {
    it('should throw error when used outside Provider', () => {
      // Suppress console.error for this test
      const consoleError = jest.spyOn(console, 'error').mockImplementation();

      expect(() => {
        renderHook(() => useAgentState());
      }).toThrow('useAgentState must be used within an AgentStateProvider');

      consoleError.mockRestore();
    });
  });
});
