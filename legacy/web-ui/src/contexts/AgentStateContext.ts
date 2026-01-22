/**
 * Agent State Context
 *
 * React Context for centralized agent state management.
 * Provides state and dispatch function to all child components.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Task: T042
 */

import { createContext } from 'react';
import type { AgentState, AgentAction } from '@/types/agentState';
import type { Dispatch } from 'react';

/**
 * Context value shape
 *
 * Provides both state and dispatch to consumers
 */
export interface AgentStateContextValue {
  /** Current agent state */
  state: AgentState;

  /** Dispatch function for state updates */
  dispatch: Dispatch<AgentAction>;
}

/**
 * Agent State Context
 *
 * Usage:
 * ```tsx
 * const { state, dispatch } = useContext(AgentStateContext);
 * ```
 *
 * Note: Prefer using the useAgentState hook instead of useContext directly
 */
export const AgentStateContext = createContext<AgentStateContextValue | undefined>(
  undefined
);

// Set display name for React DevTools
AgentStateContext.displayName = 'AgentStateContext';
