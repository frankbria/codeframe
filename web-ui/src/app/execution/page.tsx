'use client';

import { Suspense, useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Loading03Icon } from '@hugeicons/react';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import { tasksApi } from '@/lib/api';
import { BatchExecutionMonitor } from '@/components/execution/BatchExecutionMonitor';

/**
 * Execution landing page wrapper.
 *
 * Wraps the main content in `<Suspense>` because `useSearchParams()`
 * triggers a client-side rendering bailout in Next.js App Router.
 */
export default function ExecutionLandingPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-background">
          <Loading03Icon className="h-6 w-6 animate-spin text-muted-foreground" />
        </main>
      }
    >
      <ExecutionLandingContent />
    </Suspense>
  );
}

/**
 * Inner content that reads search params.
 *
 * Routing logic:
 * - `?batch=<id>` → renders BatchExecutionMonitor
 * - `?task=<id>`  → redirects to /execution/[taskId]
 * - No params     → finds latest IN_PROGRESS task and redirects, or shows empty state
 */
function ExecutionLandingContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const batchId = searchParams.get('batch');
  const taskIdParam = searchParams.get('task');

  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [resolving, setResolving] = useState(true);

  // Hydrate workspace path
  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  // If ?task= is present, redirect immediately
  useEffect(() => {
    if (taskIdParam) {
      router.replace(`/execution/${taskIdParam}`);
    }
  }, [taskIdParam, router]);

  // If no batch and no task param, find latest IN_PROGRESS task
  useEffect(() => {
    if (batchId || taskIdParam || !workspacePath) {
      setResolving(false);
      return;
    }

    tasksApi
      .getAll(workspacePath, 'IN_PROGRESS')
      .then((response) => {
        const tasks = response.tasks ?? [];
        if (tasks.length > 0) {
          router.replace(`/execution/${tasks[0].id}`);
        } else {
          setResolving(false);
        }
      })
      .catch(() => {
        setResolving(false);
      });
  }, [workspacePath, batchId, taskIdParam, router]);

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

  // Redirecting to single-task page
  if (taskIdParam || resolving) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <Loading03Icon className="h-6 w-6 animate-spin text-muted-foreground" />
      </main>
    );
  }

  // Batch mode
  if (batchId) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-6">
          <BatchExecutionMonitor
            batchId={batchId}
            workspacePath={workspacePath}
          />
        </div>
      </main>
    );
  }

  // No active execution — empty state
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl px-4 py-8">
        <div className="rounded-lg border bg-muted/50 p-8 text-center">
          <p className="text-lg font-medium text-foreground">
            No active execution
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Start an execution from the{' '}
            <Link href="/tasks" className="text-primary hover:underline">
              Task Board
            </Link>
            .
          </p>
        </div>
      </div>
    </main>
  );
}
