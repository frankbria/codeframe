'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useExecutionMonitor } from '@/hooks/useExecutionMonitor';
import { tasksApi, gatesApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import { ExecutionHeader } from '@/components/execution/ExecutionHeader';
import { ProgressIndicator } from '@/components/execution/ProgressIndicator';
import { EventStream } from '@/components/execution/EventStream';
import { ChangesSidebar } from '@/components/execution/ChangesSidebar';
import { Button } from '@/components/ui/button';
import type { Task, CompletionBannerProps, GateResult } from '@/types';

export default function ExecutionPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const taskId = params.taskId;

  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [task, setTask] = useState<Task | null>(null);
  const [taskError, setTaskError] = useState(false);

  // Gate auto-run state
  const [gateResult, setGateResult] = useState<GateResult | null>(null);
  const [gateRunning, setGateRunning] = useState(false);
  const [gateError, setGateError] = useState(false);
  const hasRunGatesRef = useRef(false);

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

  // Auto-run gates non-blocking when execution completes
  useEffect(() => {
    if (monitor.completionStatus !== 'completed' || !workspacePath || hasRunGatesRef.current) return;
    hasRunGatesRef.current = true;
    setGateRunning(true);
    gatesApi.run(workspacePath)
      .then(setGateResult)
      .catch(() => setGateError(true))
      .finally(() => setGateRunning(false));
  }, [monitor.completionStatus, workspacePath]);

  // Derive pending state immediately on first completed render (before effect commits)
  const showGatePending =
    monitor.completionStatus === 'completed' && !gateResult && !gateError;

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
            onViewProof={() => router.push('/proof')}
            onViewChanges={() => router.push('/review')}
            onBackToTasks={() => router.push('/tasks')}
            onViewBlockers={() => router.push('/blockers')}
            gateResult={gateResult}
            gateRunning={gateRunning || showGatePending}
            gateError={gateError}
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

function GateSummary({
  gateRunning,
  gateResult,
  gateError,
}: {
  gateRunning: boolean;
  gateResult: CompletionBannerProps['gateResult'];
  gateError: boolean;
}) {
  if (gateRunning) {
    return (
      <p className="mt-2 text-xs text-green-700 dark:text-green-300">
        Running quality gates…
      </p>
    );
  }
  if (gateError) {
    return (
      <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
        Gate check unavailable ·{' '}
        <Link href="/review" className="underline hover:no-underline">View in Review →</Link>
      </p>
    );
  }
  if (gateResult) {
    const total = gateResult.checks.length;
    const passed = gateResult.checks.filter((c) => c.status === 'PASSED').length;
    if (gateResult.passed) {
      return (
        <p className="mt-2 text-xs text-green-700 dark:text-green-300">
          ✓ All {total} gate{total !== 1 ? 's' : ''} passed
        </p>
      );
    }
    return (
      <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
        ⚠ {passed}/{total} gates passed ·{' '}
        <Link href="/review" className="underline hover:no-underline">View full report →</Link>
      </p>
    );
  }
  return null;
}

function CompletionBanner({
  status,
  duration,
  onViewProof,
  onViewChanges,
  onBackToTasks,
  onViewBlockers,
  gateResult,
  gateRunning = false,
  gateError = false,
}: CompletionBannerProps) {
  const durationText = duration !== null ? `${Math.round(duration)}s` : '';

  if (status === 'completed') {
    return (
      <div role="alert" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 dark:border-green-900 dark:bg-green-950/30">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-green-800 dark:text-green-200">
            Execution complete{durationText && ` in ${durationText}`}. Run PROOF9 gates to verify quality before shipping.
          </p>
          <div className="flex gap-2">
            <Button onClick={onViewProof} size="sm">
              Verify with PROOF9
            </Button>
            <Button onClick={onViewChanges} variant="outline" size="sm">
              View Changes
            </Button>
            <Button onClick={onBackToTasks} variant="outline" size="sm">
              Back to Tasks
            </Button>
          </div>
        </div>
        <GateSummary gateRunning={gateRunning} gateResult={gateResult} gateError={gateError} />
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
        <Button onClick={onBackToTasks} variant="outline" size="sm">
          Back to Tasks
        </Button>
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
        <div className="flex gap-2">
          <Button onClick={onViewBlockers} size="sm">
            View Blockers
          </Button>
          <Button onClick={onBackToTasks} variant="outline" size="sm">
            Back to Tasks
          </Button>
        </div>
      </div>
    );
  }

  return null;
}
