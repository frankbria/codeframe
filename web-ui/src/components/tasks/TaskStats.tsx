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
 * The component automatically recalculates statistics when tasks change
 * using useMemo for performance optimization.
 */
function TaskStats(): JSX.Element {
  const { tasks } = useAgentState();

  // Calculate statistics from tasks array
  const stats = useMemo(() => {
    const total = tasks.length;
    const completed = tasks.filter((task) => task.status === 'completed').length;
    const blocked = tasks.filter((task) => task.status === 'blocked').length;
    const inProgress = tasks.filter((task) => task.status === 'in_progress').length;

    return {
      total,
      completed,
      blocked,
      inProgress,
    };
  }, [tasks]);

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
