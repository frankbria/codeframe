/**
 * TaskStats - Phase-aware task statistics display component
 *
 * Displays task statistics from the appropriate data source based on project phase:
 * - Planning phase: Uses issuesData prop (REST API data from issues endpoint)
 * - Development/Review phase: Uses useAgentState hook (WebSocket real-time data)
 *
 * This phase-aware approach fixes the "late-joining user" bug where TaskStats
 * would show 0 tasks during planning phase because agent state is empty until
 * development begins.
 *
 * Statistics shown:
 * - Total tasks
 * - Completed tasks
 * - Blocked tasks
 * - In-progress tasks
 *
 * Part of Dashboard Overview tab
 */

'use client';

import React, { useMemo } from 'react';
import { useAgentState } from '@/hooks/useAgentState';
import type { IssuesResponse, Task as ApiTask } from '@/types/api';
import {
  CheckListIcon,
  CheckmarkCircle01Icon,
  Alert02Icon,
  Loading03Icon,
} from '@hugeicons/react';

/**
 * Props for TaskStats component
 */
interface TaskStatsProps {
  /**
   * Current project phase. Determines which data source to use:
   * - 'planning': Uses issuesData prop
   * - 'development' | 'review': Uses useAgentState hook
   * - undefined: Falls back to useAgentState (backward compatibility)
   */
  phase?: string;

  /**
   * Issues data from REST API, containing tasks nested within issues.
   * Used when phase is 'planning' to display accurate task counts
   * before agents start working.
   */
  issuesData?: IssuesResponse;
}

/**
 * Extract task statistics from issues data (planning phase).
 *
 * IMPORTANT: Uses `issuesData.total_tasks` directly for the total count because
 * the API does not populate the nested `issues[].tasks` arrays in the response.
 * The `total_tasks` field is the authoritative count from the database.
 *
 * For status-specific counts (completed, blocked, in-progress), we still try to
 * calculate from nested tasks when available. However, during planning phase,
 * these will typically be 0 since tasks haven't started execution yet.
 *
 * This fixes the "late-joining user" bug where TaskStats showed 0 tasks during
 * planning phase while the tab badge showed the correct count (e.g., "Review (24)").
 */
function calculateStatsFromIssues(issuesData: IssuesResponse | undefined): {
  total: number;
  completed: number;
  blocked: number;
  inProgress: number;
} {
  if (!issuesData) {
    return { total: 0, completed: 0, blocked: 0, inProgress: 0 };
  }

  // Use total_tasks directly - this is the authoritative count from the API.
  // The nested issues[].tasks arrays may be empty even when total_tasks > 0.
  const total = issuesData.total_tasks ?? 0;

  // Try to calculate status-specific counts from nested tasks when available.
  // During planning phase, tasks arrays are typically empty, so these will be 0.
  const allTasks: ApiTask[] = issuesData.issues?.flatMap(
    (issue) => issue.tasks || []
  ) ?? [];

  return {
    total,
    completed: allTasks.filter((t) => t.status === 'completed').length,
    blocked: allTasks.filter((t) => t.status === 'blocked').length,
    inProgress: allTasks.filter((t) => t.status === 'in_progress').length,
  };
}

/**
 * TaskStats Component
 *
 * Displays task statistics in a grid layout with colored stat cards.
 * Data source is selected based on project phase:
 * - Planning phase: Uses issuesData prop (REST API)
 * - Development/Review: Uses useAgentState hook (WebSocket)
 *
 * Performance: Uses memoization for both data source selection and
 * statistics calculation to prevent unnecessary re-renders.
 */
function TaskStats({ phase, issuesData }: TaskStatsProps): JSX.Element {
  // Always call the hook (React hooks rules) but conditionally use its data
  const { tasks, completedTasks, blockedTasks, activeTasks } = useAgentState();

  /**
   * Determine if we should use issues data based on phase.
   * Planning phase = use issuesData; otherwise = use agent state.
   */
  const usePlanningData = phase === 'planning';

  /**
   * Calculate statistics from the appropriate data source.
   * Memoized to prevent recalculation on every render.
   */
  const stats = useMemo(() => {
    if (usePlanningData) {
      // Planning phase: Calculate from issues data
      return calculateStatsFromIssues(issuesData);
    }

    // Development/Review phase: Use agent state (existing behavior)
    return {
      total: tasks.length,
      completed: completedTasks.length,
      blocked: blockedTasks.length,
      inProgress: activeTasks.length,
    };
  }, [usePlanningData, issuesData, tasks, completedTasks, blockedTasks, activeTasks]);

  return (
    <div className="task-stats">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Tasks */}
        <div className="p-4 rounded-lg bg-primary/10 border border-border">
          <div className="flex items-center justify-between mb-2">
            <CheckListIcon className="h-6 w-6 text-primary" />
          </div>
          <div className="text-sm text-muted-foreground mb-1">Total Tasks</div>
          <div
            className="text-3xl font-bold text-primary"
            data-testid="total-tasks"
          >
            {stats.total}
          </div>
        </div>

        {/* Completed Tasks */}
        <div className="p-4 rounded-lg bg-secondary/10 border border-border">
          <div className="flex items-center justify-between mb-2">
            <CheckmarkCircle01Icon className="h-6 w-6 text-secondary" />
          </div>
          <div className="text-sm text-muted-foreground mb-1">Completed</div>
          <div
            className="text-3xl font-bold text-secondary"
            data-testid="completed-tasks"
          >
            {stats.completed}
          </div>
        </div>

        {/* Blocked Tasks */}
        <div className="p-4 rounded-lg bg-destructive/10 border border-border">
          <div className="flex items-center justify-between mb-2">
            <Alert02Icon className="h-6 w-6 text-destructive" />
          </div>
          <div className="text-sm text-muted-foreground mb-1">Blocked</div>
          <div
            className="text-3xl font-bold text-destructive"
            data-testid="blocked-tasks"
          >
            {stats.blocked}
          </div>
        </div>

        {/* In-Progress Tasks */}
        <div className="p-4 rounded-lg bg-accent/10 border border-border">
          <div className="flex items-center justify-between mb-2">
            <Loading03Icon className="h-6 w-6 text-accent-foreground" />
          </div>
          <div className="text-sm text-muted-foreground mb-1">In Progress</div>
          <div
            className="text-3xl font-bold text-accent-foreground"
            data-testid="in-progress-tasks"
          >
            {stats.inProgress}
          </div>
        </div>
      </div>
    </div>
  );
}

// Export with React.memo for performance optimization
export default React.memo(TaskStats);
