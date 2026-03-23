'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import { prdApi, tasksApi, proofApi, reviewApi } from '@/lib/api';

export interface PhaseStatus {
  isComplete: boolean;
  isLoading: boolean;
}

export interface PipelineStatus {
  think: PhaseStatus;
  build: PhaseStatus;
  prove: PhaseStatus;
  ship: PhaseStatus;
}

/**
 * Aggregates pipeline phase completion from four existing API endpoints.
 * Returns null SWR keys when no workspace is selected, preventing fetches.
 */
export function usePipelineStatus(): PipelineStatus {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());

    const handleChange = () => setWorkspacePath(getSelectedWorkspacePath());
    window.addEventListener('storage', handleChange);
    window.addEventListener('workspaceChanged', handleChange);
    return () => {
      window.removeEventListener('storage', handleChange);
      window.removeEventListener('workspaceChanged', handleChange);
    };
  }, []);

  const { data: prdData, isLoading: prdLoading } = useSWR(
    workspacePath ? `/pipeline/prd?path=${workspacePath}` : null,
    () => prdApi.getLatest(workspacePath!),
    { revalidateOnFocus: false }
  );

  const { data: tasksData, isLoading: tasksLoading } = useSWR(
    workspacePath ? `/pipeline/tasks?path=${workspacePath}` : null,
    () => tasksApi.getAll(workspacePath!),
    { revalidateOnFocus: false }
  );

  const { data: proofData, isLoading: proofLoading } = useSWR(
    workspacePath ? `/pipeline/proof?path=${workspacePath}` : null,
    () => proofApi.getStatus(workspacePath!),
    { revalidateOnFocus: false }
  );

  const { data: reviewData, isLoading: reviewLoading } = useSWR(
    workspacePath ? `/pipeline/review?path=${workspacePath}` : null,
    () => reviewApi.getDiff(workspacePath!),
    { revalidateOnFocus: false }
  );

  const doneMerged = tasksData
    ? (tasksData.by_status.DONE ?? 0) + (tasksData.by_status.MERGED ?? 0)
    : 0;

  return {
    think: {
      isComplete: !!prdData,
      isLoading: prdLoading,
    },
    build: {
      isComplete: doneMerged > 0,
      isLoading: tasksLoading,
    },
    prove: {
      isComplete: !!proofData && proofData.total > 0 && proofData.open === 0,
      isLoading: proofLoading,
    },
    ship: {
      isComplete: !!reviewData && reviewData.files_changed === 0,
      isLoading: reviewLoading,
    },
  };
}
