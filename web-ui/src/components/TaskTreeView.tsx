/**
 * TaskTreeView Component
 * Hierarchical tree view of issues and their tasks
 */

'use client';

import { useState, memo } from 'react';
import type { Issue, Task, WorkStatus } from '@/types/api';
import QualityGateStatus from './quality-gates/QualityGateStatus';
import { BotIcon, UserIcon, Link01Icon, Cancel01Icon } from '@hugeicons/react';

interface TaskTreeViewProps {
  issues: Issue[];
}

const TaskTreeView = memo(function TaskTreeView({ issues }: TaskTreeViewProps) {
  const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set());
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());

  // Toggle issue expansion
  const toggleIssue = (issueId: string) => {
    setExpandedIssues((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(issueId)) {
        newSet.delete(issueId);
      } else {
        newSet.add(issueId);
      }
      return newSet;
    });
  };

  // Toggle task expansion (for quality gates section)
  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  // Get status badge classes
  const getStatusClasses = (status: WorkStatus) => {
    switch (status) {
      case 'completed':
        return 'bg-secondary/10 text-secondary-foreground';
      case 'in_progress':
        return 'bg-primary/10 text-primary';
      case 'blocked':
        return 'bg-destructive/10 text-destructive';
      case 'failed':
        return 'bg-destructive/10 text-destructive';
      case 'assigned':
        return 'bg-accent/10 text-accent-foreground';
      case 'pending':
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

  // Get priority badge classes
  const getPriorityClasses = (priority: number) => {
    if (priority === 1) return 'bg-destructive/10 text-destructive';
    if (priority === 2) return 'bg-destructive/20 text-destructive';
    if (priority === 3) return 'bg-accent/10 text-accent-foreground';
    return 'bg-muted text-muted-foreground';
  };

  // Get provenance icon
  const getProvenanceIcon = (proposedBy: 'agent' | 'human') => {
    return proposedBy === 'agent' ? (
      <BotIcon className="h-4 w-4" aria-hidden="true" />
    ) : (
      <UserIcon className="h-4 w-4" aria-hidden="true" />
    );
  };

  /**
   * Check if task is blocked by incomplete dependencies.
   *
   * Uses dual-lookup pattern to find dependencies: matches by either `id` (stable,
   * unique identifier) or `task_number` (human-readable, hierarchical). This supports
   * backward compatibility with legacy data that may use task_number references.
   *
   * Prefer using `id` for new dependencies as it's permanent and won't break
   * if tasks are renumbered.
   *
   * @see docs/architecture/task-identifiers.md for full documentation
   */
  const isTaskBlocked = (task: Task, allTasks: Task[]): boolean => {
    if (!task.depends_on || task.depends_on.length === 0) return false;
    if (task.status === 'completed' || task.status === 'in_progress') return false;

    // Find dependency tasks and check if any are not completed
    return task.depends_on.some((depId) => {
      // Dual-lookup: match by id (stable) OR task_number (human-readable, may change)
      // This pattern allows depends_on to contain either identifier type
      const depTask = allTasks.find((t) => t.id === depId || t.task_number === depId);
      return depTask && depTask.status !== 'completed';
    });
  };

  // Get all tasks from all issues for dependency checking
  const getAllTasks = (): Task[] => {
    return issues.flatMap((issue) => issue.tasks || []);
  };

  if (!issues || issues.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No issues available
      </div>
    );
  }

  return (
    <div role="tree" className="space-y-2" data-testid="task-tree">
      {issues.map((issue) => {
        const isExpanded = expandedIssues.has(issue.id);
        const hasTasks = issue.tasks && issue.tasks.length > 0;

        return (
          <div key={issue.id} className="border border-border rounded-lg" data-testid={`issue-${issue.id}`}>
            {/* Issue Header */}
            <div className="flex items-start gap-3 p-4 bg-card hover:bg-muted/50">
              {/* Expand/Collapse Button */}
              <button
                onClick={() => toggleIssue(issue.id)}
                aria-expanded={isExpanded}
                aria-label={isExpanded ? 'Collapse' : 'Expand'}
                className="flex-shrink-0 mt-1 text-muted-foreground hover:text-foreground"
              >
                {isExpanded ? '▼' : '▶'}
              </button>

              {/* Issue Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 mb-2">
                  <span className="flex-shrink-0 text-sm font-mono text-muted-foreground">
                    {issue.issue_number}
                  </span>
                  <h3 className="flex-1 font-medium text-foreground">
                    {issue.title}
                  </h3>
                  <span className="flex-shrink-0 text-lg" title={`Proposed by ${issue.proposed_by}`}>
                    {getProvenanceIcon(issue.proposed_by)}
                  </span>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getStatusClasses(
                      issue.status
                    )}`}
                  >
                    {issue.status}
                  </span>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getPriorityClasses(
                      issue.priority
                    )}`}
                  >
                    Priority: {issue.priority}
                  </span>
                  {issue.depends_on && issue.depends_on.length > 0 && (
                    <span className="text-xs text-muted-foreground">
                      Depends on: {issue.depends_on.join(', ')}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Tasks (when expanded) */}
            {isExpanded && (
              <div className="border-t border-border bg-muted px-4 py-2">
                {!hasTasks ? (
                  <div className="text-sm text-muted-foreground py-2 pl-8">
                    No tasks available for this issue
                  </div>
                ) : (
                  <div className="space-y-2">
                    {issue.tasks!.map((task) => {
                      const allTasks = getAllTasks();
                      const blocked = isTaskBlocked(task, allTasks);
                      const hasDependencies = task.depends_on && task.depends_on.length > 0;

                      return (
                        <div
                          key={task.id}
                          data-testid={`task-item-${task.id}`}
                          data-status={task.status}
                          className={`ml-8 p-3 bg-card border rounded transition-colors ${
                            blocked
                              ? 'border-destructive/20 bg-destructive/5'
                              : task.status === 'completed'
                              ? 'border-secondary/20'
                              : task.status === 'in_progress'
                              ? 'border-primary/20'
                              : 'border-border'
                          }`}
                        >
                          <div className="flex items-start gap-2 mb-1">
                            {/* Dependency indicator */}
                            {hasDependencies && (
                              <span
                                className="flex-shrink-0"
                                title={`Depends on: ${task.depends_on.join(', ')}`}
                              >
                                <Link01Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                              </span>
                            )}
                            <span className="flex-shrink-0 text-xs font-mono text-muted-foreground">
                              {task.task_number}
                            </span>
                            <span className="flex-1 text-sm font-medium text-foreground">
                              {task.title}
                            </span>
                            <span className="flex-shrink-0" title={`Proposed by ${task.proposed_by}`}>
                              {getProvenanceIcon(task.proposed_by)}
                            </span>
                          </div>

                          <div className="ml-14 flex items-center gap-2 flex-wrap">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getStatusClasses(
                                task.status
                              )}`}
                            >
                              {task.status}
                            </span>

                            {/* Blocked badge */}
                            {blocked && (
                              <span
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-destructive/10 text-destructive"
                                title="Waiting for dependencies to complete"
                              >
                                <Cancel01Icon className="h-3 w-3" aria-hidden="true" />
                                <span>Blocked</span>
                              </span>
                            )}

                            {/* Dependency details tooltip
                                Uses same dual-lookup pattern as isTaskBlocked:
                                matches by id (stable) OR task_number (human-readable)
                                @see docs/architecture/task-identifiers.md */}
                            {hasDependencies && task.depends_on && (
                              <span
                                className="ml-2 text-xs text-muted-foreground cursor-help"
                                title={`Dependencies:\n${task.depends_on
                                  .map((depId) => {
                                    // Dual-lookup: supports both id and task_number references
                                    const depTask = allTasks.find(
                                      (t) => t.id === depId || t.task_number === depId
                                    );
                                    return depTask
                                      ? `${depTask.task_number}: ${depTask.title} (${depTask.status})`
                                      : depId;
                                  })
                                  .join('\n')}`}
                              >
                                Depends on: {task.depends_on.join(', ')}
                              </span>
                            )}
                          </div>

                          {task.description && (
                            <div className="ml-14 mt-2 text-xs text-muted-foreground">
                              {task.description}
                            </div>
                          )}

                          {/* Quality Gates Section */}
                          {(task.status === 'completed' || task.status === 'in_progress') && (
                            <div className="ml-14 mt-3 border-t border-border pt-3">
                              <button
                                onClick={() => toggleTask(task.id)}
                                className="flex items-center gap-2 text-xs font-medium text-foreground hover:text-primary mb-2"
                                aria-expanded={expandedTasks.has(task.id)}
                              >
                                <span>{expandedTasks.has(task.id) ? '▼' : '▶'}</span>
                                <span>Quality Gates</span>
                              </button>
                              {expandedTasks.has(task.id) && (
                                <div className="mt-2">
                                  <QualityGateStatus
                                    taskId={parseInt(task.id, 10)}
                                    autoRefresh={true}
                                    refreshInterval={5000}
                                  />
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
});

TaskTreeView.displayName = 'TaskTreeView';

export default TaskTreeView;
