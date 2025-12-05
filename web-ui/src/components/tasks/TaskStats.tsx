/**
 * TaskStats - Task statistics display component
 *
 * Displays real-time task statistics from the agent state:
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

/**
 * TaskStats Component
 *
 * Displays task statistics in a grid layout with colored stat cards.
 * Data is sourced from the useAgentState hook, which provides real-time
 * task data updated via WebSocket.
 *
 * Performance: Uses pre-filtered derived state from useAgentState hook
 * to avoid redundant filtering operations. The hook already memoizes
 * these filtered arrays.
 *
 * UI Note: Emojis are used for visual appeal and quick recognition,
 * following the pattern established in CostDashboard and ReviewSummary.
 */
function TaskStats(): JSX.Element {
  // Use pre-filtered derived state from useAgentState for better performance
  // These are already memoized in the hook (see useAgentState.ts:201-231)
  const { tasks, completedTasks, blockedTasks, activeTasks } = useAgentState();

  /**
   * Calculate statistics from pre-filtered task arrays.
   * Memoized to prevent recalculation on every render.
   * Only recalculates when any of the task arrays change.
   *
   * Benefits of using derived state:
   * - Type-safe (uses hook's TaskStatus type)
   * - More efficient (no redundant filtering)
   * - Leverages existing memoization from useAgentState
   */
  const stats = useMemo(() => ({
    total: tasks.length,
    completed: completedTasks.length,  // Already filtered for status === 'completed'
    blocked: blockedTasks.length,      // Already filtered for status === 'blocked'
    inProgress: activeTasks.length,    // Already filtered for status === 'in_progress'
  }), [tasks, completedTasks, blockedTasks, activeTasks]);

  return (
    <div className="task-stats">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Total Tasks */}
        <div className="p-4 rounded-lg bg-blue-50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-2xl">📋</span>
          </div>
          <div className="text-sm text-gray-600 mb-1">Total Tasks</div>
          <div
            className="text-3xl font-bold text-blue-600"
            data-testid="total-tasks"
          >
            {stats.total}
          </div>
        </div>

        {/* Completed Tasks */}
        <div className="p-4 rounded-lg bg-green-50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-2xl">✅</span>
          </div>
          <div className="text-sm text-gray-600 mb-1">Completed</div>
          <div
            className="text-3xl font-bold text-green-600"
            data-testid="completed-tasks"
          >
            {stats.completed}
          </div>
        </div>

        {/* Blocked Tasks */}
        <div className="p-4 rounded-lg bg-red-50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-2xl">🚫</span>
          </div>
          <div className="text-sm text-gray-600 mb-1">Blocked</div>
          <div
            className="text-3xl font-bold text-red-600"
            data-testid="blocked-tasks"
          >
            {stats.blocked}
          </div>
        </div>

        {/* In-Progress Tasks */}
        <div className="p-4 rounded-lg bg-yellow-50">
          <div className="flex items-center justify-between mb-2">
            <span className="text-2xl">⚙️</span>
          </div>
          <div className="text-sm text-gray-600 mb-1">In Progress</div>
          <div
            className="text-3xl font-bold text-yellow-600"
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
