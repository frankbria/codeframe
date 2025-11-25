/**
 * Agent State Provider Component
 *
 * Provides centralized agent state management via React Context.
 * Wraps children with Context Provider and manages state with useReducer.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Tasks: T043, T044
 */

'use client';

import { useReducer, useEffect, type ReactNode } from 'react';
import useSWR from 'swr';
import { AgentStateContext } from '@/contexts/AgentStateContext';
import { agentReducer, getInitialState } from '@/reducers/agentReducer';
import { agentsApi, tasksApi, activityApi } from '@/lib/api';
import { getWebSocketClient } from '@/lib/websocket';
import { processWebSocketMessage } from '@/lib/websocketMessageMapper';
import { fullStateResyncWithRetry } from '@/lib/agentStateSync';
import type { Agent, ActivityItem } from '@/types/agentState';

/**
 * Props for AgentStateProvider
 */
export interface AgentStateProviderProps {
  /** Project ID to fetch data for */
  projectId: number;

  /** Child components that will have access to agent state */
  children: ReactNode;
}

/**
 * Provides centralized agent state management and real-time synchronization to descendant components.
 *
 * Initializes state via SWR, keeps it current via WebSocket messages and reconnect resyncs, and exposes
 * the reducer state and dispatch through AgentStateContext.
 *
 * @param projectId - Numeric project identifier used to scope SWR fetches and WebSocket subscriptions.
 * @param children - React children that will receive the agent state context.
 */
export function AgentStateProvider({
  projectId,
  children,
}: AgentStateProviderProps) {
  // Initialize reducer with initial state
  const [state, dispatch] = useReducer(agentReducer, getInitialState());

  // ============================================================================
  // Initial Data Fetching with SWR
  // ============================================================================

  /**
   * Fetch initial agents data
   */
  const { data: agentsData } = useSWR(
    projectId ? `/api/projects/${projectId}/agents` : null,
    () => agentsApi.list(projectId),
    {
      refreshInterval: 0, // Don't auto-refresh - rely on WebSocket
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  /**
   * Fetch initial tasks data
   */
  const { data: tasksData } = useSWR(
    projectId ? `/api/projects/${projectId}/tasks` : null,
    () => tasksApi.list(projectId, { limit: 100 }),
    {
      refreshInterval: 0,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  /**
   * Fetch initial activity data
   */
  const { data: activityData } = useSWR(
    projectId ? `/api/projects/${projectId}/activity` : null,
    () => activityApi.list(projectId, 50),
    {
      refreshInterval: 0,
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  // ============================================================================
  // Load Initial Data into State
  // ============================================================================

  /**
   * Load agents when data is fetched
   */
  useEffect(() => {
    if (agentsData?.data?.agents) {
      // Transform API agents to include timestamp if missing
      const agentsWithTimestamp: Agent[] = agentsData.data.agents.map(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (agent: any) => ({
          ...agent,
          timestamp: agent.timestamp || Date.now(),
        })
      );

      dispatch({
        type: 'AGENTS_LOADED',
        payload: agentsWithTimestamp,
      });
    }
  }, [agentsData]);

  /**
   * Load tasks when data is fetched
   * 
   * Note: Tasks don't have a dedicated TASKS_LOADED action.
   * We skip loading tasks separately to avoid complexity.
   * Tasks will be loaded via WebSocket updates or can be accessed via SWR directly.
   */
  useEffect(() => {
    // Intentionally empty - tasks are managed via WebSocket or fetched on-demand
    // This prevents infinite loops and simplifies the data flow
  }, [tasksData]);

  /**
   * Load activity when data is fetched
   */
  useEffect(() => {
    if (activityData?.data?.activity) {
      // Add each activity item
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (activityData.data.activity as any[]).forEach((item: ActivityItem) => {
        dispatch({
          type: 'ACTIVITY_ADDED',
          payload: item,
        });
      });
    }
  }, [activityData]);

  // ============================================================================
  // WebSocket Integration (Phase 4: T073-T076, Phase 5: T088-T092)
  // ============================================================================

  useEffect(() => {
    // Only connect if we have a valid project ID
    if (!projectId) return;

    // Get WebSocket client instance
    const ws = getWebSocketClient();

    // Track if this is the first connection or a reconnection
    let isFirstConnection = true;

    // Connect to WebSocket
    ws.connect();

    // Subscribe to project-specific messages
    ws.subscribe(projectId);

    // Handle incoming messages (T073-T074)
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const unsubscribeMessages = ws.onMessage((message: any) => {
      // Filter by project ID (T074)
      if (message.project_id && message.project_id !== projectId) {
        return;
      }

      // Map message to action and dispatch (T075)
      const action = processWebSocketMessage(message, projectId);
      if (action) {
        dispatch(action);
      }
    });

    // Handle connection status changes (T089)
    const unsubscribeConnection = ws.onConnectionChange((connected: boolean) => {
      // Dispatch connection status (T089)
      dispatch({
        type: 'WS_CONNECTED',
        payload: connected,
      });

      if (!connected) {
        if (process.env.NODE_ENV === 'development') {
          console.log('WebSocket disconnected, will resync on reconnect');
        }
      }
    });

    // Handle reconnection with full state resync (T088, T090-T092)
    const unsubscribeReconnect = ws.onReconnect(async () => {
      // Skip resync on first connection (initial data is loaded via SWR)
      if (isFirstConnection) {
        isFirstConnection = false;
        return;
      }

      if (process.env.NODE_ENV === 'development') {
        console.log('WebSocket reconnected, performing full state resync...');
      }

      try {
        // Trigger full state resync (T090)
        const freshState = await fullStateResyncWithRetry(projectId, 3);

        // Dispatch FULL_RESYNC action with fresh data (T091)
        dispatch({
          type: 'FULL_RESYNC',
          payload: freshState,
        });

        // Dispatch WS_CONNECTED(true) after successful resync (T092)
        dispatch({
          type: 'WS_CONNECTED',
          payload: true,
        });

        if (process.env.NODE_ENV === 'development') {
          console.log('Full state resync completed successfully');
        }
      } catch (error) {
        console.error('Failed to resync state after reconnection:', error);
        // Connection status remains true from onConnectionChange,
        // but we log the error for debugging
      }
    });

    // Cleanup on unmount (T076)
    return () => {
      unsubscribeMessages();
      unsubscribeConnection();
      unsubscribeReconnect();
      // Note: We don't disconnect the WebSocket because it's a singleton
      // and may be used by other components
    };
  }, [projectId, dispatch]);

  // ============================================================================
  // Render Provider
  // ============================================================================

  return (
    <AgentStateContext.Provider value={{ state, dispatch }}>
      {children}
    </AgentStateContext.Provider>
  );
}