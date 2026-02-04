'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import {
  WorkspaceHeader,
  WorkspaceStatsCards,
  QuickActions,
  RecentActivityFeed,
} from '@/components/workspace';
import { WorkspaceSelector } from '@/components/workspace/WorkspaceSelector';
import { workspaceApi, tasksApi } from '@/lib/api';
import {
  getSelectedWorkspacePath,
  setSelectedWorkspacePath,
  clearSelectedWorkspacePath,
} from '@/lib/workspace-storage';
import type {
  WorkspaceResponse,
  TaskListResponse,
  TaskStatusCounts,
  ActivityItem,
  ApiError,
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
  // Track the selected workspace path
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [isSelectingWorkspace, setIsSelectingWorkspace] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  // Load workspace path from localStorage on mount
  useEffect(() => {
    const stored = getSelectedWorkspacePath();
    setWorkspacePath(stored);
  }, []);

  // Fetch workspace data (only if we have a path)
  const {
    data: workspace,
    error: workspaceError,
    isLoading: workspaceLoading,
    mutate: mutateWorkspace,
  } = useSWR<WorkspaceResponse, ApiError>(
    workspacePath ? `/api/v2/workspaces/current?path=${workspacePath}` : null,
    () => workspaceApi.getByPath(workspacePath!)
  );

  // Fetch tasks data (only if workspace exists)
  const { data: tasksData } = useSWR<TaskListResponse>(
    workspace && workspacePath ? `/api/v2/tasks?path=${workspacePath}` : null,
    () => tasksApi.getAll(workspacePath!)
  );

  // Calculate active runs (tasks in IN_PROGRESS status)
  const activeRunCount = tasksData?.by_status?.IN_PROGRESS || 0;

  // Handle workspace selection/initialization
  const handleSelectWorkspace = async (path: string) => {
    setIsSelectingWorkspace(true);
    setSelectionError(null);

    try {
      // First check if workspace exists
      const exists = await workspaceApi.checkExists(path);

      if (exists.exists) {
        // Workspace exists, just select it
        setSelectedWorkspacePath(path);
        setWorkspacePath(path);
      } else {
        // Initialize new workspace
        await workspaceApi.init(path, { detect: true });
        setSelectedWorkspacePath(path);
        setWorkspacePath(path);
      }
    } catch (error) {
      const apiError = error as ApiError;
      setSelectionError(apiError.detail || 'Failed to open project');
    } finally {
      setIsSelectingWorkspace(false);
    }
  };

  // Handle switching to a different workspace
  const handleSwitchWorkspace = () => {
    clearSelectedWorkspacePath();
    setWorkspacePath(null);
  };

  // Show workspace selector if no path selected
  if (!workspacePath) {
    return (
      <WorkspaceSelector
        onSelectWorkspace={handleSelectWorkspace}
        isLoading={isSelectingWorkspace}
        error={selectionError}
      />
    );
  }

  // Show loading skeleton while fetching workspace
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

  // Show error state for API errors (but not 404 - that means workspace needs init)
  if (workspaceError && workspaceError.status_code !== 404) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border border-destructive bg-destructive/10 p-6">
            <h2 className="text-lg font-semibold text-destructive">Error</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {workspaceError.detail || 'Failed to load workspace'}
            </p>
            <button
              onClick={handleSwitchWorkspace}
              className="mt-4 text-sm text-primary hover:underline"
            >
              ← Select a different project
            </button>
          </div>
        </div>
      </main>
    );
  }

  // Check if workspace needs initialization
  const workspaceNotFound = workspaceError?.status_code === 404 || !workspace;

  // Handle workspace initialization from the header
  const handleInitialize = async () => {
    if (!workspacePath) return;
    try {
      await workspaceApi.init(workspacePath, { detect: true });
      await mutateWorkspace();
    } catch (error) {
      console.error('Failed to initialize workspace:', error);
    }
  };

  // TODO: In future, fetch recent activity from an activity/events endpoint
  const activities: ActivityItem[] = [];

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        {/* Switch workspace link */}
        <div className="mb-4">
          <button
            onClick={handleSwitchWorkspace}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ← Switch project
          </button>
        </div>

        <WorkspaceHeader
          workspace={workspaceNotFound ? null : workspace}
          isLoading={false}
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
