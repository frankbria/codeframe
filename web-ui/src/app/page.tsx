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
import { workspaceApi, tasksApi, eventsApi } from '@/lib/api';
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
  ActivityType,
  EventListResponse,
  EventResponse,
  ApiError,
} from '@/types';

// Default empty task counts (must match TaskStatusCounts interface)
const emptyTaskCounts: TaskStatusCounts = {
  BACKLOG: 0,
  READY: 0,
  IN_PROGRESS: 0,
  DONE: 0,
  BLOCKED: 0,
  FAILED: 0,
  MERGED: 0,
};

// Map backend event types to UI activity types
// Backend uses uppercase constants from codeframe.core.events.EventType
const EVENT_TYPE_MAP: Record<string, ActivityType> = {
  // Task events
  'TASK_STATUS_CHANGED': 'task_completed',
  'RUN_COMPLETED': 'task_completed',
  'BATCH_TASK_COMPLETED': 'task_completed',
  // Run events
  'RUN_STARTED': 'run_started',
  'BATCH_STARTED': 'run_started',
  'BATCH_TASK_STARTED': 'run_started',
  // Blocker events
  'BLOCKER_CREATED': 'blocker_raised',
  'BATCH_TASK_BLOCKED': 'blocker_raised',
  // Workspace events
  'WORKSPACE_INIT': 'workspace_initialized',
  // PRD events
  'PRD_ADDED': 'prd_added',
  'PRD_UPDATED': 'prd_added',
};

// Safely extract string from unknown payload field
function safeString(value: unknown): string | null {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return null;
}

// Convert EventResponse to ActivityItem
function mapEventToActivity(event: EventResponse): ActivityItem {
  const activityType = EVENT_TYPE_MAP[event.event_type] || 'task_completed';
  const payload = event.payload || {};

  // Build description from payload or event type with runtime type checks
  let description = safeString(payload.description) ||
                    safeString(payload.message) ||
                    event.event_type.replace(/[._]/g, ' ');

  // Add task/blocker context if available (with type check)
  const taskTitle = safeString(payload.task_title);
  if (taskTitle) {
    description = `${taskTitle}: ${description}`;
  }

  return {
    id: String(event.id),
    type: activityType,
    timestamp: event.created_at,
    description,
    metadata: payload,
  };
}

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

  // Fetch recent events for activity feed (only if workspace exists)
  const { data: eventsData } = useSWR<EventListResponse>(
    workspace && workspacePath ? `/api/v2/events?path=${workspacePath}` : null,
    () => eventsApi.getRecent(workspacePath!, { limit: 5 })
  );

  // Calculate active runs (tasks in IN_PROGRESS status)
  const activeRunCount = tasksData?.by_status?.IN_PROGRESS || 0;

  // Map events to activity items
  const activities: ActivityItem[] = (eventsData?.events || []).map(mapEventToActivity);

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
