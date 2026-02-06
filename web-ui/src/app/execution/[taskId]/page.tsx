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

  // Hydrate workspace path from localStorage
  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  // Fetch task details
  useEffect(() => {
    if (!workspacePath || !taskId) return;
    tasksApi.getOne(workspacePath, taskId).then(setTask).catch(() => {
      // Task not found — task may have been deleted
    });
  }, [workspacePath, taskId]);

  // Connect to SSE stream
  const monitor = useExecutionMonitor(workspaceReady && taskId ? taskId : null);

  // Stop handler
  const handleStop = useCallback(async () => {
    if (!workspacePath || !taskId) return;
    await tasksApi.stopExecution(workspacePath, taskId);
  }, [workspacePath, taskId]);

  // Re-fetch blocker list when a blocker is answered inline
  const handleBlockerAnswered = useCallback(() => {
    // After answering a blocker the SSE stream will resume automatically.
    // No extra action needed — the stream pushes new events.
  }, []);

  // ── Guards ──────────────────────────────────────────────────────────

  if (!workspaceReady) return null;

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
        <div className="flex flex-1 gap-4 overflow-hidden">
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
      <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-900 dark:bg-green-950/30">
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
      <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-900 dark:bg-red-950/30">
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
      <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/30">
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
