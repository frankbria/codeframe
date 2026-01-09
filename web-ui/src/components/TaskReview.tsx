/**
 * TaskReview Component
 * Hierarchical tree view with checkboxes for reviewing and approving task breakdown
 * Used in planning phase to let users select which tasks to include
 */

'use client';

import { useState, useEffect, useCallback, useRef, memo } from 'react';
import { useRouter } from 'next/navigation';
import { projectsApi } from '@/lib/api';
import { Button } from '@/components/ui/button';
import type { Issue } from '@/types/api';

export interface TaskReviewProps {
  projectId: number | string;
  onApprovalSuccess?: () => void;
  onApprovalError?: (error: Error) => void;
}

interface SprintGroup {
  sprintNumber: number;
  issues: Issue[];
  totalTasks: number;
}

/**
 * Groups issues by sprint number extracted from issue_number
 * e.g., "1.1" -> Sprint 1, "2.3" -> Sprint 2
 */
function groupIssuesBySprint(issues: Issue[]): SprintGroup[] {
  const sprintMap = new Map<number, Issue[]>();

  issues.forEach((issue) => {
    const sprintNumber = parseInt(issue.issue_number.split('.')[0], 10) || 1;
    const existing = sprintMap.get(sprintNumber) || [];
    sprintMap.set(sprintNumber, [...existing, issue]);
  });

  return Array.from(sprintMap.entries())
    .map(([sprintNumber, sprintIssues]) => ({
      sprintNumber,
      issues: sprintIssues,
      totalTasks: sprintIssues.reduce(
        (sum, issue) => sum + (issue.tasks?.length || 0),
        0
      ),
    }))
    .sort((a, b) => a.sprintNumber - b.sprintNumber);
}

/**
 * Get all task IDs from issues
 */
function getAllTaskIds(issues: Issue[]): string[] {
  return issues.flatMap((issue) => (issue.tasks || []).map((task) => task.id));
}

/**
 * Get task IDs for a specific issue
 */
function getIssueTaskIds(issue: Issue): string[] {
  return (issue.tasks || []).map((task) => task.id);
}

