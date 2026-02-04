'use client';

import { useState } from 'react';
import useSWR from 'swr';
import {
  WorkspaceHeader,
  WorkspaceStatsCards,
  QuickActions,
  RecentActivityFeed,
} from '@/components/workspace';
import { workspaceApi, tasksApi } from '@/lib/api';
import type {
  WorkspaceResponse,
  TaskListResponse,
  TaskStatusCounts,
  ActivityItem,
} from '@/types';

// Default empty task counts
const emptyTaskCounts: TaskStatusCounts = {
  BACKLOG: 0,
  READY: 0,
  IN_PROGRESS: 0,
  DONE: 0,
  BLOCKED: 0,
  FAILED: 0,
};

export default function WorkspacePage() {
  const [isInitializing, setIsInitializing] = useState(false);

  // Fetch workspace data
  const {
    data: workspace,
    error: workspaceError,
    isLoading: workspaceLoading,
    mutate: mutateWorkspace,
  } = useSWR<WorkspaceResponse>('/api/v2/workspaces/current', () =>
    workspaceApi.getCurrent()
  );

  // Fetch tasks data (only if workspace exists)
  const {
    data: tasksData,
    isLoading: tasksLoading,
  } = useSWR<TaskListResponse>(
    workspace ? '/api/v2/tasks' : null,
    () => tasksApi.getAll()
  );

  // Calculate active runs (tasks in IN_PROGRESS status)
  const activeRunCount = tasksData?.by_status?.IN_PROGRESS || 0;

  // Handle workspace initialization
  const handleInitialize = async () => {
    setIsInitializing(true);
    try {
      // Get current directory (would come from user input in real implementation)
      // For now, we'll use a placeholder that the server will resolve
      await workspaceApi.init('.', { detect: true });
      await mutateWorkspace();
    } catch (error) {
      console.error('Failed to initialize workspace:', error);
    } finally {
      setIsInitializing(false);
    }
  };

  // Determine if we're in a loading state
  const isLoading = workspaceLoading || tasksLoading;

  // Check if workspace doesn't exist (404 error)
  const workspaceNotFound =
    workspaceError?.status_code === 404 || !workspace;

  // Show loading skeleton
  if (workspaceLoading) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div data-testid="workspace-loading" className="animate-pulse">
            <div className="mb-8 h-8 w-48 rounded bg-muted" />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="h-32 rounded-xl bg-muted" />
              <div className="h-32 rounded-xl bg-muted" />
              <div className="h-32 rounded-xl bg-muted" />
            </div>
          </div>
        </div>
      </main>
    );
  }

  // Show error state for non-404 errors
  if (workspaceError && workspaceError.status_code !== 404) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border border-destructive bg-destructive/10 p-6">
            <h2 className="text-lg font-semibold text-destructive">Error</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {workspaceError.detail || 'Failed to load workspace'}
            </p>
          </div>
        </div>
      </main>
    );
  }

  // TODO: In future, fetch recent activity from an activity/events endpoint
  // For now, show empty state
  const activities: ActivityItem[] = [];

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <WorkspaceHeader
          workspace={workspaceNotFound ? null : workspace}
          isLoading={isInitializing}
          onInitialize={handleInitialize}
        />

        {!workspaceNotFound && (
          <>
            <WorkspaceStatsCards
              techStack={workspace?.tech_stack || null}
              taskCounts={tasksData?.by_status || emptyTaskCounts}
              activeRunCount={activeRunCount}
            />

            <QuickActions />

            <RecentActivityFeed activities={activities} />
          </>
        )}
      </div>
    </main>
  );
}
