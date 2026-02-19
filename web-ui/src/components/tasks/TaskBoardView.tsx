'use client';

import { useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { TaskBoardContent } from './TaskBoardContent';
import { TaskDetailModal } from './TaskDetailModal';
import { TaskFilters } from './TaskFilters';
import { BatchActionsBar } from './BatchActionsBar';
import { BulkActionConfirmDialog, type BulkActionType } from './BulkActionConfirmDialog';
import { tasksApi } from '@/lib/api';
import type {
  TaskStatus,
  TaskListResponse,
  BatchStrategy,
  ApiError,
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
  } | null>(null);

  // ─── Detail modal state ────────────────────────────────────────
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null);

  // ─── Error state for actions ───────────────────────────────────
  const [actionError, setActionError] = useState<string | null>(null);

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
  const selectedTasks = useMemo(
    () => filteredTasks.filter((t) => selectedTaskIds.has(t.id)),
    [filteredTasks, selectedTaskIds]
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
      try {
        await tasksApi.stopExecution(workspacePath, taskId);
        await mutate();
      } catch (err) {
        const apiErr = err as ApiError;
        setActionError(apiErr.detail || 'Failed to stop task');
      }
    },
    [workspacePath, mutate]
  );

  const handleReset = useCallback(
    async (taskId: string) => {
      setActionError(null);
      try {
        await tasksApi.updateStatus(workspacePath, taskId, 'READY');
        await mutate();
      } catch (err) {
        const apiErr = err as ApiError;
        setActionError(apiErr.detail || 'Failed to reset task');
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
    const inProgressCount = selectedTasks.filter((t) => t.status === 'IN_PROGRESS').length;
    setConfirmAction({ type: 'stop', count: inProgressCount });
  }, [selectedTasks]);

  const handleResetBatch = useCallback(() => {
    const failedCount = selectedTasks.filter((t) => t.status === 'FAILED').length;
    setConfirmAction({ type: 'reset', count: failedCount });
  }, [selectedTasks]);

  const handleConfirmAction = useCallback(async () => {
    if (!confirmAction) return;
    setActionError(null);

    if (confirmAction.type === 'stop') {
      setIsStoppingBatch(true);
      const inProgressTasks = selectedTasks.filter((t) => t.status === 'IN_PROGRESS');
      const results = await Promise.allSettled(
        inProgressTasks.map((t) => tasksApi.stopExecution(workspacePath, t.id))
      );
      const failures = results.filter((r) => r.status === 'rejected');
      if (failures.length > 0) {
        setActionError(`Failed to stop ${failures.length} task(s)`);
      }
      setIsStoppingBatch(false);
    } else if (confirmAction.type === 'reset') {
      setIsResettingBatch(true);
      const failedTasks = selectedTasks.filter((t) => t.status === 'FAILED');
      const results = await Promise.allSettled(
        failedTasks.map((t) => tasksApi.updateStatus(workspacePath, t.id, 'READY'))
      );
      const failures = results.filter((r) => r.status === 'rejected');
      if (failures.length > 0) {
        setActionError(`Failed to reset ${failures.length} task(s)`);
      }
      setIsResettingBatch(false);
    } else if (confirmAction.type === 'execute') {
      await handleExecuteBatch();
    }

    setConfirmAction(null);
    handleClearSelection();
    await mutate();
  }, [confirmAction, selectedTasks, workspacePath, mutate, handleClearSelection, handleExecuteBatch]);

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
        <div className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {actionError}
        </div>
      )}

      {/* Kanban board */}
      <TaskBoardContent
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
      />

      {/* Task detail modal */}
      <TaskDetailModal
        taskId={detailTaskId}
        workspacePath={workspacePath}
        open={detailTaskId !== null}
        onClose={handleCloseDetail}
        onExecute={handleExecute}
        onStatusChange={handleStatusChange}
      />

      {/* Bulk action confirmation */}
      <BulkActionConfirmDialog
        open={confirmAction !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmAction(null);
        }}
        actionType={confirmAction?.type ?? 'execute'}
        taskCount={confirmAction?.count ?? 0}
        onConfirm={handleConfirmAction}
        isLoading={isStoppingBatch || isResettingBatch || isExecuting}
      />
    </div>
  );
}
