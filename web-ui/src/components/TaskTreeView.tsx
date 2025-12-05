/**
 * TaskTreeView Component
 * Hierarchical tree view of issues and their tasks
 */

'use client';

import { useState, memo } from 'react';
import type { Issue, Task, WorkStatus } from '@/types/api';
import QualityGateStatus from './quality-gates/QualityGateStatus';

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
        return 'bg-green-100 text-green-800';
      case 'in_progress':
        return 'bg-blue-100 text-blue-800';
      case 'blocked':
        return 'bg-red-100 text-red-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'assigned':
        return 'bg-yellow-100 text-yellow-800';
      case 'pending':
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  // Get priority badge classes
  const getPriorityClasses = (priority: number) => {
    if (priority === 1) return 'bg-red-100 text-red-800';
    if (priority === 2) return 'bg-orange-100 text-orange-800';
    if (priority === 3) return 'bg-yellow-100 text-yellow-800';
    return 'bg-gray-100 text-gray-800';
  };

  // Get provenance icon
  const getProvenanceIcon = (proposedBy: 'agent' | 'human') => {
    return proposedBy === 'agent' ? '🤖' : '👤';
  };

  // Check if task is blocked by dependencies
  const isTaskBlocked = (task: Task, allTasks: Task[]): boolean => {
    if (!task.depends_on || task.depends_on.length === 0) return false;
    if (task.status === 'completed' || task.status === 'in_progress') return false;

    // Find dependency tasks and check if any are not completed
    return task.depends_on.some((depId) => {
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
      <div className="text-center py-8 text-gray-500">
        No issues available
      </div>
    );
  }

  return (
    <div role="tree" className="space-y-2">
      {issues.map((issue) => {
        const isExpanded = expandedIssues.has(issue.id);
        const hasTasks = issue.tasks && issue.tasks.length > 0;

        return (
          <div key={issue.id} className="border border-gray-200 rounded-lg">
            {/* Issue Header */}
            <div className="flex items-start gap-3 p-4 bg-white hover:bg-gray-50">
              {/* Expand/Collapse Button */}
              <button
                onClick={() => toggleIssue(issue.id)}
                aria-expanded={isExpanded}
                aria-label={isExpanded ? 'Collapse' : 'Expand'}
                className="flex-shrink-0 mt-1 text-gray-500 hover:text-gray-700"
              >
                {isExpanded ? '▼' : '▶'}
              </button>

              {/* Issue Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 mb-2">
                  <span className="flex-shrink-0 text-sm font-mono text-gray-500">
                    {issue.issue_number}
                  </span>
                  <h3 className="flex-1 font-medium text-gray-900">
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
                    <span className="text-xs text-gray-500">
                      Depends on: {issue.depends_on.join(', ')}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Tasks (when expanded) */}
            {isExpanded && (
              <div className="border-t border-gray-200 bg-gray-50 px-4 py-2">
                {!hasTasks ? (
                  <div className="text-sm text-gray-500 py-2 pl-8">
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
                          className={`ml-8 p-3 bg-white border rounded transition-colors ${
                            blocked
                              ? 'border-red-300 bg-red-50'
                              : task.status === 'completed'
                              ? 'border-green-200'
                              : task.status === 'in_progress'
                              ? 'border-blue-200'
                              : 'border-gray-200'
                          }`}
                        >
                          <div className="flex items-start gap-2 mb-1">
                            {/* Dependency indicator */}
                            {hasDependencies && (
                              <span
                                className="flex-shrink-0 text-sm"
                                title={`Depends on: ${task.depends_on.join(', ')}`}
                              >
                                🔗
                              </span>
                            )}
                            <span className="flex-shrink-0 text-xs font-mono text-gray-500">
                              {task.task_number}
                            </span>
                            <span className="flex-1 text-sm font-medium text-gray-900">
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
                                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800"
                                title="Waiting for dependencies to complete"
                              >
                                🚫 Blocked
                              </span>
                            )}

                            {/* Dependency details */}
                            {hasDependencies && (
                              <span className="text-xs text-gray-500">
                                Depends on: {task.depends_on.join(', ')}
                              </span>
                            )}
                          </div>

                          {task.description && (
                            <div className="ml-14 mt-2 text-xs text-gray-600">
                              {task.description}
                            </div>
                          )}

                          {/* Quality Gates Section */}
                          {(task.status === 'completed' || task.status === 'in_progress') && (
                            <div className="ml-14 mt-3 border-t border-gray-200 pt-3">
                              <button
                                onClick={() => toggleTask(task.id)}
                                className="flex items-center gap-2 text-xs font-medium text-gray-700 hover:text-gray-900 mb-2"
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
