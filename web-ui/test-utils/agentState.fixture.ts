/**
 * Test Fixtures for Agent State Management
 *
 * Mock data for testing agent state reducer, Context, and components
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 */

import type {
  Agent,
  Task,
  ActivityItem,
  ProjectProgress,
  AgentState,
  AgentType,
  AgentStatus,
  TaskStatus,
} from '@/types/agentState';

/**
 * Create a mock agent with default values
 */
export function createMockAgent(overrides?: Partial<Agent>): Agent {
  return {
    id: 'backend-worker-1',
    type: 'backend-worker',
    status: 'idle',
    provider: 'anthropic',
    maturity: 'directive',
    context_tokens: 0,
    tasks_completed: 0,
    timestamp: Date.now(),
    ...overrides,
  };
}

/**
 * Create a mock task with default values
 */
export function createMockTask(overrides?: Partial<Task>): Task {
  return {
    id: 1,
    title: 'Implement authentication',
    status: 'pending',
    timestamp: Date.now(),
    ...overrides,
  };
}

/**
 * Create a mock activity item with default values
 */
export function createMockActivityItem(overrides?: Partial<ActivityItem>): ActivityItem {
  return {
    timestamp: new Date().toISOString(),
    type: 'task_assigned',
    agent: 'backend-worker-1',
    message: 'Assigned task #1 to backend-worker-1',
    ...overrides,
  };
}

/**
 * Create mock project progress
 */
export function createMockProjectProgress(overrides?: Partial<ProjectProgress>): ProjectProgress {
  return {
    completed_tasks: 0,
    total_tasks: 10,
    percentage: 0,
    ...overrides,
  };
}

/**
 * Create initial agent state for testing
 */
export function createInitialAgentState(overrides?: Partial<AgentState>): AgentState {
  return {
    agents: [],
    tasks: [],
    activity: [],
    projectProgress: null,
    wsConnected: false,
    lastSyncTimestamp: 0,
    ...overrides,
  };
}

/**
 * Create a populated agent state for testing
 */
export function createPopulatedAgentState(): AgentState {
  return {
    agents: [
      createMockAgent({
        id: 'backend-worker-1',
        type: 'backend-worker',
        status: 'working',
        current_task: { id: 1, title: 'Implement auth' },
        timestamp: Date.now(),
      }),
      createMockAgent({
        id: 'frontend-specialist-1',
        type: 'frontend-specialist',
        status: 'idle',
        timestamp: Date.now(),
      }),
      createMockAgent({
        id: 'test-engineer-1',
        type: 'test-engineer',
        status: 'blocked',
        blocker: 'Waiting for API endpoints',
        timestamp: Date.now(),
      }),
    ],
    tasks: [
      createMockTask({
        id: 1,
        title: 'Implement authentication',
        status: 'in_progress',
        agent_id: 'backend-worker-1',
        timestamp: Date.now(),
      }),
      createMockTask({
        id: 2,
        title: 'Create login UI',
        status: 'blocked',
        blocked_by: [1],
        timestamp: Date.now(),
      }),
      createMockTask({
        id: 3,
        title: 'Write unit tests',
        status: 'pending',
        timestamp: Date.now(),
      }),
    ],
    activity: [
      createMockActivityItem({
        type: 'task_assigned',
        agent: 'backend-worker-1',
        message: 'Assigned task #1 to backend-worker-1',
      }),
      createMockActivityItem({
        type: 'agent_created',
        agent: 'system',
        message: '🤖 Created backend-worker agent (backend-worker-1)',
      }),
    ],
    projectProgress: createMockProjectProgress({
      completed_tasks: 0,
      total_tasks: 3,
      percentage: 0,
    }),
    wsConnected: true,
    lastSyncTimestamp: Date.now(),
  };
}

/**
 * Create array of N mock agents
 */
export function createMockAgents(count: number, startIndex: number = 1): Agent[] {
  const types: AgentType[] = ['backend-worker', 'frontend-specialist', 'test-engineer'];
  const statuses: AgentStatus[] = ['idle', 'working', 'blocked'];

  return Array.from({ length: count }, (_, i) => {
    const index = startIndex + i;
    const type = types[i % types.length];
    const status = statuses[i % statuses.length];

    return createMockAgent({
      id: `${type}-${index}`,
      type,
      status,
      timestamp: Date.now() + i, // Slightly different timestamps
    });
  });
}

/**
 * Create array of N mock tasks
 */
export function createMockTasks(count: number, startId: number = 1): Task[] {
  const statuses: TaskStatus[] = ['pending', 'in_progress', 'blocked', 'completed'];

  return Array.from({ length: count }, (_, i) => {
    const id = startId + i;
    const status = statuses[i % statuses.length];

    return createMockTask({
      id,
      title: `Task #${id}`,
      status,
      timestamp: Date.now() + i,
    });
  });
}

/**
 * Create array of N mock activity items
 */
export function createMockActivityItems(count: number): ActivityItem[] {
  return Array.from({ length: count }, (_, i) => {
    return createMockActivityItem({
      message: `Activity item ${i + 1}`,
    });
  });
}

/**
 * Create a state with 10 agents (max limit) for testing
 */
export function createStateWithMaxAgents(): AgentState {
  return createInitialAgentState({
    agents: createMockAgents(10),
    wsConnected: true,
  });
}

/**
 * Create a state with 11 agents (over limit) for testing warnings
 */
export function createStateWithTooManyAgents(): AgentState {
  return createInitialAgentState({
    agents: createMockAgents(11),
    wsConnected: true,
  });
}

/**
 * Create a state with 50 activity items (max limit) for testing
 */
export function createStateWithMaxActivity(): AgentState {
  return createInitialAgentState({
    activity: createMockActivityItems(50),
    wsConnected: true,
  });
}

/**
 * Create two agents with conflicting timestamps for testing conflict resolution
 */
export function createAgentsWithConflictingTimestamps(): {
  olderAgent: Agent;
  newerAgent: Agent;
} {
  const baseTimestamp = Date.now();

  return {
    olderAgent: createMockAgent({
      id: 'test-agent-1',
      status: 'idle',
      timestamp: baseTimestamp - 1000, // 1 second older
    }),
    newerAgent: createMockAgent({
      id: 'test-agent-1',
      status: 'working',
      timestamp: baseTimestamp, // Current time
    }),
  };
}
