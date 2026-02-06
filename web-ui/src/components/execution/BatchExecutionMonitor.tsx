'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import {
  CheckmarkCircle01Icon,
  Cancel01Icon,
  Loading03Icon,
  Alert02Icon,
  StopIcon,
} from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { batchesApi, tasksApi } from '@/lib/api';
import { EventStream } from './EventStream';
import { useExecutionMonitor } from '@/hooks/useExecutionMonitor';
import type { BatchResponse, Task } from '@/types';

// ── Status icon helper ────────────────────────────────────────────────

const statusConfig: Record<string, { icon: typeof CheckmarkCircle01Icon; className: string; label: string }> = {
  COMPLETED: { icon: CheckmarkCircle01Icon, className: 'text-green-600', label: 'Completed' },
  DONE: { icon: CheckmarkCircle01Icon, className: 'text-green-600', label: 'Done' },
  FAILED: { icon: Cancel01Icon, className: 'text-red-600', label: 'Failed' },
  IN_PROGRESS: { icon: Loading03Icon, className: 'text-blue-600 animate-spin', label: 'Running' },
  BLOCKED: { icon: Alert02Icon, className: 'text-amber-600', label: 'Blocked' },
  READY: { icon: Loading03Icon, className: 'text-gray-400', label: 'Waiting' },
};

function getStatusConfig(status: string) {
  return statusConfig[status] ?? { icon: Loading03Icon, className: 'text-gray-400', label: status };
}

// ── Props ─────────────────────────────────────────────────────────────

interface BatchExecutionMonitorProps {
  batchId: string;
  workspacePath: string;
}

export function BatchExecutionMonitor({ batchId, workspacePath }: BatchExecutionMonitorProps) {
  const router = useRouter();
  const [batch, setBatch] = useState<BatchResponse | null>(null);
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Track which task IDs have already been fetched to avoid refetching
  const fetchedTaskIdsRef = useRef<Set<string>>(new Set());

  // ── Fetch batch details + task names ────────────────────────────────
  const fetchBatch = useCallback(async () => {
    try {
      setError(null);
      const data = await batchesApi.get(workspacePath, batchId);
      setBatch(data);

      // Fetch task details for any new task IDs (check ref, not state)
      for (const taskId of data.task_ids) {
        if (!fetchedTaskIdsRef.current.has(taskId)) {
          fetchedTaskIdsRef.current.add(taskId);
          tasksApi.getOne(workspacePath, taskId).then((task) => {
            setTasks((prev) => ({ ...prev, [taskId]: task }));
          }).catch(() => {
            // Task may have been deleted
          });
        }
      }
    } catch {
      setError('Failed to load batch details');
    }
  }, [workspacePath, batchId]);

  // Initial fetch
  useEffect(() => {
    fetchBatch();
  }, [batchId, workspacePath]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll every 5 seconds while batch is active
  useEffect(() => {
    const isActive = batch && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(batch.status);
    if (isActive) {
      pollRef.current = setInterval(fetchBatch, 5000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [batch?.status, fetchBatch]);

  // Auto-expand the first IN_PROGRESS task
  useEffect(() => {
    if (!batch || expandedTaskId) return;
    const inProgress = batch.task_ids.find(
      (id) => batch.results[id] === 'IN_PROGRESS'
    );
    if (inProgress) setExpandedTaskId(inProgress);
  }, [batch, expandedTaskId]);

  // ── Batch controls ──────────────────────────────────────────────────
  const handleStop = useCallback(async () => {
    try {
      await batchesApi.stop(workspacePath, batchId);
      fetchBatch();
    } catch {
      setError('Failed to stop batch');
    }
  }, [workspacePath, batchId, fetchBatch]);

  const handleCancel = useCallback(async () => {
    try {
      await batchesApi.cancel(workspacePath, batchId);
      fetchBatch();
    } catch {
      setError('Failed to cancel batch');
    }
  }, [workspacePath, batchId, fetchBatch]);

  // ── Render ──────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center dark:border-red-900 dark:bg-red-950/30">
        <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
      </div>
    );
  }

  if (!batch) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loading03Icon className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isActive = !['COMPLETED', 'FAILED', 'CANCELLED'].includes(batch.status);
  const completedCount = batch.task_ids.filter(
    (id) => batch.results[id] === 'COMPLETED' || batch.results[id] === 'DONE'
  ).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between rounded-lg border bg-card p-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Batch Execution ({batch.task_ids.length} tasks)
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Strategy: {batch.strategy} &middot; {completedCount}/{batch.task_ids.length} complete
          </p>
        </div>

        {isActive && (
          <div className="flex items-center gap-2">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 gap-1.5 px-3">
                  <StopIcon className="h-3.5 w-3.5" />
                  Stop Batch
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Stop Batch?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will stop all currently running tasks in this batch.
                    Completed tasks will not be affected.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleStop}>
                    Stop Batch
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>

            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="h-8 gap-1.5 px-3">
                  <Cancel01Icon className="h-3.5 w-3.5" />
                  Cancel Batch
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Cancel Batch?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will cancel the entire batch, stopping all running
                    tasks and skipping remaining ones.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep Running</AlertDialogCancel>
                  <AlertDialogAction onClick={handleCancel}>
                    Cancel Batch
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}

        {!isActive && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push('/tasks')}
          >
            Back to Tasks
          </Button>
        )}
      </div>

      {/* Task rows */}
      <div className="space-y-1">
        {batch.task_ids.map((taskId) => (
          <BatchTaskRow
            key={taskId}
            taskId={taskId}
            task={tasks[taskId] ?? null}
            status={batch.results[taskId] ?? 'READY'}
            isExpanded={expandedTaskId === taskId}
            onToggle={() =>
              setExpandedTaskId(expandedTaskId === taskId ? null : taskId)
            }
            workspacePath={workspacePath}
          />
        ))}
      </div>
    </div>
  );
}

// ── Batch Task Row ────────────────────────────────────────────────────

function BatchTaskRow({
  taskId,
  task,
  status,
  isExpanded,
  onToggle,
  workspacePath,
}: {
  taskId: string;
  task: Task | null;
  status: string;
  isExpanded: boolean;
  onToggle: () => void;
  workspacePath: string;
}) {
  const config = getStatusConfig(status);
  const StatusIcon = config.icon;

  // Only connect SSE when expanded and task is in progress or blocked
  const shouldStream = isExpanded && (status === 'IN_PROGRESS' || status === 'BLOCKED');
  const monitor = useExecutionMonitor(shouldStream ? taskId : null, workspacePath);

  return (
    <div className="rounded-lg border bg-card">
      {/* Row header */}
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50"
        aria-expanded={isExpanded}
      >
        <StatusIcon className={`h-4 w-4 shrink-0 ${config.className}`} />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {task?.title ?? taskId}
        </span>
        <span className="text-xs text-muted-foreground">{config.label}</span>
        <span className="text-xs text-muted-foreground">
          {isExpanded ? '▲' : '▼'}
        </span>
      </button>

      {/* Expanded event stream */}
      {isExpanded && (
        <div className="border-t px-4 pb-4 pt-2">
          {shouldStream ? (
            <div className="h-64">
              <EventStream
                events={monitor.events}
                workspacePath={workspacePath}
              />
            </div>
          ) : (
            <p className="py-4 text-center text-xs text-muted-foreground">
              {status === 'COMPLETED' || status === 'DONE'
                ? 'Task completed successfully.'
                : status === 'FAILED'
                  ? 'Task failed. Check diagnostics for details.'
                  : 'Waiting to start...'}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
