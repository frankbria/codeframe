/**
 * useAgentState Hook
 *
 * Custom hook for consuming agent state from Context.
 * Provides state, derived state, and action wrapper functions.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Tasks: T045, T046, T047, T048
 */

'use client';

import { useContext, useMemo, useCallback } from 'react';
import { AgentStateContext } from '@/contexts/AgentStateContext';
import type {
  Agent,
  Task,
  ActivityItem,
  ProjectProgress,

  TaskStatus,
} from '@/types/agentState';

/**
 * Return type for useAgentState hook
 *
 * Includes state, derived state, and action wrapper functions
 */
export interface UseAgentStateReturn {
  // ============================================================================
  // Raw State
  // ============================================================================

  /** All agents */
  agents: Agent[];

  /** All tasks */
  tasks: Task[];

  /** Activity feed (max 50 items) */
  activity: ActivityItem[];

  /** Project progress */
  projectProgress: ProjectProgress | null;

  /** WebSocket connection status */
  wsConnected: boolean;

  /** Last full resync timestamp */
  lastSyncTimestamp: number;

  // ============================================================================
  // Derived State (Memoized)
  // ============================================================================

  /** Agents that are currently working or blocked */
  activeAgents: Agent[];

  /** Agents that are idle */
  idleAgents: Agent[];

  /** Tasks that are in progress */
  activeTasks: Task[];

  /** Tasks that are blocked */
  blockedTasks: Task[];

  /** Tasks that are pending */
  pendingTasks: Task[];

  /** Tasks that are completed */
  completedTasks: Task[];

  // ============================================================================
  // Action Wrapper Functions (useCallback)
  // ============================================================================

  /** Load initial agents */
  loadAgents: (agents: Agent[]) => void;

  /** Create new agent */
  createAgent: (agent: Agent) => void;

  /** Update agent (partial) */
  updateAgent: (agentId: string, updates: Partial<Agent>, timestamp: number) => void;

  /** Retire/remove agent */
  retireAgent: (agentId: string, timestamp: number) => void;

  /** Assign task to agent */
  assignTask: (
    taskId: number,
    agentId: string,
    taskTitle: string | undefined,
    timestamp: number
  ) => void;

  /** Update task status */
  updateTaskStatus: (
    taskId: number,
    status: TaskStatus,
    progress: number | undefined,
    timestamp: number
  ) => void;

  /** Block task */
  blockTask: (taskId: number, blockedBy: number[], timestamp: number) => void;

  /** Unblock task */
  unblockTask: (taskId: number, timestamp: number) => void;

  /** Add activity item */
  addActivity: (item: ActivityItem) => void;

  /** Update project progress */
  updateProgress: (progress: ProjectProgress) => void;

  /** Set WebSocket connection status */
  setWSConnected: (connected: boolean) => void;

  /** Full state resync (after reconnect) */
  fullResync: (payload: {
    agents: Agent[];
    tasks: Task[];
    activity: ActivityItem[];
    timestamp: number;
  }) => void;
}

/**
 * useAgentState Hook
 *
 * Consumes agent state from Context and provides:
 * - Raw state values
 * - Derived/computed state (memoized)
 * - Action wrapper functions (memoized with useCallback)
 *
 * Usage:
 * ```tsx
 * function MyComponent() {
 *   const { agents, activeAgents, createAgent } = useAgentState();
 *
 *   return (
 *     <div>
 *       <p>Active agents: {activeAgents.length}</p>
 *       {agents.map(agent => <AgentCard key={agent.id} agent={agent} />)}
 *     </div>
 *   );
 * }
 * ```
 *
 * @throws {Error} If used outside AgentStateProvider
 */
