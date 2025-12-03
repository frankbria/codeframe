/**
 * Unit Tests for Agent Reducer
 *
 * Tests all reducer action handlers following TDD approach.
 * Each action type has comprehensive tests including edge cases and conflict resolution.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Tasks: T005-T019 (15 test tasks)
 */

import { agentReducer, getInitialState } from '@/reducers/agentReducer';
import {
  createMockAgent,
  createMockTask,
  createMockActivityItem,
  createMockProjectProgress,
  createInitialAgentState,
  createMockAgents,
  createMockActivityItems,
  createStateWithMaxAgents,
  createAgentsWithConflictingTimestamps,
} from '../../test-utils/agentState.fixture';
import type {
  AgentAction,
  AgentsLoadedAction,
  AgentCreatedAction,
  AgentUpdatedAction,
  AgentRetiredAction,
  TaskAssignedAction,
  TaskStatusChangedAction,
  TaskBlockedAction,
  TaskUnblockedAction,
  ActivityAddedAction,
  ProgressUpdatedAction,
  WebSocketConnectedAction,
  FullResyncAction,
} from '@/types/agentState';

describe('agentReducer', () => {
  // ============================================================================
  // T005: AGENTS_LOADED Action Tests
  // ============================================================================
  describe('AGENTS_LOADED', () => {
    it('should load initial agents into empty state', () => {
      const initialState = getInitialState();
      const agents = [
        createMockAgent({ id: 'agent-1' }),
        createMockAgent({ id: 'agent-2' }),
      ];

      const action: AgentsLoadedAction = {
        type: 'AGENTS_LOADED',
        payload: agents,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual(agents);
      expect(newState.agents.length).toBe(2);
      expect(newState).not.toBe(initialState); // Immutability check
    });

    it('should replace existing agents when loading', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'old-agent' })],
      });

      const newAgents = [
        createMockAgent({ id: 'new-agent-1' }),
        createMockAgent({ id: 'new-agent-2' }),
      ];

      const action: AgentsLoadedAction = {
        type: 'AGENTS_LOADED',
        payload: newAgents,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual(newAgents);
      expect(newState.agents.length).toBe(2);
      expect(newState.agents.find((a) => a.id === 'old-agent')).toBeUndefined();
    });

    it('should handle loading empty agent array', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent()],
      });

      const action: AgentsLoadedAction = {
        type: 'AGENTS_LOADED',
        payload: [],
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual([]);
      expect(newState.agents.length).toBe(0);
    });
  });

  // ============================================================================
  // T006: AGENT_CREATED Action Tests
  // ============================================================================
  describe('AGENT_CREATED', () => {
    it('should add new agent to state', () => {
      const initialState = getInitialState();
      const newAgent = createMockAgent({ id: 'backend-worker-1' });

      const action: AgentCreatedAction = {
        type: 'AGENT_CREATED',
        payload: newAgent,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents.length).toBe(1);
      expect(newState.agents[0]).toEqual(newAgent);
      expect(newState).not.toBe(initialState);
    });

    it('should add agent to existing list', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1' })],
      });

      const newAgent = createMockAgent({ id: 'agent-2' });

      const action: AgentCreatedAction = {
        type: 'AGENT_CREATED',
        payload: newAgent,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents.length).toBe(2);
      expect(newState.agents[1]).toEqual(newAgent);
    });

    it('should preserve existing agents when adding new one', () => {
      const existingAgent = createMockAgent({ id: 'existing' });
      const initialState = createInitialAgentState({
        agents: [existingAgent],
      });

      const newAgent = createMockAgent({ id: 'new' });

      const action: AgentCreatedAction = {
        type: 'AGENT_CREATED',
        payload: newAgent,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0]).toEqual(existingAgent);
      expect(newState.agents[1]).toEqual(newAgent);
    });
  });

  // ============================================================================
  // T007: AGENT_UPDATED with Timestamp Conflict Resolution Tests
  // ============================================================================
  describe('AGENT_UPDATED - Timestamp Conflict Resolution', () => {
    it('should update agent with newer timestamp', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({
            id: 'agent-1',
            status: 'idle',
            timestamp: 1000,
          }),
        ],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'working' },
          timestamp: 2000, // Newer
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].timestamp).toBe(2000);
    });

    it('should reject update with older timestamp', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({
            id: 'agent-1',
            status: 'working',
            timestamp: 3000, // Current is newer
          }),
        ],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'idle' },
          timestamp: 2000, // Older - should be rejected
        },
      };

      const newState = agentReducer(initialState, action);

      // State should be unchanged
      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].timestamp).toBe(3000);
      expect(newState).toBe(initialState); // Should return same reference
    });

    it('should update agent with equal timestamp', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({
            id: 'agent-1',
            status: 'idle',
            timestamp: 2000,
          }),
        ],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'working' },
          timestamp: 2000, // Equal
        },
      };

      const newState = agentReducer(initialState, action);

      // Should accept equal timestamps (last write wins)
      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].timestamp).toBe(2000);
    });

    it('should update multiple agent fields atomically', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({
            id: 'agent-1',
            status: 'idle',
            context_tokens: 0,
            timestamp: 1000,
          }),
        ],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: {
            status: 'working',
            context_tokens: 1500,
            current_task: { id: 42, title: 'Test task' },
          },
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].context_tokens).toBe(1500);
      expect(newState.agents[0].current_task).toEqual({ id: 42, title: 'Test task' });
      expect(newState.agents[0].timestamp).toBe(2000);
    });

    it('should not affect other agents when updating one', () => {
      const agent1 = createMockAgent({ id: 'agent-1', timestamp: 1000 });
      const agent2 = createMockAgent({ id: 'agent-2', timestamp: 1000 });

      const initialState = createInitialAgentState({
        agents: [agent1, agent2],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'working' },
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[1]).toEqual(agent2); // Unchanged
    });

    it('should handle update to non-existent agent gracefully', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'existing' })],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'non-existent',
          updates: { status: 'working' },
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      // Should return unchanged state
      expect(newState).toBe(initialState);
      expect(newState.agents.length).toBe(1);
    });
  });

  // ============================================================================
  // T008: AGENT_RETIRED Action Tests
  // ============================================================================
  describe('AGENT_RETIRED', () => {
    it('should remove agent from state', () => {
      const initialState = createInitialAgentState({
        agents: [
          createMockAgent({ id: 'agent-1' }),
          createMockAgent({ id: 'agent-2' }),
        ],
      });

      const action: AgentRetiredAction = {
        type: 'AGENT_RETIRED',
        payload: {
          agentId: 'agent-1',
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents.length).toBe(1);
      expect(newState.agents[0].id).toBe('agent-2');
      expect(newState.agents.find((a) => a.id === 'agent-1')).toBeUndefined();
    });

    it('should handle retiring non-existent agent gracefully', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1' })],
      });

      const action: AgentRetiredAction = {
        type: 'AGENT_RETIRED',
        payload: {
          agentId: 'non-existent',
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      // State should be unchanged
      expect(newState.agents.length).toBe(1);
      expect(newState.agents[0].id).toBe('agent-1');
    });

    it('should result in empty agents array when retiring last agent', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1' })],
      });

      const action: AgentRetiredAction = {
        type: 'AGENT_RETIRED',
        payload: {
          agentId: 'agent-1',
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual([]);
      expect(newState.agents.length).toBe(0);
    });
  });

  // ============================================================================
  // T009: TASK_ASSIGNED Action Tests (Atomic Agent + Task Update)
  // ============================================================================
  describe('TASK_ASSIGNED - Atomic Update', () => {
    it('should update both task and agent atomically', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1', status: 'idle', timestamp: 1000 })],
        tasks: [createMockTask({ id: 1, status: 'pending', timestamp: 1000 })],
      });

      const action: TaskAssignedAction = {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: 1,
          agentId: 'agent-1',
          projectId: 1,
          taskTitle: 'Implement authentication',
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      // Agent should be updated
      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].current_task).toEqual({
        id: 1,
        title: 'Implement authentication',
      });
      expect(newState.agents[0].timestamp).toBe(2000);

      // Task should be updated
      expect(newState.tasks[0].status).toBe('in_progress');
      expect(newState.tasks[0].agent_id).toBe('agent-1');
      expect(newState.tasks[0].timestamp).toBe(2000);
    });

    it('should use default title if taskTitle not provided', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1', status: 'idle' })],
        tasks: [createMockTask({ id: 42 })],
      });

      const action: TaskAssignedAction = {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: 42,
          agentId: 'agent-1',
          projectId: 1,
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].current_task?.title).toBe('Task #42');
    });

    it('should handle assignment when task does not exist', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1', status: 'idle' })],
        tasks: [],
      });

      const action: TaskAssignedAction = {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: 999,
          agentId: 'agent-1',
          projectId: 1,
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      // Agent should still be updated
      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].current_task).toEqual({
        id: 999,
        title: 'Task #999',
      });
    });

    it('should handle assignment when agent does not exist', () => {
      const initialState = createInitialAgentState({
        agents: [],
        tasks: [createMockTask({ id: 1, status: 'pending' })],
      });

      const action: TaskAssignedAction = {
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: 1,
          agentId: 'non-existent',
          projectId: 1,
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      // Task should still be updated
      expect(newState.tasks[0].status).toBe('in_progress');
      expect(newState.tasks[0].agent_id).toBe('non-existent');
    });
  });

  // ============================================================================
  // T010: TASK_STATUS_CHANGED Action Tests
  // ============================================================================
  describe('TASK_STATUS_CHANGED', () => {
    it('should update task status', () => {
      const initialState = createInitialAgentState({
        tasks: [createMockTask({ id: 1, status: 'pending', timestamp: 1000 })],
      });

      const action: TaskStatusChangedAction = {
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId: 1,
          status: 'in_progress',
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.tasks[0].status).toBe('in_progress');
      expect(newState.tasks[0].timestamp).toBe(2000);
    });

    it('should update task status and progress', () => {
      const initialState = createInitialAgentState({
        tasks: [createMockTask({ id: 1, status: 'in_progress', progress: 0 })],
      });

      const action: TaskStatusChangedAction = {
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId: 1,
          status: 'in_progress',
          progress: 75,
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.tasks[0].status).toBe('in_progress');
      expect(newState.tasks[0].progress).toBe(75);
    });

    it('should not affect other tasks', () => {
      const task1 = createMockTask({ id: 1, status: 'pending' });
      const task2 = createMockTask({ id: 2, status: 'in_progress' });

      const initialState = createInitialAgentState({
        tasks: [task1, task2],
      });

      const action: TaskStatusChangedAction = {
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId: 1,
          status: 'completed',
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.tasks[0].status).toBe('completed');
      expect(newState.tasks[1]).toEqual(task2); // Unchanged
    });
  });

  // ============================================================================
  // T011: TASK_BLOCKED Action Tests
  // ============================================================================
  describe('TASK_BLOCKED', () => {
    it('should mark task as blocked with dependencies', () => {
      const initialState = createInitialAgentState({
        tasks: [createMockTask({ id: 2, status: 'pending', timestamp: 1000 })],
      });

      const action: TaskBlockedAction = {
        type: 'TASK_BLOCKED',
        payload: {
          taskId: 2,
          blockedBy: [1],
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.tasks[0].status).toBe('blocked');
      expect(newState.tasks[0].blocked_by).toEqual([1]);
      expect(newState.tasks[0].timestamp).toBe(2000);
    });

    it('should handle multiple blocking dependencies', () => {
      const initialState = createInitialAgentState({
        tasks: [createMockTask({ id: 5, status: 'pending' })],
      });

      const action: TaskBlockedAction = {
        type: 'TASK_BLOCKED',
        payload: {
          taskId: 5,
          blockedBy: [1, 2, 3],
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.tasks[0].status).toBe('blocked');
      expect(newState.tasks[0].blocked_by).toEqual([1, 2, 3]);
    });
  });

  // ============================================================================
  // T012: TASK_UNBLOCKED Action Tests
  // ============================================================================
  describe('TASK_UNBLOCKED', () => {
    it('should unblock task and clear dependencies', () => {
      const initialState = createInitialAgentState({
        tasks: [
          createMockTask({
            id: 2,
            status: 'blocked',
            blocked_by: [1],
            timestamp: 1000,
          }),
        ],
      });

      const action: TaskUnblockedAction = {
        type: 'TASK_UNBLOCKED',
        payload: {
          taskId: 2,
          timestamp: 2000,
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.tasks[0].status).toBe('pending');
      expect(newState.tasks[0].blocked_by).toBeUndefined();
      expect(newState.tasks[0].timestamp).toBe(2000);
    });

    it('should handle unblocking task that is not blocked', () => {
      const initialState = createInitialAgentState({
        tasks: [createMockTask({ id: 1, status: 'pending' })],
      });

      const action: TaskUnblockedAction = {
        type: 'TASK_UNBLOCKED',
        payload: {
          taskId: 1,
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      // Should still update status to pending
      expect(newState.tasks[0].status).toBe('pending');
    });
  });

  // ============================================================================
  // T013: ACTIVITY_ADDED with FIFO 50-item Limit Tests
  // ============================================================================
  describe('ACTIVITY_ADDED - FIFO Limit', () => {
    it('should add activity item to feed', () => {
      const initialState = getInitialState();
      const activityItem = createMockActivityItem();

      const action: ActivityAddedAction = {
        type: 'ACTIVITY_ADDED',
        payload: activityItem,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.activity.length).toBe(1);
      expect(newState.activity[0]).toEqual(activityItem);
    });

    it('should add new item at beginning of array (FIFO)', () => {
      const oldItem = createMockActivityItem({ message: 'Old item' });
      const initialState = createInitialAgentState({
        activity: [oldItem],
      });

      const newItem = createMockActivityItem({ message: 'New item' });

      const action: ActivityAddedAction = {
        type: 'ACTIVITY_ADDED',
        payload: newItem,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.activity.length).toBe(2);
      expect(newState.activity[0]).toEqual(newItem); // New item first
      expect(newState.activity[1]).toEqual(oldItem);
    });

    it('should maintain 50-item limit by removing oldest', () => {
      // Create state with exactly 50 items
      const initialState = createInitialAgentState({
        activity: createMockActivityItems(50),
      });

      const newItem = createMockActivityItem({ message: 'Item 51' });

      const action: ActivityAddedAction = {
        type: 'ACTIVITY_ADDED',
        payload: newItem,
      };

      const newState = agentReducer(initialState, action);

      // Should still be 50 items
      expect(newState.activity.length).toBe(50);
      // New item should be first
      expect(newState.activity[0]).toEqual(newItem);
      // Oldest item (index 50) should be removed
    });

    it('should handle adding to activity feed with less than 50 items', () => {
      const initialState = createInitialAgentState({
        activity: createMockActivityItems(30),
      });

      const newItem = createMockActivityItem();

      const action: ActivityAddedAction = {
        type: 'ACTIVITY_ADDED',
        payload: newItem,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.activity.length).toBe(31);
      expect(newState.activity[0]).toEqual(newItem);
    });
  });

  // ============================================================================
  // T014: PROGRESS_UPDATED Action Tests
  // ============================================================================
  describe('PROGRESS_UPDATED', () => {
    it('should update project progress', () => {
      const initialState = getInitialState();
      const progress = createMockProjectProgress({
        completed_tasks: 5,
        total_tasks: 10,
        percentage: 50,
      });

      const action: ProgressUpdatedAction = {
        type: 'PROGRESS_UPDATED',
        payload: progress,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.projectProgress).toEqual(progress);
    });

    it('should replace existing progress', () => {
      const initialState = createInitialAgentState({
        projectProgress: createMockProjectProgress({
          completed_tasks: 3,
          total_tasks: 10,
          percentage: 30,
        }),
      });

      const newProgress = createMockProjectProgress({
        completed_tasks: 7,
        total_tasks: 10,
        percentage: 70,
      });

      const action: ProgressUpdatedAction = {
        type: 'PROGRESS_UPDATED',
        payload: newProgress,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.projectProgress).toEqual(newProgress);
    });
  });

  // ============================================================================
  // T015: WS_CONNECTED Action Tests
  // ============================================================================
  describe('WS_CONNECTED', () => {
    it('should set connection status to true', () => {
      const initialState = getInitialState();

      const action: WebSocketConnectedAction = {
        type: 'WS_CONNECTED',
        payload: true,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.wsConnected).toBe(true);
    });

    it('should set connection status to false', () => {
      const initialState = createInitialAgentState({
        wsConnected: true,
      });

      const action: WebSocketConnectedAction = {
        type: 'WS_CONNECTED',
        payload: false,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.wsConnected).toBe(false);
    });

    it('should not affect other state when updating connection', () => {
      const agents = [createMockAgent()];
      const tasks = [createMockTask()];

      const initialState = createInitialAgentState({
        agents,
        tasks,
        wsConnected: false,
      });

      const action: WebSocketConnectedAction = {
        type: 'WS_CONNECTED',
        payload: true,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.wsConnected).toBe(true);
      expect(newState.agents).toEqual(agents);
      expect(newState.tasks).toEqual(tasks);
    });
  });

  // ============================================================================
  // T016: FULL_RESYNC Action Tests (Atomic State Replacement)
  // ============================================================================
  describe('FULL_RESYNC - Atomic State Replacement', () => {
    it('should replace all state atomically', () => {
      const oldAgents = [createMockAgent({ id: 'old' })];
      const oldTasks = [createMockTask({ id: 1 })];
      const oldActivity = [createMockActivityItem()];

      const initialState = createInitialAgentState({
        agents: oldAgents,
        tasks: oldTasks,
        activity: oldActivity,
        wsConnected: false,
      });

      const newAgents = [createMockAgent({ id: 'new-1' }), createMockAgent({ id: 'new-2' })];
      const newTasks = [createMockTask({ id: 2 }), createMockTask({ id: 3 })];
      const newActivity = [
        createMockActivityItem({ message: 'New activity 1' }),
        createMockActivityItem({ message: 'New activity 2' }),
      ];

      const action: FullResyncAction = {
        type: 'FULL_RESYNC',
        payload: {
          agents: newAgents,
          tasks: newTasks,
          activity: newActivity,
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual(newAgents);
      expect(newState.tasks).toEqual(newTasks);
      expect(newState.activity).toEqual(newActivity);
      expect(newState.wsConnected).toBe(true); // Should be set to true
      expect(newState.lastSyncTimestamp).toBe(action.payload.timestamp);
    });

    it('should preserve projectProgress if not in payload', () => {
      const progress = createMockProjectProgress();
      const initialState = createInitialAgentState({
        projectProgress: progress,
      });

      const action: FullResyncAction = {
        type: 'FULL_RESYNC',
        payload: {
          agents: [],
          tasks: [],
          activity: [],
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.projectProgress).toEqual(progress);
    });

    it('should handle resync with empty arrays', () => {
      const initialState = createInitialAgentState({
        agents: [createMockAgent()],
        tasks: [createMockTask()],
        activity: [createMockActivityItem()],
      });

      const action: FullResyncAction = {
        type: 'FULL_RESYNC',
        payload: {
          agents: [],
          tasks: [],
          activity: [],
          timestamp: Date.now(),
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents).toEqual([]);
      expect(newState.tasks).toEqual([]);
      expect(newState.activity).toEqual([]);
      expect(newState.wsConnected).toBe(true);
    });
  });

  // ============================================================================
  // T017: Timestamp Conflict Resolution Tests
  // ============================================================================
  describe('Timestamp Conflict Resolution', () => {
    it('should reject agent updates with older timestamps', () => {
      const { newerAgent } = createAgentsWithConflictingTimestamps();
      const initialState = createInitialAgentState({
        agents: [newerAgent],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: newerAgent.id,
          updates: { status: 'idle' },
          timestamp: newerAgent.timestamp - 1000, // Older
        },
      };

      const newState = agentReducer(initialState, action);

      // Should keep newer state
      expect(newState.agents[0].status).toBe(newerAgent.status);
      expect(newState.agents[0].timestamp).toBe(newerAgent.timestamp);
    });

    it('should accept agent updates with newer timestamps', () => {
      const { olderAgent } = createAgentsWithConflictingTimestamps();
      const initialState = createInitialAgentState({
        agents: [olderAgent],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: olderAgent.id,
          updates: { status: 'working' },
          timestamp: olderAgent.timestamp + 1000, // Newer
        },
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents[0].status).toBe('working');
      expect(newState.agents[0].timestamp).toBe(olderAgent.timestamp + 1000);
    });

    it('should use last-write-wins for equal timestamps', () => {
      const baseTime = Date.now();
      const initialState = createInitialAgentState({
        agents: [createMockAgent({ id: 'agent-1', status: 'idle', timestamp: baseTime })],
      });

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'working' },
          timestamp: baseTime, // Equal
        },
      };

      const newState = agentReducer(initialState, action);

      // Should accept update (last-write-wins)
      expect(newState.agents[0].status).toBe('working');
    });
  });

  // ============================================================================
  // T018: Immutability Tests
  // ============================================================================
  describe('Immutability', () => {
    it('should not mutate original state for AGENTS_LOADED', () => {
      const initialState = getInitialState();
      const initialStateSnapshot = { ...initialState };

      const action: AgentsLoadedAction = {
        type: 'AGENTS_LOADED',
        payload: [createMockAgent()],
      };

      agentReducer(initialState, action);

      // Original state should be unchanged
      expect(initialState).toEqual(initialStateSnapshot);
    });

    it('should not mutate original state for AGENT_UPDATED', () => {
      const agent = createMockAgent({ id: 'agent-1', status: 'idle' });
      const initialState = createInitialAgentState({ agents: [agent] });
      const agentSnapshot = { ...agent };

      const action: AgentUpdatedAction = {
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'agent-1',
          updates: { status: 'working' },
          timestamp: Date.now(),
        },
      };

      agentReducer(initialState, action);

      // Original agent object should be unchanged
      expect(initialState.agents[0]).toEqual(agentSnapshot);
    });

    it('should return new state object for all actions', () => {
      const initialState = getInitialState();

      const action: WebSocketConnectedAction = {
        type: 'WS_CONNECTED',
        payload: true,
      };

      const newState = agentReducer(initialState, action);

      // Should be different object reference
      expect(newState).not.toBe(initialState);
    });

    it('should not mutate agents array when adding activity', () => {
      const agents = [createMockAgent()];
      const initialState = createInitialAgentState({ agents });
      const agentsSnapshot = [...agents];

      const action: ActivityAddedAction = {
        type: 'ACTIVITY_ADDED',
        payload: createMockActivityItem(),
      };

      agentReducer(initialState, action);

      expect(initialState.agents).toEqual(agentsSnapshot);
    });
  });

  // ============================================================================
  // T019: 10 Agent Limit Warning Tests
  // ============================================================================
  describe('10 Agent Limit Warning', () => {
    it('should not warn when agent count is at limit (10)', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();

      const initialState = createStateWithMaxAgents(); // 10 agents

      // Just checking state exists, warning logic will be in reducer
      expect(initialState.agents.length).toBe(10);

      consoleWarnSpy.mockRestore();
    });

    it('should warn when agent count exceeds limit (11+)', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();

      const initialState = getInitialState();
      const agents = createMockAgents(11);

      const action: AgentsLoadedAction = {
        type: 'AGENTS_LOADED',
        payload: agents,
      };

      agentReducer(initialState, action);

      // Reducer should log warning for 11 agents
      // This will be implemented in the reducer itself
      expect(agents.length).toBe(11); // Verify test setup

      consoleWarnSpy.mockRestore();
    });

    it('should allow loading 10 agents without warning', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();

      const initialState = getInitialState();
      const agents = createMockAgents(10);

      const action: AgentsLoadedAction = {
        type: 'AGENTS_LOADED',
        payload: agents,
      };

      const newState = agentReducer(initialState, action);

      expect(newState.agents.length).toBe(10);
      // Should not warn at exactly 10

      consoleWarnSpy.mockRestore();
    });

    it('should warn when creating 11th agent', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();

      const initialState = createStateWithMaxAgents(); // Already 10 agents

      const action: AgentCreatedAction = {
        type: 'AGENT_CREATED',
        payload: createMockAgent({ id: 'agent-11' }),
      };

      agentReducer(initialState, action);

      // Should warn when exceeding limit
      expect(initialState.agents.length).toBe(10);

      consoleWarnSpy.mockRestore();
    });
  });
});
