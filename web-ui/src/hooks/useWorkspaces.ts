'use client';

import { useCallback, useMemo } from 'react';
import useSWR from 'swr';
import { workspaceApi } from '@/lib/api';
import {
  getRecentWorkspaces,
  setRecentWorkspaces,
  removeFromRecentWorkspaces,
  type RecentWorkspace,
} from '@/lib/workspace-storage';
import type { WorkspaceRegistryItem } from '@/types';

export const WORKSPACES_SWR_KEY = '/api/v2/workspaces';

export interface UseWorkspacesReturn {
  workspaces: WorkspaceRegistryItem[];
  isLoading: boolean;
  error: unknown;
  refresh: () => Promise<unknown>;
  removeWorkspace: (workspaceId: string) => Promise<void>;
}

/** Map server registry entries to the localStorage recents shape (mirror). */
function itemsToRecents(items: WorkspaceRegistryItem[]): RecentWorkspace[] {
  return items.map((item) => ({
    path: item.repo_path,
    name: item.name ?? item.repo_path.split(/[\\/]/).pop() ?? item.repo_path,
    lastUsed: item.last_opened_at ?? item.created_at ?? new Date(0).toISOString(),
  }));
}

/** Map localStorage recents back to registry items for the offline fallback. */
function recentsToItems(recents: RecentWorkspace[]): WorkspaceRegistryItem[] {
  return recents.map((recent) => ({
    // Offline entries have no server id; the path is a stable local key.
    id: recent.path,
    repo_path: recent.path,
    name: recent.name,
    tech_stack: null,
    created_at: null,
    last_opened_at: recent.lastUsed,
    // Optimistic: assume present; the server confirms once reachable.
    path_exists: true,
  }));
}

/**
 * Server-backed workspace list with a localStorage fallback (issue #601).
 *
 * - Fetches the registry from the server via SWR.
 * - On success, mirrors the list into localStorage so it survives offline.
 * - On fetch error (network/auth), falls back to the localStorage recents.
 */
export function useWorkspaces(): UseWorkspacesReturn {
  const { data, error, isLoading, mutate } = useSWR<WorkspaceRegistryItem[]>(
    WORKSPACES_SWR_KEY,
    () => workspaceApi.list(),
    {
      onSuccess: (items) => {
        setRecentWorkspaces(itemsToRecents(items));
      },
    }
  );

  const fallback = useMemo<WorkspaceRegistryItem[]>(
    // Recompute only when an error is present (offline/auth failure).
    () => (error ? recentsToItems(getRecentWorkspaces()) : []),
    [error]
  );

  const workspaces = data ?? (error ? fallback : []);

  const removeWorkspace = useCallback(
    async (workspaceId: string) => {
      await workspaceApi.remove(workspaceId);
      // Keep the localStorage mirror in sync by path.
      const removed = (data ?? []).find((w) => w.id === workspaceId);
      if (removed) {
        removeFromRecentWorkspaces(removed.repo_path);
      }
      await mutate();
    },
    [data, mutate]
  );

  const refresh = useCallback(() => mutate(), [mutate]);

  return {
    workspaces,
    isLoading,
    error,
    refresh,
    removeWorkspace,
  };
}