export function useAgentState(): UseAgentStateReturn {
  // ============================================================================
  // Get Context
  // ============================================================================

  const context = useContext(AgentStateContext);

  if (!context) {
    throw new Error(
      'useAgentState must be used within an AgentStateProvider. ' +
        'Wrap your component tree with <AgentStateProvider>.'
    );
  }

  const { state, dispatch } = context;

  // ============================================================================
  // Derived State (T046 - useMemo for performance)
  // ============================================================================

  /**
   * Active agents (working or blocked)
   * Recomputed only when agents array changes
   */
  const activeAgents = useMemo(
    () =>
      state.agents.filter(
        (agent) => agent.status === 'working' || agent.status === 'blocked'
      ),
    [state.agents]
  );

  /**
   * Idle agents
   * Recomputed only when agents array changes
   */
  const idleAgents = useMemo(
    () => state.agents.filter((agent) => agent.status === 'idle'),
    [state.agents]
  );

  /**
   * Active tasks (in progress)
   * Recomputed only when tasks array changes
   */
  const activeTasks = useMemo(
    () => state.tasks.filter((task) => task.status === 'in_progress'),
    [state.tasks]
  );

  /**
   * Blocked tasks
   * Recomputed only when tasks array changes
   */
  const blockedTasks = useMemo(
    () => state.tasks.filter((task) => task.status === 'blocked'),
    [state.tasks]
  );

  /**
   * Pending tasks
   * Recomputed only when tasks array changes
   */
  const pendingTasks = useMemo(
    () => state.tasks.filter((task) => task.status === 'pending'),
    [state.tasks]
  );

  /**
   * Completed tasks
   * Recomputed only when tasks array changes
   */
  const completedTasks = useMemo(
    () => state.tasks.filter((task) => task.status === 'completed'),
    [state.tasks]
  );

  // ============================================================================
  // Action Wrapper Functions (T047, T048 - useCallback for performance)
  // ============================================================================

  /**
   * Load initial agents
   */
  const loadAgents = useCallback(
    (agents: Agent[]) => {
      dispatch({
        type: 'AGENTS_LOADED',
        payload: agents,
      });
    },
    [dispatch]
  );

  /**
   * Create new agent
   */
  const createAgent = useCallback(
    (agent: Agent) => {
      dispatch({
        type: 'AGENT_CREATED',
        payload: agent,
      });
    },
    [dispatch]
  );

  /**
   * Update agent (partial update with timestamp)
   */
  const updateAgent = useCallback(
    (agentId: string, updates: Partial<Agent>, timestamp: number) => {
      dispatch({
        type: 'AGENT_UPDATED',
        payload: {
          agentId,
          updates,
          timestamp,
        },
      });
    },
    [dispatch]
  );

  /**
   * Retire/remove agent
   */
  const retireAgent = useCallback(
    (agentId: string, timestamp: number) => {
      dispatch({
        type: 'AGENT_RETIRED',
        payload: {
          agentId,
          timestamp,
        },
      });
    },
    [dispatch]
  );

  /**
   * Assign task to agent (atomic operation)
   */
  const assignTask = useCallback(
    (
      taskId: number,
      agentId: string,
      taskTitle: string | undefined,
      timestamp: number
    ) => {
      dispatch({
        type: 'TASK_ASSIGNED',
        payload: {
          taskId,
          agentId,
          taskTitle,
          timestamp,
        },
      });
    },
    [dispatch]
  );

  /**
   * Update task status
   */
  const updateTaskStatus = useCallback(
    (
      taskId: number,
      status: TaskStatus,
      progress: number | undefined,
      timestamp: number
    ) => {
      dispatch({
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId,
          status,
          progress,
          timestamp,
        },
      });
    },
    [dispatch]
  );

  /**
   * Block task with dependencies
   */
  const blockTask = useCallback(
    (taskId: number, blockedBy: number[], timestamp: number) => {
      dispatch({
        type: 'TASK_BLOCKED',
        payload: {
          taskId,
          blockedBy,
          timestamp,
        },
      });
    },
    [dispatch]
  );

  /**
   * Unblock task
   */
  const unblockTask = useCallback(
    (taskId: number, timestamp: number) => {
      dispatch({
        type: 'TASK_UNBLOCKED',
        payload: {
          taskId,
          timestamp,
        },
      });
    },
    [dispatch]
  );

  /**
   * Add activity item to feed
   */
  const addActivity = useCallback(
    (item: ActivityItem) => {
      dispatch({
        type: 'ACTIVITY_ADDED',
        payload: item,
      });
    },
    [dispatch]
  );

  /**
   * Update project progress
   */
  const updateProgress = useCallback(
    (progress: ProjectProgress) => {
      dispatch({
        type: 'PROGRESS_UPDATED',
        payload: progress,
      });
    },
    [dispatch]
  );

  /**
   * Set WebSocket connection status
   */
  const setWSConnected = useCallback(
    (connected: boolean) => {
      dispatch({
        type: 'WS_CONNECTED',
        payload: connected,
      });
    },
    [dispatch]
  );

  /**
   * Full state resync (after WebSocket reconnection)
   */
  const fullResync = useCallback(
    (payload: {
      agents: Agent[];
      tasks: Task[];
      activity: ActivityItem[];
      timestamp: number;
    }) => {
      dispatch({
        type: 'FULL_RESYNC',
        payload,
      });
    },
    [dispatch]
  );

  // ============================================================================
  // Return Complete Interface
  // ============================================================================

  return {
    // Raw state
    agents: state.agents,
    tasks: state.tasks,
    activity: state.activity,
    projectProgress: state.projectProgress,
    wsConnected: state.wsConnected,
    lastSyncTimestamp: state.lastSyncTimestamp,

    // Derived state (memoized)
    activeAgents,
    idleAgents,
    activeTasks,
    blockedTasks,
    pendingTasks,
    completedTasks,

    // Action wrappers (memoized with useCallback)
    loadAgents,
    createAgent,
    updateAgent,
    retireAgent,
    assignTask,
    updateTaskStatus,
    blockTask,
    unblockTask,
    addActivity,
    updateProgress,
    setWSConnected,
    fullResync,
  };
}
