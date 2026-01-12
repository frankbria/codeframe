/**
 * TaskList Component
 * Displays tasks during development phase with real-time updates
 *
 * Used in the Tasks tab when project is in 'active' or 'review' phase.
 * Provides a simpler flat list view compared to TaskTreeView, with
 * status filtering and agent assignment display.
 */

'use client';

import { useState, useMemo, useCallback, memo } from 'react';
import { useAgentState } from '@/hooks/useAgentState';
import { tasksApi } from '@/lib/api';
import QualityGateStatus from '@/components/quality-gates/QualityGateStatus';
import ErrorBoundary from '@/components/ErrorBoundary';
import type { Task, TaskStatus } from '@/types/agentState';

export interface TaskListProps {
  projectId: number;
}

type FilterOption = 'all' | TaskStatus;

interface FilterConfig {
  label: string;
  status: FilterOption;
}

const FILTER_OPTIONS: FilterConfig[] = [
  { label: 'All', status: 'all' },
  { label: 'Pending', status: 'pending' },
  { label: 'Assigned', status: 'assigned' },
  { label: 'In Progress', status: 'in_progress' },
  { label: 'Blocked', status: 'blocked' },
  { label: 'Completed', status: 'completed' },
  { label: 'Failed', status: 'failed' },
];

/**
 * Get status badge styling based on task status
 */
function getStatusStyles(status: TaskStatus): { bgClass: string; textClass: string } {
  switch (status) {
    case 'completed':
      return { bgClass: 'bg-secondary/10', textClass: 'text-secondary-foreground' };
    case 'in_progress':
      return { bgClass: 'bg-primary/10', textClass: 'text-primary' };
    case 'blocked':
      return { bgClass: 'bg-destructive/10', textClass: 'text-destructive' };
    case 'failed':
      return { bgClass: 'bg-destructive/20', textClass: 'text-destructive' };
    case 'assigned':
      return { bgClass: 'bg-accent', textClass: 'text-accent-foreground' };
    case 'pending':
    default:
      return { bgClass: 'bg-muted', textClass: 'text-muted-foreground' };
  }
}

/**
 * Format status label for display
 */
function formatStatus(status: TaskStatus): string {
  return status.replace('_', ' ');
}

/**
 * Individual task card component
 */
interface TaskCardProps {
  task: Task;
  onViewQualityGates: (taskId: number) => void;
  showQualityGates: boolean;
}