const TaskReview = memo(function TaskReview({
  projectId,
  onApprovalSuccess,
  onApprovalError,
}: TaskReviewProps) {
  const router = useRouter();

  // Data state
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selection state
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());

  // Expansion state
  const [expandedSprints, setExpandedSprints] = useState<Set<number>>(new Set());
  const [expandedIssues, setExpandedIssues] = useState<Set<string>>(new Set());

  // Approval state
  const [approving, setApproving] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  // Refs for indeterminate checkboxes
  const issueCheckboxRefs = useRef<Map<string, HTMLInputElement>>(new Map());

  // Fetch issues with tasks on mount
  // Must pass include='tasks' to get nested task arrays for approval selection
  const fetchIssues = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await projectsApi.getIssues(projectId, { include: 'tasks' });
      const fetchedIssues = response.data.issues;
      setIssues(fetchedIssues);

      // Initialize all tasks as selected
      const allTaskIds = getAllTaskIds(fetchedIssues);
      setSelectedTaskIds(new Set(allTaskIds));

      // Auto-expand first sprint if there are issues
      if (fetchedIssues.length > 0) {
        const firstSprint = parseInt(fetchedIssues[0].issue_number.split('.')[0], 10) || 1;
        setExpandedSprints(new Set([firstSprint]));
      }
    } catch (_err) {
      setError('Failed to load task breakdown. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchIssues();
  }, [fetchIssues]);

  // Update indeterminate state for issue checkboxes
  useEffect(() => {
    issues.forEach((issue) => {
      const checkbox = issueCheckboxRefs.current.get(issue.id);
      if (checkbox) {
        const issueTaskIds = getIssueTaskIds(issue);
        const selectedCount = issueTaskIds.filter((id) => selectedTaskIds.has(id)).length;
        const isIndeterminate = selectedCount > 0 && selectedCount < issueTaskIds.length;
        checkbox.indeterminate = isIndeterminate;
      }
    });
  }, [selectedTaskIds, issues]);

  // Toggle sprint expansion
  const toggleSprint = useCallback((sprintNumber: number) => {
    setExpandedSprints((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(sprintNumber)) {
        newSet.delete(sprintNumber);
      } else {
        newSet.add(sprintNumber);
      }
      return newSet;
    });
  }, []);

  // Toggle issue expansion
  const toggleIssue = useCallback((issueId: string) => {
    setExpandedIssues((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(issueId)) {
        newSet.delete(issueId);
      } else {
        newSet.add(issueId);
      }
      return newSet;
    });
  }, []);

  // Toggle single task selection
  const toggleTask = useCallback((taskId: string) => {
    setSelectedTaskIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  }, []);

  // Toggle all tasks in an issue
  const toggleIssueTasks = useCallback((issue: Issue) => {
    const issueTaskIds = getIssueTaskIds(issue);

    setSelectedTaskIds((prev) => {
      // Compute allSelected inside the updater to avoid stale closure
      const allSelected = issueTaskIds.every((id) => prev.has(id));
      const newSet = new Set(prev);

      if (allSelected) {
        // Deselect all tasks in this issue
        issueTaskIds.forEach((id) => newSet.delete(id));
      } else {
        // Select all tasks in this issue
        issueTaskIds.forEach((id) => newSet.add(id));
      }
      return newSet;
    });
  }, []);

  // Handle approval
  const handleApprove = useCallback(async () => {
    if (selectedTaskIds.size === 0) return;

    // Validate projectId before calling API
    const numericProjectId = typeof projectId === 'string' ? parseInt(projectId, 10) : projectId;
    if (isNaN(numericProjectId) || numericProjectId <= 0) {
      setApprovalError('Invalid project ID. Please refresh and try again.');
      return;
    }

    setApproving(true);
    setApprovalError(null);

    try {
      await projectsApi.approveTaskBreakdown(
        numericProjectId,
        Array.from(selectedTaskIds)
      );

      onApprovalSuccess?.();
      router.push(`/projects/${projectId}`);
    } catch (err: unknown) {
      // Log full error details for debugging
      console.error('[TaskReview] Task approval failed:', err);

      // Extract specific error message from API response
      let errorMessage = 'Failed to approve tasks. Please try again.';
      let isAuthError = false;

      if (err instanceof Error) {
        // Check for authentication errors (401)
        if (err.message.includes('401') || err.message.includes('Not authenticated')) {
          errorMessage = 'Session expired. Please log in again to continue.';
          isAuthError = true;
        } else if (err.message.includes('403')) {
          errorMessage = 'You do not have permission to approve these tasks.';
        } else if (err.message.includes('404')) {
          errorMessage = 'Project or tasks not found. Please refresh the page.';
        } else if (err.message.includes('Request failed:')) {
          // Extract detail from our authFetch error format
          const detailMatch = err.message.match(/Request failed: \d+ (.+)/);
          if (detailMatch && detailMatch[1]) {
            try {
              const detail = JSON.parse(detailMatch[1]);
              errorMessage = detail.detail || detail.message || errorMessage;
            } catch {
              // Use the raw message if not JSON
              errorMessage = detailMatch[1] || errorMessage;
            }
          }
        }
      }

      setApprovalError(errorMessage);

      // Redirect to login on auth errors
      if (isAuthError) {
        setTimeout(() => {
          router.push('/login');
        }, 2000);
      }

      const error = err instanceof Error ? err : new Error(errorMessage);
      onApprovalError?.(error);
    } finally {
      setApproving(false);
    }
  }, [projectId, selectedTaskIds, onApprovalSuccess, onApprovalError, router]);

  // Check if all tasks in an issue are selected
  const isIssueFullySelected = (issue: Issue): boolean => {
    const issueTaskIds = getIssueTaskIds(issue);
    return issueTaskIds.length > 0 && issueTaskIds.every((id) => selectedTaskIds.has(id));
  };

  // Computed values
  const sprintGroups = groupIssuesBySprint(issues);
  const totalTasks = getAllTaskIds(issues).length;

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-muted-foreground">Loading task breakdown...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-8 gap-4">
        <div className="text-destructive">{error}</div>
        <Button variant="outline" onClick={fetchIssues} aria-label="Retry">
          Retry
        </Button>
      </div>
    );
  }

  // Empty state
  if (issues.length === 0 || totalTasks === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No tasks available for approval
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Task Tree */}
      <div role="tree" className="space-y-3">
        {sprintGroups.map((sprint) => {
          const isSprintExpanded = expandedSprints.has(sprint.sprintNumber);

          return (
            <div
              key={sprint.sprintNumber}
              className="border border-border rounded-lg overflow-hidden"
            >
              {/* Sprint Header */}
              <div className="flex items-center gap-3 p-4 bg-muted/50">
                <button
                  onClick={() => toggleSprint(sprint.sprintNumber)}
                  aria-expanded={isSprintExpanded}
                  aria-label={isSprintExpanded ? 'Collapse' : 'Expand'}
                  className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {isSprintExpanded ? '▼' : '▶'}
                </button>
                <div className="flex-1">
                  <h3 className="font-semibold text-foreground">
                    Sprint {sprint.sprintNumber}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {sprint.issues.length} issue{sprint.issues.length !== 1 ? 's' : ''} ·{' '}
                    {sprint.totalTasks} task{sprint.totalTasks !== 1 ? 's' : ''}
                  </p>
                </div>
              </div>

              {/* Issues (when sprint expanded) */}
              {isSprintExpanded && (
                <div className="border-t border-border">
                  {sprint.issues.map((issue) => {
                    const isIssueExpanded = expandedIssues.has(issue.id);
                    const hasTasks = issue.tasks && issue.tasks.length > 0;
                    const taskCount = issue.tasks?.length || 0;

                    return (
                      <div
                        key={issue.id}
                        className="border-b border-border last:border-b-0"
                      >
                        {/* Issue Header */}
                        <div className="flex items-center gap-3 p-4 bg-card hover:bg-muted/30 transition-colors">
                          {/* Issue Checkbox */}
                          <input
                            ref={(el) => {
                              if (el) {
                                issueCheckboxRefs.current.set(issue.id, el);
                              }
                            }}
                            type="checkbox"
                            checked={isIssueFullySelected(issue)}
                            onChange={() => toggleIssueTasks(issue)}
                            aria-label={issue.title}
                            className="h-4 w-4 rounded border-border accent-primary cursor-pointer"
                            disabled={!hasTasks}
                          />

                          {/* Expand/Collapse Button */}
                          <button
                            onClick={() => toggleIssue(issue.id)}
                            aria-expanded={isIssueExpanded}
                            aria-label={isIssueExpanded ? 'Collapse' : 'Expand'}
                            className="flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                          >
                            {isIssueExpanded ? '▼' : '▶'}
                          </button>

                          {/* Issue Content */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-mono text-muted-foreground">
                                {issue.issue_number}
                              </span>
                              <span className="font-medium text-foreground truncate">
                                {issue.title}
                              </span>
                            </div>
                            <p className="text-sm text-muted-foreground">
                              {taskCount} task{taskCount !== 1 ? 's' : ''}
                            </p>
                          </div>
                        </div>

                        {/* Tasks (when issue expanded) */}
                        {isIssueExpanded && (
                          <div className="bg-muted/20 px-4 py-2">
                            {!hasTasks ? (
                              <div className="text-sm text-muted-foreground py-2 pl-12">
                                No tasks for this issue
                              </div>
                            ) : (
                              <div className="space-y-2">
                                {issue.tasks!.map((task) => (
                                  <div
                                    key={task.id}
                                    className="flex items-start gap-3 ml-8 p-3 bg-card border border-border rounded transition-colors hover:bg-muted/30"
                                  >
                                    {/* Task Checkbox */}
                                    <input
                                      type="checkbox"
                                      checked={selectedTaskIds.has(task.id)}
                                      onChange={() => toggleTask(task.id)}
                                      aria-label={task.title}
                                      className="h-4 w-4 mt-0.5 rounded border-border accent-primary cursor-pointer"
                                    />

                                    {/* Task Content */}
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2">
                                        <span className="text-xs font-mono text-muted-foreground">
                                          {task.task_number}
                                        </span>
                                        <span className="text-sm font-medium text-foreground">
                                          {task.title}
                                        </span>
                                      </div>
                                      {task.description && (
                                        <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                                          {task.description}
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                ))}
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
          );
        })}
      </div>

      {/* Summary and Approval */}
      <div className="border-t border-border pt-4 space-y-4">
        {/* Selection Summary */}
        <div className="flex items-center gap-4 text-lg">
          <span className="font-medium text-foreground">
            ✅ {selectedTaskIds.size} task{selectedTaskIds.size !== 1 ? 's' : ''} selected
          </span>
        </div>

        {/* Approval Error */}
        {approvalError && (
          <div className="p-3 bg-destructive/10 border border-destructive/20 rounded text-destructive text-sm">
            {approvalError}
          </div>
        )}

        {/* Approval Button */}
        <Button
          size="lg"
          onClick={handleApprove}
          disabled={approving || selectedTaskIds.size === 0}
          className="w-full sm:w-auto"
        >
          {approving ? 'Approving...' : 'Approve and Start Development'}
        </Button>
      </div>
    </div>
  );
});

TaskReview.displayName = 'TaskReview';

export default TaskReview;
