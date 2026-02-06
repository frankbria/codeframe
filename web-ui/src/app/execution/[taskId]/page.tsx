'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useExecutionMonitor } from '@/hooks/useExecutionMonitor';
import { tasksApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import { ExecutionHeader } from '@/components/execution/ExecutionHeader';
import { ProgressIndicator } from '@/components/execution/ProgressIndicator';
import { EventStream } from '@/components/execution/EventStream';
import { ChangesSidebar } from '@/components/execution/ChangesSidebar';
import type { Task } from '@/types';

export default function ExecutionPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const taskId = params.taskId;

  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [task, setTask] = useState<Task | null>(null);
  const [taskError, setTaskError] = useState(false);

  // Hydrate workspace path from localStorage
  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  // Fetch task details
  useEffect(() => {
    if (!workspacePath || !taskId) return;
    tasksApi.getOne(workspacePath, taskId).then(setTask).catch((err) => {
      console.error('Failed to load task:', err);
      setTaskError(true);
    });
  }, [workspacePath, taskId]);

  // Connect to SSE stream
  const monitor = useExecutionMonitor(
    workspaceReady && taskId ? taskId : null,
    workspacePath
  );

  // Stop handler — may fail if run already completed or no active run
  const handleStop = useCallback(async () => {
    if (!workspacePath || !taskId) return;
    try {
      await tasksApi.stopExecution(workspacePath, taskId);
    } catch (err) {
      const detail = (err as { detail?: string })?.detail ?? '';
      // 400/404 from stop is expected if run already completed
      if (!detail.includes('not found') && !detail.includes('Cannot stop')) {
        console.error('Failed to stop execution:', detail);
      }
    }
  }, [workspacePath, taskId]);

  // Re-fetch blocker list when a blocker is answered inline
  const handleBlockerAnswered = useCallback(() => {
    // After answering a blocker the SSE stream will resume automatically.
    // No extra action needed — the stream pushes new events.
  }, []);

  // ── Guards ──────────────────────────────────────────────────────────

  if (!workspaceReady) return null;

  if (taskError) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-500">
        <p>Task not found or failed to load.</p>
        <a href="/tasks" className="text-blue-600 hover:underline">Back to Task Board</a>
      </div>
    );
  }

  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected.{' '}
              <Link href="/" className="text-primary hover:underline">
                Select a workspace
              </Link>{' '}
              first.
            </p>
          </div>
        </div>
      </main>
    );
  }

  // ── Layout ──────────────────────────────────────────────────────────

  return (
    <main className="flex min-h-screen flex-col bg-background">
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-6">
        {/* Header: task info + agent state + stop button */}
        <ExecutionHeader
          task={task}
          agentState={monitor.agentState}
          sseStatus={monitor.sseStatus}
          onStop={handleStop}
          isCompleted={monitor.isCompleted}
        />

        {/* Progress bar */}
        <ProgressIndicator
          currentStep={monitor.currentStep}
          totalSteps={monitor.totalSteps}
          currentMessage={monitor.currentMessage}
          agentState={monitor.agentState}
        />

        {/* SSE disconnection banner */}
        {monitor.agentState === 'DISCONNECTED' && !monitor.isCompleted && (
          <div className="mx-4 mt-2 flex items-center justify-between rounded-md border border-yellow-200 bg-yellow-50 px-4 py-2 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300">
            <span>Connection lost. Events may be missing.</span>
            <button
              onClick={() => window.location.reload()}
              className="rounded px-3 py-1 text-xs font-medium bg-yellow-200 hover:bg-yellow-300 dark:bg-yellow-800 dark:hover:bg-yellow-700"
            >
              Reconnect
            </button>
          </div>
        )}

        {/* Completion banner */}
        {monitor.isCompleted && (
          <CompletionBanner
            status={monitor.completionStatus}
            duration={monitor.duration}
            onViewChanges={() => router.push('/review')}
            onBackToTasks={() => router.push('/tasks')}
          />
        )}

        {/* Main content: event stream + changes sidebar */}
        <div className="flex flex-1 flex-col gap-4 overflow-hidden md:flex-row">
          <EventStream
            events={monitor.events}
            workspacePath={workspacePath}
            onBlockerAnswered={handleBlockerAnswered}
          />
          <ChangesSidebar changedFiles={monitor.changedFiles} />
        </div>
      </div>
    </main>
  );
}

// ── Completion Banner ─────────────────────────────────────────────────

function CompletionBanner({
  status,
  duration,
  onViewChanges,
  onBackToTasks,
}: {
  status: 'completed' | 'failed' | 'blocked' | null;
  duration: number | null;
  onViewChanges: () => void;
  onBackToTasks: () => void;
}) {
  const durationText = duration !== null ? `${Math.round(duration)}s` : '';

  if (status === 'completed') {
    return (
      <div role="alert" className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-900 dark:bg-green-950/30">
        <p className="text-sm font-medium text-green-800 dark:text-green-200">
          Execution completed successfully{durationText && ` in ${durationText}`}.
        </p>
        <div className="flex gap-2">
          <button
            onClick={onViewChanges}
            className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
          >
            View Changes
          </button>
          <button
            onClick={onBackToTasks}
            className="rounded-md border border-green-300 px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-100 dark:border-green-800 dark:text-green-300 dark:hover:bg-green-900/40"
          >
            Back to Tasks
          </button>
        </div>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div role="alert" className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900 dark:bg-red-950/30">
        <p className="text-sm font-medium text-red-800 dark:text-red-200">
          Execution failed{durationText && ` after ${durationText}`}. Check the
          event stream for details.
        </p>
        <button
          onClick={onBackToTasks}
          className="rounded-md border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-900/40"
        >
          Back to Tasks
        </button>
      </div>
    );
  }

  if (status === 'blocked') {
    return (
      <div role="alert" className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/30">
        <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
          Execution blocked — a blocker was raised. Answer it in the event
          stream below to continue.
        </p>
        <button
          onClick={onBackToTasks}
          className="rounded-md border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 dark:border-amber-800 dark:text-amber-300 dark:hover:bg-amber-900/40"
        >
          Back to Tasks
        </button>
      </div>
    );
  }

  return null;
}
