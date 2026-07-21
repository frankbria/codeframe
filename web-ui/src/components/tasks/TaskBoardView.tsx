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
import { GitHubIssueImportModal } from './GitHubIssueImportModal';
import { HugeiconsIcon } from '@hugeicons/react';
import { Cancel01Icon, Task01Icon, GithubIcon } from '@hugeicons/core-free-icons';
import { Button } from '@/components/ui/button';
import { tasksApi, prdApi, costsApi, integrationsApi } from '@/lib/api';
import { useRequirementsLookup } from '@/hooks/useRequirementsLookup';
import type {
  TaskStatus,
  TaskListResponse,
  TaskCostsResponse,
  TaskCostEntry,
  BatchStrategy,
  ApiError,
  PrdListResponse,
  GitHubIntegrationStatus,
  GitHubIssue,
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

  // Cost badge data (issue #558) — non-blocking. If this request fails or
  // returns no data the board still renders; badges simply don't show.
  //
  // Limit 1000: we want a badge for every task on the board, not just the
  // top 10 analytics view. The endpoint caps server-side at 1000. The SWR
  // key is intentionally separate from the /costs page (which uses a
  // user-controlled time range) — these are independent views.
  const { data: costData } = useSWR<TaskCostsResponse, ApiError>(
    `/api/v2/costs/tasks?path=${workspacePath}&limit=1000`,
    () => costsApi.getTopTasks(workspacePath, 30, 1000),
    { refreshInterval: 60000 }
  );
  const costMap = useMemo(() => {
    const map = new Map<string, TaskCostEntry>();
    for (const entry of costData?.tasks ?? []) {
      map.set(entry.task_id, entry);
    }
    return map;
  }, [costData?.tasks]);

  // PRD existence check — drives empty state context message
  const { data: prdData } = useSWR<PrdListResponse>(
    `/api/v2/prd?path=${workspacePath}`,
    () => prdApi.getAll(workspacePath)
  );
  const hasPrd = (prdData?.total ?? 0) > 0;

  // GitHub connection status (issue #564) — gates the "Import from GitHub"
  // button. Non-blocking: if this fails the board still renders without it.
  const { data: ghStatus } = useSWR<GitHubIntegrationStatus, ApiError>(
    `/api/v2/integrations/github/status?path=${workspacePath}`,
    () => integrationsApi.getStatus(workspacePath)
  );
  const githubConnected = ghStatus?.connected === true;

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

  // ─── GitHub issue import modal (issues #564 / #565) ────────────
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importSummary, setImportSummary] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Execute the import (#565): create tasks from the selected issues, then
  // refresh the board so the new tasks (with their GitHub badges) appear.
  const handleImportIssues = useCallback(
    async (selectedIssues: GitHubIssue[]) => {
      if (selectedIssues.length === 0) {
        setImportModalOpen(false);
        return;
      }
      setIsImporting(true);
      setActionError(null);
      setImportSummary(null);
      setImportError(null);
      let imported = false;
      try {
        const numbers = selectedIssues.map((i) => i.number);
        const result = await integrationsApi.importIssues(workspacePath, numbers);
        imported = true;
        setImportModalOpen(false);
        const parts = [
          `${result.total_created} task${result.total_created !== 1 ? 's' : ''} created`,
        ];
        if (result.skipped.length > 0) {
          parts.push(
            `${result.skipped.length} skipped (already imported)`
          );
        }
        setImportSummary(parts.join(' · '));
      } catch (err) {
        const apiErr = err as ApiError;
        // Keep the modal open and show the error inline there, so the user sees
        // it (a board-level banner would sit behind the dialog) and keeps their
        // selection for a retry.
        setImportError(apiErr.detail || 'Failed to import issues from GitHub');
      } finally {
        setIsImporting(false);
      }
      // Refresh the board AFTER the import resolves. A refresh failure is not an
      // import failure — the tasks were already created — so it must not flip
      // the success summary into an error (SWR will revalidate again later).
      if (imported) {
        mutate();
      }
    },
    [workspacePath, mutate]
  );

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
        {githubConnected && (
          <Button
            variant="outline"
            onClick={() => setImportModalOpen(true)}
          >
            <HugeiconsIcon icon={GithubIcon} className="mr-2 h-4 w-4" />
            Import from GitHub
          </Button>
        )}
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

      {/* Import success summary banner (#565) */}
      {importSummary && (
        <div
          role="status"
          className="flex items-center justify-between rounded-md bg-green-500/10 px-4 py-2 text-sm text-green-700 dark:text-green-400"
        >
          <span>Imported from GitHub: {importSummary}</span>
          <button
            onClick={() => setImportSummary(null)}
            aria-label="Dismiss import summary"
            className="ml-2 rounded p-0.5 hover:opacity-70 focus-visible:outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring"
          >
            <HugeiconsIcon icon={Cancel01Icon} className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Action error banner */}
      {actionError && (
        <div role="alert" className="flex items-center justify-between rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            aria-label="Dismiss error"
            className="ml-2 rounded p-0.5 text-destructive hover:text-destructive/80 focus-visible:outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring"
          >
            <HugeiconsIcon icon={Cancel01Icon} className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Empty state — shown when no tasks exist after loading completes */}
      {tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border bg-muted/30 py-16 text-center">
          <HugeiconsIcon icon={Task01Icon} className="mb-4 h-10 w-10 text-muted-foreground/50" />
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
            {hasPrd ? (
              <>
                <Button asChild>
                  <Link href="/prd">Generate from PRD →</Link>
                </Button>
                <Button variant="outline" asChild>
                  <Link href="/prd">View PRD</Link>
                </Button>
              </>
            ) : (
              <Button asChild>
                <Link href="/prd">Create PRD →</Link>
              </Button>
            )}
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
        costMap={costMap}
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

      {/* GitHub issue import browser (issue #564) */}
      <GitHubIssueImportModal
        open={importModalOpen}
        workspacePath={workspacePath}
        repo={ghStatus?.repo}
        importing={isImporting}
        importError={importError}
        onClose={() => {
          setImportModalOpen(false);
          setImportError(null);
        }}
        onImport={handleImportIssues}
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
