/**
 * Phase-Aware Data Utilities
 *
 * Utility functions for selecting the appropriate data source based on project phase.
 * This is part of the "late-joining user" bug fix where components need to display
 * REST API data (issuesData) during planning phase instead of WebSocket data
 * (useAgentState) which is empty until development begins.
 *
 * Pattern Reference: TaskStats component (web-ui/src/components/tasks/TaskStats.tsx)
 * Architecture Docs: docs/architecture/phase-awareness-pattern.md
 *
 * @module phaseAwareData
 */

import type { IssuesResponse, Task as ApiTask } from '@/types/api';

/**
 * Project phases that indicate planning (before agents start working)
 */
const PLANNING_PHASES = ['planning'] as const;

/**
 * Check if the current phase is a planning phase.
 *
 * During planning phase:
 * - Agents haven't been created yet
 * - Task execution hasn't started
 * - WebSocket/useAgentState data is empty
 * - Components should use REST API data (issuesData) instead
 *
 * @param phase - Current project phase (normalized or raw)
 * @returns true if in planning phase, false otherwise
 *
 * @example
 * if (isPlanningPhase(phase)) {
 *   return calculateStatsFromIssuesData(issuesData);
 * }
 */
export function isPlanningPhase(phase: string | undefined): boolean {
  if (!phase || phase === '') {
    return false;
  }
  return PLANNING_PHASES.includes(phase as typeof PLANNING_PHASES[number]);
}

/**
 * Extract tasks from IssuesResponse by flattening nested task arrays.
 *
 * IMPORTANT: The API may return empty task arrays even when total_tasks > 0.
 * This function returns only the tasks that are actually present in the response.
 * For accurate task counts, use issuesData.total_tasks directly.
 *
 * NOTE: Performance consideration - uses flatMap which creates a new array on each call.
 * Intended for planning phase only where data volume is typically small (<100 tasks).
 * Not recommended for heavy production use with large datasets.
 *
 * @param issuesData - Issues response from REST API
 * @returns Flattened array of tasks from all issues
 *
 * @example
 * const tasks = extractTasksFromIssuesData(issuesData);
 * const completedCount = tasks.filter(t => t.status === 'completed').length;
 */
export function extractTasksFromIssuesData(
  issuesData: IssuesResponse | undefined
): ApiTask[] {
  if (!issuesData || !issuesData.issues) {
    return [];
  }

  return issuesData.issues.flatMap((issue) => issue.tasks || []);
}

/**
 * Calculate progress statistics from IssuesResponse.
 *
 * Uses total_tasks field as the authoritative total count (since the API
 * may not populate nested task arrays). Calculates completed count from
 * nested tasks when available.
 *
 * @param issuesData - Issues response from REST API
 * @returns Progress object with totalTasks, completedTasks, and percentage
 *
 * @example
 * const { totalTasks, completedTasks, percentage } = calculateProgressFromIssuesData(issuesData);
 * // Use in progress bar: <ProgressBar value={percentage} />
 */
export function calculateProgressFromIssuesData(
  issuesData: IssuesResponse | undefined
): {
  totalTasks: number;
  completedTasks: number;
  percentage: number;
} {
  if (!issuesData) {
    return { totalTasks: 0, completedTasks: 0, percentage: 0 };
  }

  // Use total_tasks from API as authoritative count
  const totalTasks = issuesData.total_tasks ?? 0;

  // Calculate completed from nested tasks (may be 0 if arrays empty)
  const allTasks = extractTasksFromIssuesData(issuesData);
  const completedTasks = allTasks.filter((t) => t.status === 'completed').length;

  // Calculate percentage, clamping to 0-100 range
  const percentage =
    totalTasks > 0 ? Math.min(100, Math.round((completedTasks / totalTasks) * 100)) : 0;

  return { totalTasks, completedTasks, percentage };
}

/**
 * Planning phase message templates for different component types.
 */
const PLANNING_MESSAGES: Record<string, string> = {
  'agent-list': 'Agents will be created automatically when development begins',
  'quality-gates': 'Quality gates will be evaluated during development phase',
  'cost-dashboard': 'Cost metrics will be available during development phase',
  default: 'This feature is available during development phase',
};

/**
 * Get appropriate planning phase message for a component.
 *
 * Returns user-friendly messaging that explains why data is unavailable
 * during planning phase and what to expect when development begins.
 *
 * @param componentType - Component identifier (e.g., 'agent-list', 'quality-gates')
 * @param issuesData - Optional issues data for task count messaging
 * @returns Human-readable message for planning phase
 *
 * @example
 * <p>{getPlanningPhaseMessage('agent-list', issuesData)}</p>
 * // "Agents will be created automatically when development begins"
 */
export function getPlanningPhaseMessage(
  componentType: string,
  issuesData?: IssuesResponse
): string {
  const baseMessage = PLANNING_MESSAGES[componentType] || PLANNING_MESSAGES.default;

  // For agent-list, optionally include task count
  if (componentType === 'agent-list' && issuesData?.total_tasks) {
    return `${baseMessage}. ${issuesData.total_tasks} tasks ready for agent assignment.`;
  }

  return baseMessage;
}
