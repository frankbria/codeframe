'use client';

import { useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { TaskBoardContent } from './TaskBoardContent';
import { TaskDetailModal } from './TaskDetailModal';
import { TaskFilters } from './TaskFilters';
import { BatchActionsBar } from './BatchActionsBar';
import { BulkActionConfirmDialog, type BulkActionType } from './BulkActionConfirmDialog';
import { Cancel01Icon, Task01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { tasksApi, prdApi } from '@/lib/api';
import { useRequirementsLookup } from '@/hooks/useRequirementsLookup';
import type {
  TaskStatus,
  TaskListResponse,
  BatchStrategy,
  ApiError,
  PrdListResponse,
} from '@/types';

interface TaskBoardViewProps {
  workspacePath: string;
}

export function TaskBoardView({ workspacePath }: TaskBoardViewProps) {
  const router = useRouter();

  // ─── Data fetching ─────────────────────────────────────────────
  const { data, isLoading, error, mutate } = useSWR<TaskListResponse, ApiError>(
    `/api/v2/tasks?path=${workspacePath}`,
    () => tasksApi.getAll(workspacePath)
  );
  const { requirementsMap } = useRequirementsLookup(workspacePath);

  // PRD existence check — drives empty state context message
  const { data: prdData } = useSWR<PrdListResponse>(
    `/api/v2/prd?path=${workspacePath}`,
    () => prdApi.getAll(workspacePath)
  );
  const hasPrd = (prdData?.total ?? 0) > 0;

  // ─── Filter state ──────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskStatus | null>(null);

  // ─── Batch execution state ─────────────────────────────────────
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());
  const [batchStrategy, setBatchStrategy] = useState<BatchStrategy>('serial');
  const [isExecuting, setIsExecuting] = useState(false);
  const [isStoppingBatch, setIsStoppingBatch] = useState(false);
  const [isResettingBatch, setIsResettingBatch] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    type: BulkActionType;
    count: number;
    taskIds: string[];
  } | null>(null);

  // ─── Detail modal state ────────────────────────────────────────
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);

  // ─── Error state for actions ───────────────────────────────────
  const [actionError, setActionError] = useState<string | null>(null);

  // ─── Per-task loading state ──────────────────────────────────────
  const [loadingTaskIds, setLoadingTaskIds] = useState<Set<string>>(new Set());

  // ─── Filtered tasks ────────────────────────────────────────────
  const filteredTasks = useMemo(() => {
    if (!data?.tasks) return [];
    let tasks = data.tasks;

    if (statusFilter) {
      tasks = tasks.filter((t) => t.status === statusFilter);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      tasks = tasks.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q)
      );
    }

    return tasks;
  }, [data?.tasks, statusFilter, searchQuery]);

  // ─── Selected tasks (for batch actions) ───────────────────────
  // Derive from full task list (not filteredTasks) so bulk actions
  // include all selected tasks even when filters hide some of them.
  const selectedTasks = useMemo(
    () => (data?.tasks ?? []).filter((t) => selectedTaskIds.has(t.id)),
    [data?.tasks, selectedTaskIds]
  );

  // ─── Handlers ──────────────────────────────────────────────────
  const handleToggleSelectionMode = useCallback(() => {
    setSelectionMode((prev) => {
      if (prev) setSelectedTaskIds(new Set());
      return !prev;
    });
  }, []);

  const handleToggleSelect = useCallback((taskId: string) => {
    setSelectedTaskIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedTaskIds(new Set());
  }, []);

  const handleSelectAll = useCallback((taskIds: string[]) => {
    setSelectedTaskIds((prev) => {
      const next = new Set(prev);
      for (const id of taskIds) next.add(id);
      return next;
    });
  }, []);

  const handleDeselectAll = useCallback((taskIds: string[]) => {
    setSelectedTaskIds((prev) => {
      const next = new Set(prev);
      for (const id of taskIds) next.delete(id);
      return next;
    });
  }, []);

  const handleTaskClick = useCallback((taskId: string) => {
    setDetailTaskId(taskId);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setDetailTaskId(null);
  }, []);

  const handleExecute = useCallback(
    async (taskId: string) => {
      setActionError(null);
      try {
        await tasksApi.startExecution(workspacePath, taskId);
        setDetailTaskId(null);
        router.push(`/execution/${taskId}`);
      } catch (err) {
        const apiErr = err as ApiError;
        setActionError(apiErr.detail || 'Failed to start execution');
      }
    },
    [workspacePath, router]
  );

  const handleMarkReady = useCallback(
    async (taskId: string) => {
      setActionError(null);
      try {
        await tasksApi.updateStatus(workspacePath, taskId, 'READY');
        await mutate();
      } catch (err) {
        const apiErr = err as ApiError;
        setActionError(apiErr.detail || 'Failed to update task status');
      }
    },
    [workspacePath, mutate]
  );

  const handleStop = useCallback(
    async (taskId: string) => {
      setActionError(null);
      setLoadingTaskIds((prev) => new Set(prev).add(taskId));
      try {
        await tasksApi.stopExecution(workspacePath, taskId);
        await mutate();
      } catch (err) {
        const apiErr = err as ApiError;
        setActionError(apiErr.detail || 'Failed to stop task');
      } finally {
        setLoadingTaskIds((prev) => {
          const next = new Set(prev);
          next.delete(taskId);
          return next;
        });
      }
    },
    [workspacePath, mutate]
  );

  const handleReset = useCallback(
    async (taskId: string) => {
      setActionError(null);
      setLoadingTaskIds((prev) => new Set(prev).add(taskId));
      try {
        await tasksApi.updateStatus(workspacePath, taskId, 'READY');
        await mutate();
      } catch (err) {
        const apiErr = err as ApiError;
        setActionError(apiErr.detail || 'Failed to reset task');
      } finally {
        setLoadingTaskIds((prev) => {
          const next = new Set(prev);
          next.delete(taskId);
          return next;
        });
      }
    },
    [workspacePath, mutate]
  );

  const handleExecuteBatch = useCallback(async () => {
    if (selectedTaskIds.size === 0) return;
    setIsExecuting(true);
    setActionError(null);
    try {
      const result = await tasksApi.executeBatch(workspacePath, {
        task_ids: Array.from(selectedTaskIds),
        strategy: batchStrategy,
      });
      setSelectionMode(false);
      setSelectedTaskIds(new Set());
      router.push(`/execution?batch=${result.batch_id}`);
    } catch (err) {
      const apiErr = err as ApiError;
      setActionError(apiErr.detail || 'Failed to start batch execution');
    } finally {
      setIsExecuting(false);
    }
  }, [workspacePath, selectedTaskIds, batchStrategy, router]);

  const handleStopBatch = useCallback(() => {
    const inProgressTasks = selectedTasks.filter((t) => t.status === 'IN_PROGRESS');
    setConfirmAction({ type: 'stop', count: inProgressTasks.length, taskIds: inProgressTasks.map((t) => t.id) });
  }, [selectedTasks]);

  const handleResetBatch = useCallback(() => {
    const failedTasks = selectedTasks.filter((t) => t.status === 'FAILED');
    setConfirmAction({ type: 'reset', count: failedTasks.length, taskIds: failedTasks.map((t) => t.id) });
  }, [selectedTasks]);

  const handleConfirmAction = useCallback(async () => {
    if (!confirmAction) return;
    setActionError(null);

    try {
      if (confirmAction.type === 'stop') {
        setIsStoppingBatch(true);
        const results = await Promise.allSettled(
          confirmAction.taskIds.map((id) => tasksApi.stopExecution(workspacePath, id))
        );
        const failures = results.filter((r) => r.status === 'rejected');
        if (failures.length > 0) {
          setActionError(`Failed to stop ${failures.length} task(s)`);
        }
      } else if (confirmAction.type === 'reset') {
        setIsResettingBatch(true);
        const results = await Promise.allSettled(
          confirmAction.taskIds.map((id) => tasksApi.updateStatus(workspacePath, id, 'READY'))
        );
        const failures = results.filter((r) => r.status === 'rejected');
        if (failures.length > 0) {
          setActionError(`Failed to reset ${failures.length} task(s)`);
        }
      }
    } finally {
      setIsStoppingBatch(false);
      setIsResettingBatch(false);
      setConfirmAction(null);
      handleClearSelection();
      await mutate();
    }
  }, [confirmAction, workspacePath, mutate, handleClearSelection]);

  const handleStatusChange = useCallback(() => {
    mutate();
  }, [mutate]);

  // ─── Render ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-9 w-64 animate-pulse rounded bg-muted" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-lg bg-muted/30" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-6">
        <h2 className="text-lg font-semibold text-destructive">Error</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {error.detail || 'Failed to load tasks'}
        </p>
      </div>
    );
  }

  const tasks = data?.tasks ?? [];

  return (
    <div className="space-y-4">
      {/* Header: page title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Task Board</h1>
          <p className="text-sm text-muted-foreground">
            {tasks.length} task{tasks.length !== 1 ? 's' : ''} total
          </p>
        </div>
      </div>

      {/* Filters + batch actions */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <TaskFilters
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          statusFilter={statusFilter}
          onStatusFilter={setStatusFilter}
        />
        <BatchActionsBar
          selectionMode={selectionMode}
          onToggleSelectionMode={handleToggleSelectionMode}
          selectedCount={selectedTaskIds.size}
          strategy={batchStrategy}
          onStrategyChange={setBatchStrategy}
          onExecuteBatch={handleExecuteBatch}
          onClearSelection={handleClearSelection}
          isExecuting={isExecuting}
          selectedTasks={selectedTasks}
          onStopBatch={handleStopBatch}
          onResetBatch={handleResetBatch}
          isStoppingBatch={isStoppingBatch}
          isResettingBatch={isResettingBatch}
        />
      </div>

      {/* Action error banner */}
      {actionError && (
        <div role="alert" className="flex items-center justify-between rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            aria-label="Dismiss error"
            className="ml-2 rounded p-0.5 text-destructive hover:text-destructive/80 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
          >
            <Cancel01Icon className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Empty state — shown when no tasks exist after loading completes */}
      {tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-muted/30 py-16 text-center">
          <Task01Icon className="mb-4 h-10 w-10 text-muted-foreground/50" />
          <h2 className="text-base font-semibold text-foreground">No tasks yet</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Generate tasks from your PRD or create them manually to start building.
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            {hasPrd ? (
              <span className="flex items-center gap-1 justify-center">
                <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                PRD found — ready to generate tasks
              </span>
            ) : (
              <span className="flex items-center gap-1 justify-center">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                No PRD yet — create one first
              </span>
            )}
          </p>
          <div className="mt-6 flex gap-3">
            <Button asChild>
              <Link href="/prd">
                Generate from PRD →
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/prd">
                View PRD
              </Link>
            </Button>
          </div>
        </div>
      )}

      {/* Kanban board — hidden when no tasks */}
      {tasks.length > 0 && <TaskBoardContent
        tasks={filteredTasks}
        selectionMode={selectionMode}
        selectedTaskIds={selectedTaskIds}
        onTaskClick={handleTaskClick}
        onToggleSelect={handleToggleSelect}
        onExecute={handleExecute}
        onMarkReady={handleMarkReady}
        onStop={handleStop}
        onReset={handleReset}
        onSelectAll={handleSelectAll}
        onDeselectAll={handleDeselectAll}
        loadingTaskIds={loadingTaskIds}
        requirementsMap={requirementsMap}
      />}

      {/* Task detail modal */}
      <TaskDetailModal
        taskId={detailTaskId}
        workspacePath={workspacePath}
        open={detailTaskId !== null}
        onClose={handleCloseDetail}
        onExecute={handleExecute}
        onStatusChange={handleStatusChange}
        onOpenTask={handleTaskClick}
      />

      {/* Bulk action confirmation */}
      <BulkActionConfirmDialog
        open={confirmAction !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmAction(null);
        }}
        actionType={confirmAction?.type ?? 'stop'}
        taskCount={confirmAction?.count ?? 0}
        onConfirm={handleConfirmAction}
        isLoading={isStoppingBatch || isResettingBatch || isExecuting}
      />
    </div>
  );
}
