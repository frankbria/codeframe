'use client';

import { useCallback, useMemo, useState } from 'react';
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

/**
 * Merge the server list into the existing localStorage recents without losing
 * local-only entries (e.g. projects opened before the registry existed, or only
 * known to this browser). Server entries win for overlapping paths and keep
 * their recency order; local-only recents are appended.
 */
function mergeRecents(
  serverItems: WorkspaceRegistryItem[],
  existing: RecentWorkspace[]
): RecentWorkspace[] {
  const serverRecents = itemsToRecents(serverItems);
  const serverPaths = new Set(serverRecents.map((r) => r.path));
  const localOnly = existing.filter((r) => !serverPaths.has(r.path));
  return [...serverRecents, ...localOnly];
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
  // Bumped after a local-only (offline) removal so the fallback list re-renders.
  const [localVersion, setLocalVersion] = useState(0);

  const { data, error, isLoading, mutate } = useSWR<WorkspaceRegistryItem[]>(
    WORKSPACES_SWR_KEY,
    () => workspaceApi.list(),
    {
      onSuccess: (items) => {
        // Merge (never clobber) so local-only recents survive as offline fallback.
        setRecentWorkspaces(mergeRecents(items, getRecentWorkspaces()));
      },
    }
  );

  const fallback = useMemo<WorkspaceRegistryItem[]>(() => {
    // Referenced so this recomputes after a local-only removal bumps it.
    void localVersion;
    // Offline/error fallback only.
    return error ? recentsToItems(getRecentWorkspaces()) : [];
  }, [error, localVersion]);

  // Online: the server list is authoritative — we do NOT append browser-only
  // recents here. Doing so would resurrect entries another device deregistered
  // (the local mirror can't tell "never registered" from "deleted elsewhere").
  // Local-only projects remain reachable via the "Open Project" path input,
  // which auto-registers them server-side on open. localStorage stays a faithful
  // mirror so the offline fallback still shows full history.
  const workspaces = data ?? fallback;

  const removeWorkspace = useCallback(
    async (workspaceId: string) => {
      // Server-backed entry: deregister on the server, then sync the local mirror.
      const serverEntry = (data ?? []).find((w) => w.id === workspaceId);
      if (serverEntry) {
        await workspaceApi.remove(workspaceId);
        removeFromRecentWorkspaces(serverEntry.repo_path);
        await mutate();
        return;
      }

      // Fallback (offline) entry: its id IS the filesystem path. Remove it from
      // localStorage directly — calling the unreachable server would only fail
      // and strand the stale entry in the list.
      removeFromRecentWorkspaces(workspaceId);
      setLocalVersion((v) => v + 1);
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
