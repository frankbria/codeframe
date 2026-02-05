'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import { PRDView } from '@/components/prd';
import { UploadPRDModal } from '@/components/prd/UploadPRDModal';
import { prdApi, tasksApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type {
  PrdResponse,
  TaskListResponse,
  ApiError,
} from '@/types';

export default function PrdPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
  }, []);

  // Fetch latest PRD
  const {
    data: prd,
    error: prdError,
    isLoading: prdLoading,
    mutate: mutatePrd,
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

  const handleUploadPrd = () => {
    setUploadModalOpen(true);
  };

  const handleUploadSuccess = (newPrd: PrdResponse) => {
    // Update SWR cache with the new PRD so UI reflects it immediately
    mutatePrd(newPrd, false);
  };

  const handleSavePrd = async (content: string, changeSummary: string) => {
    if (!prd || !workspacePath) return;
    setIsSaving(true);
    try {
      const updated = await prdApi.createVersion(
        prd.id,
        workspacePath,
        content,
        changeSummary
      );
      mutatePrd(updated, false);
    } finally {
      setIsSaving(false);
    }
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
          isSaving={isSaving}
          onUploadPrd={handleUploadPrd}
          onStartDiscovery={handleStartDiscovery}
          onGenerateTasks={handleGenerateTasks}
          onSavePrd={handleSavePrd}
        />

        <UploadPRDModal
          open={uploadModalOpen}
          onOpenChange={setUploadModalOpen}
          workspacePath={workspacePath}
          onSuccess={handleUploadSuccess}
        />
      </div>
    </main>
  );
}
