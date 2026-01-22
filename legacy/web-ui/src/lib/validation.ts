/**
 * Validation utilities for agent state management
 * Provides validation functions to warn about constraint violations
 */

/**
 * Validates agent count and warns if it exceeds the recommended limit
 * @param agentCount - Current number of agents
 * @returns true if validation passes, false if warning issued
 */
export function validateAgentCount(agentCount: number): boolean {
  const MAX_AGENTS = 10;

  if (agentCount > MAX_AGENTS) {
    if (process.env.NODE_ENV === 'development') {
      console.warn(
        `[AgentState] Agent count (${agentCount}) exceeds recommended limit of ${MAX_AGENTS}. ` +
        `Performance may degrade with too many concurrent agents.`
      );
    }
    return false;
  }

  return true;
}

/**
 * Validates activity feed size and warns if it exceeds the limit
 * @param activitySize - Current number of activity items
 * @returns true if validation passes, false if warning issued
 */
export function validateActivitySize(activitySize: number): boolean {
  const MAX_ACTIVITY_ITEMS = 50;

  if (activitySize > MAX_ACTIVITY_ITEMS) {
    if (process.env.NODE_ENV === 'development') {
      console.warn(
        `[AgentState] Activity feed size (${activitySize}) exceeds maximum of ${MAX_ACTIVITY_ITEMS}. ` +
        `Older items should have been pruned by the reducer.`
      );
    }
    return false;
  }

  return true;
}
