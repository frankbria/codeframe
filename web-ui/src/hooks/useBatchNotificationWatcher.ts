'use client';

import { useEffect, useRef } from 'react';
import { batchesApi, tasksApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { AddNotificationInput } from '@/hooks/useNotifications';
import type { AppNotificationBatchStatus } from '@/types';

const DEFAULT_INTERVAL_MS = 10_000;
const TERMINAL = ['COMPLETED', 'FAILED', 'CANCELLED'];

interface UseBatchNotificationWatcherOptions {
  intervalMs?: number;
}

/**
 * Cross-page background watcher that polls the workspace's batches and fires
 * notifications on terminal/blocked transitions — regardless of the current
 * route. This is what makes batch notifications work when the execution page
 * (and its `BatchExecutionMonitor`) is unmounted. See issue #652.
 *
 * Mounted once inside `NotificationProvider`, it is the single source of truth
 * for `batch.completed` and `blocker.created`; `BatchExecutionMonitor` no
 * longer dispatches these to avoid duplicates.
 */
export function useBatchNotificationWatcher(
  addNotification: (input: AddNotificationInput) => void,
  options?: UseBatchNotificationWatcherOptions
): void {
  const intervalMs = options?.intervalMs ?? DEFAULT_INTERVAL_MS;

  // Latest addNotification without retriggering the polling effect.
  const addRef = useRef(addNotification);
  addRef.current = addNotification;

  // Per-session transition baselines. `undefined` for a batch/task means
  // "never seen" — we record it without notifying so pre-existing terminal or
  // blocked state doesn't produce a spurious alert on first poll.
  const prevBatchStatusRef = useRef<Record<string, string>>({});
  const prevTaskStatusRef = useRef<Record<string, string>>({});
  // Workspace whose baselines the refs currently hold; resets on change.
  const watchedWorkspaceRef = useRef<string | null>(null);
  // Guards against overlapping polls: a slow poll (e.g. a sluggish list or the
  // extra title fetch on a BLOCKED transition) must not run concurrently with
  // the next tick, or two runs would read the same baseline before either
  // writes it — double-firing or re-arming a transition.
  const pollingRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      if (pollingRef.current) return;
      const workspacePath = getSelectedWorkspacePath();
      if (!workspacePath) return;
      pollingRef.current = true;
      try {
        await runPoll(workspacePath);
      } finally {
        pollingRef.current = false;
      }
    };

    const runPoll = async (workspacePath: string) => {
      // Reset baselines when the active workspace changes so we don't compare
      // statuses across unrelated batch sets.
      if (watchedWorkspaceRef.current !== workspacePath) {
        watchedWorkspaceRef.current = workspacePath;
        prevBatchStatusRef.current = {};
        prevTaskStatusRef.current = {};
      }

      let batches;
      try {
        const response = await batchesApi.list(workspacePath, { limit: 50 });
        batches = response.batches;
      } catch {
        // Transient API/network failure — keep baselines and retry next tick.
        return;
      }
      if (cancelled) return;

      const prevBatchStatus = prevBatchStatusRef.current;
      const prevTaskStatus = prevTaskStatusRef.current;

      for (const batch of batches) {
        // ── Batch terminal transition ──────────────────────────────────
        const prevStatus = prevBatchStatus[batch.id];
        if (
          prevStatus !== undefined &&
          !TERMINAL.includes(prevStatus) &&
          TERMINAL.includes(batch.status)
        ) {
          addRef.current({
            type: 'batch.completed',
            batchStatus: batch.status as AppNotificationBatchStatus,
            message: buildBatchMessage(batch.id, batch.status, batch.task_ids, batch.results),
            batchId: batch.id,
          });
        }
        prevBatchStatus[batch.id] = batch.status;

        // ── Per-task BLOCKED transition ────────────────────────────────
        for (const taskId of batch.task_ids) {
          const current = batch.results[taskId] ?? 'READY';
          const prev = prevTaskStatus[taskId];
          if (prev !== undefined && current === 'BLOCKED' && prev !== 'BLOCKED') {
            void notifyBlocked(workspacePath, taskId, addRef.current);
          }
          prevTaskStatus[taskId] = current;
        }
      }
    };

    // Poll immediately so a freshly-finished batch is reported without waiting
    // a full interval, then on a steady cadence.
    void poll();
    const timer = setInterval(poll, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);
}

function buildBatchMessage(
  batchId: string,
  status: string,
  taskIds: string[],
  results: Record<string, string>
): string {
  const completedCount = taskIds.filter(
    (id) => results[id] === 'COMPLETED' || results[id] === 'DONE'
  ).length;
  const total = taskIds.length;
  const shortId = batchId.slice(0, 8);
  if (status === 'COMPLETED') {
    return `Batch ${shortId} finished — ${completedCount}/${total} tasks done`;
  }
  if (status === 'FAILED') {
    return `Batch ${shortId} failed — ${completedCount}/${total} tasks completed before failure`;
  }
  return `Batch ${shortId} cancelled — ${completedCount}/${total} tasks completed`;
}

async function notifyBlocked(
  workspacePath: string,
  taskId: string,
  add: (input: AddNotificationInput) => void
): Promise<void> {
  let title: string | undefined;
  try {
    const task = await tasksApi.getOne(workspacePath, taskId);
    title = task.title;
  } catch {
    // Title is best-effort; fall back to a generic message.
  }
  add({
    type: 'blocker.created',
    message: title
      ? `Agent is blocked on "${title}" — your input needed`
      : 'Agent is blocked — your input needed',
    taskId,
  });
}
