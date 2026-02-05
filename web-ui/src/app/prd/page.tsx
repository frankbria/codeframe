'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import { PRDView } from '@/components/prd';
import { prdApi, tasksApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type {
  PrdResponse,
  TaskListResponse,
  ApiError,
} from '@/types';

export default function PrdPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
  }, []);

  // Fetch latest PRD
  const {
    data: prd,
    error: prdError,
    isLoading: prdLoading,
  } = useSWR<PrdResponse, ApiError>(
    workspacePath ? `/api/v2/prd/latest?path=${workspacePath}` : null,
    () => prdApi.getLatest(workspacePath!)
  );

  // Fetch task counts (to show summary)
  const { data: tasksData } = useSWR<TaskListResponse>(
    workspacePath ? `/api/v2/tasks?path=${workspacePath}` : null,
    () => tasksApi.getAll(workspacePath!)
  );

  // No workspace selected
  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected.{' '}
              <a href="/" className="text-primary hover:underline">
                Select a project
              </a>{' '}
              first.
            </p>
          </div>
        </div>
      </main>
    );
  }

  // Treat 404 as "no PRD yet" (not an error)
  const hasPrd = prd && !prdError;
  const isError = prdError && prdError.status_code !== 404;

  if (isError) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border border-destructive bg-destructive/10 p-6">
            <h2 className="text-lg font-semibold text-destructive">Error</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {prdError.detail || 'Failed to load PRD'}
            </p>
          </div>
        </div>
      </main>
    );
  }

  // Action stubs — these will be wired up in later steps
  const handleUploadPrd = () => {
    // Step 3: UploadPRDModal
    console.log('[PRD] Upload PRD clicked');
  };

  const handleStartDiscovery = () => {
    // Step 5: DiscoveryPanel
    console.log('[PRD] Start Discovery clicked');
  };

  const handleGenerateTasks = () => {
    // Step 6: Task generation
    console.log('[PRD] Generate Tasks clicked');
  };

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-4">
          <a
            href="/"
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; Workspace
          </a>
        </div>

        <PRDView
          prd={hasPrd ? prd : null}
          taskCounts={tasksData?.by_status ?? null}
          isLoading={prdLoading}
          onUploadPrd={handleUploadPrd}
          onStartDiscovery={handleStartDiscovery}
          onGenerateTasks={handleGenerateTasks}
        />
      </div>
    </main>
  );
}