const TaskCard = memo(function TaskCard({
  task,
  onViewQualityGates,
  showQualityGates,
}: TaskCardProps) {
  const statusStyles = getStatusStyles(task.status);
  const hasProgress = task.status === 'in_progress' && typeof task.progress === 'number';
  const isCompleted = task.status === 'completed';
  const isBlocked = task.status === 'blocked';

  return (
    <li
      role="listitem"
      data-testid="task-card"
      data-status={task.status}
      className="bg-card border border-border rounded-lg p-4 hover:border-primary/50 transition-colors"
    >
      {/* Task Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="font-medium text-foreground truncate flex-1" title={task.title}>
          {task.title}
        </h3>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusStyles.bgClass} ${statusStyles.textClass}`}
        >
          {formatStatus(task.status)}
        </span>
      </div>

      {/* Agent Assignment */}
      <div className="text-sm text-muted-foreground mb-2">
        <span className="text-xs">Assigned to: </span>
        <span className="font-mono text-xs">
          {task.agent_id || 'Unassigned'}
        </span>
      </div>

      {/* Progress Bar (for in-progress tasks) */}
      {hasProgress && (
        <div className="mb-2">
          <div className="flex justify-between text-xs text-muted-foreground mb-1">
            <span>Progress</span>
            <span>{task.progress}%</span>
          </div>
          <div
            role="progressbar"
            aria-valuenow={task.progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Task progress: ${task.progress}%`}
            className="w-full bg-muted rounded-full h-2 overflow-hidden"
          >
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${task.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Blocked By Info (for blocked tasks) */}
      {isBlocked && task.blocked_by && task.blocked_by.length > 0 && (
        <div className="text-sm text-destructive mb-2">
          <span>🚫 Blocked by {task.blocked_by.length} task{task.blocked_by.length !== 1 ? 's' : ''}</span>
        </div>
      )}

      {/* Quality Gates Button (for completed tasks) */}
      {isCompleted && (
        <div className="mt-3 pt-3 border-t border-border">
          <button
            data-testid="quality-gates-button"
            onClick={() => onViewQualityGates(task.id)}
            className="text-xs text-primary hover:text-primary/80 transition-colors"
          >
            {showQualityGates ? '▼ Hide Quality Gates' : '▶ View Quality Gates'}
          </button>

          {showQualityGates && (
            <div className="mt-2">
              <ErrorBoundary fallback={<div className="text-destructive text-xs">Failed to load quality gates</div>}>
                <QualityGateStatus taskId={task.id} />
              </ErrorBoundary>
            </div>
          )}
        </div>
      )}
    </li>
  );
});

TaskCard.displayName = 'TaskCard';

/**
 * TaskList component
 */
const TaskList = memo(function TaskList({ projectId }: TaskListProps) {
  const { tasks, wsConnected } = useAgentState();

  // Filter state
  const [activeFilter, setActiveFilter] = useState<FilterOption>('all');

  // Quality gates visibility state (keyed by task ID)
  const [qualityGatesVisible, setQualityGatesVisible] = useState<Set<number>>(new Set());

  // Assignment state (Issue #248 fix)
  const [isAssigning, setIsAssigning] = useState(false);
  const [assignmentError, setAssignmentError] = useState<string | null>(null);

  // Filter tasks by project ID
  const projectTasks = useMemo(
    () => tasks.filter((task) => task.project_id === projectId),
    [tasks, projectId]
  );

  // Calculate counts for each filter
  const filterCounts = useMemo(() => {
    const counts: Record<FilterOption, number> = {
      all: projectTasks.length,
      pending: 0,
      assigned: 0,
      in_progress: 0,
      blocked: 0,
      completed: 0,
      failed: 0,
    };

    projectTasks.forEach((task) => {
      if (task.status in counts) {
        counts[task.status as TaskStatus]++;
      }
    });

    return counts;
  }, [projectTasks]);

  // Apply status filter
  const filteredTasks = useMemo(() => {
    if (activeFilter === 'all') {
      return projectTasks;
    }
    return projectTasks.filter((task) => task.status === activeFilter);
  }, [projectTasks, activeFilter]);

  // Check if there are pending unassigned tasks (Issue #248 fix)
  const hasPendingUnassigned = useMemo(() => {
    return projectTasks.some(
      (task) => task.status === 'pending' && !task.agent_id
    );
  }, [projectTasks]);

  // Count of pending unassigned tasks
  const pendingUnassignedCount = useMemo(() => {
    return projectTasks.filter(
      (task) => task.status === 'pending' && !task.agent_id
    ).length;
  }, [projectTasks]);

  // Handler for Assign Tasks button (Issue #248 fix)
  const handleAssignTasks = useCallback(async () => {
    setIsAssigning(true);
    setAssignmentError(null);
    try {
      const response = await tasksApi.assignPending(projectId);
      if (!response.data.success) {
        setAssignmentError(response.data.message || 'Assignment failed');
      }
      // Success - the WebSocket will update the task list as agents are assigned
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to assign tasks';
      setAssignmentError(errorMessage);
    } finally {
      setIsAssigning(false);
    }
  }, [projectId]);

  // Toggle quality gates visibility for a task
  const handleViewQualityGates = useCallback((taskId: number) => {
    setQualityGatesVisible((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  }, []);

  // Handle filter change
  const handleFilterChange = useCallback((filter: FilterOption) => {
    setActiveFilter(filter);
  }, []);

  // Empty state
  if (projectTasks.length === 0) {
    return (
      <div
        aria-label="Task list"
        className="text-center py-8 text-muted-foreground"
      >
        <p>No tasks available</p>
        <p className="text-sm mt-2">Tasks will appear here during the development phase</p>
      </div>
    );
  }

  return (
    <div aria-label="Task list" data-testid="task-list">
      {/* Connection Status */}
      <div
        data-testid="connection-status"
        className="flex items-center gap-2 mb-4"
      >
        <span
          className={`w-2 h-2 rounded-full ${
            wsConnected ? 'bg-secondary animate-pulse' : 'bg-destructive'
          }`}
        />
        <span className="text-xs text-muted-foreground">
          {wsConnected ? 'Live updates enabled' : 'Reconnecting...'}
        </span>
      </div>

      {/* Pending Unassigned Tasks Banner (Issue #248 fix) */}
      {hasPendingUnassigned && (
        <div
          data-testid="assign-tasks-banner"
          className="mb-4 p-4 bg-muted/50 border border-border rounded-lg"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1">
              <h3 className="font-medium text-foreground">Tasks Pending Assignment</h3>
              <p className="text-sm text-muted-foreground">
                {pendingUnassignedCount} task{pendingUnassignedCount !== 1 ? 's are' : ' is'} waiting to be assigned to agents
              </p>
            </div>
            <button
              data-testid="assign-tasks-button"
              onClick={handleAssignTasks}
              disabled={isAssigning}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isAssigning ? 'Assigning...' : 'Assign Tasks'}
            </button>
          </div>
          {assignmentError && (
            <p className="mt-2 text-sm text-destructive">{assignmentError}</p>
          )}
        </div>
      )}

      {/* Filter Buttons */}
      <div className="flex flex-wrap gap-2 mb-4" role="group" aria-label="Filter tasks by status">
        {FILTER_OPTIONS.map((option) => (
          <button
            key={option.status}
            onClick={() => handleFilterChange(option.status)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeFilter === option.status
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
            aria-pressed={activeFilter === option.status}
          >
            {option.label} ({filterCounts[option.status]})
          </button>
        ))}
      </div>

      {/* Task List */}
      {filteredTasks.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <p>No tasks match the selected filter</p>
        </div>
      ) : (
        <ul
          role="list"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          {filteredTasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onViewQualityGates={handleViewQualityGates}
              showQualityGates={qualityGatesVisible.has(task.id)}
            />
          ))}
        </ul>
      )}

      {/* Task Summary */}
      <div className="mt-4 pt-4 border-t border-border text-sm text-muted-foreground">
        Showing {filteredTasks.length} of {projectTasks.length} tasks
      </div>
    </div>
  );
});

TaskList.displayName = 'TaskList';

export default TaskList;
