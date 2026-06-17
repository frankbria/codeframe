'use client';

import { useState, useEffect, useCallback } from 'react';
import { mutate as globalMutate } from 'swr';
import { WORKSPACES_SWR_KEY } from '@/hooks/useWorkspaces';
import { workspaceApi } from '@/lib/api';
import {
  getSelectedWorkspacePath,
  setSelectedWorkspacePath,
  clearSelectedWorkspacePath,
} from '@/lib/workspace-storage';
import type { ApiError, WorkspaceResponse } from '@/types';

interface SelectWorkspaceOptions {
  /**
   * Called after a *new* workspace is initialized (the path did not exist yet).
   * Lets a page react to the freshly created workspace — e.g. the home page
   * opens its tech-stack confirmation dialog.
   */
  onInitialized?: (workspace: WorkspaceResponse) => void;
}

export interface UseWorkspaceSelectionResult {
  /** The selected workspace path, or null when none is selected. */
  workspacePath: string | null;
  /** Imperatively set the path (e.g. after the home tech-stack flow). */
  setWorkspacePath: (path: string | null) => void;
  /**
   * True once the path has been hydrated from localStorage on mount. Pages
   * gate their no-workspace UI on this to avoid an SSR/client hydration
   * mismatch (localStorage is client-only).
   */
  workspaceReady: boolean;
  /** True while {@link selectWorkspace} is resolving. */
  isSelecting: boolean;
  /** Last selection error message, or null. */
  selectionError: string | null;
  /** Validate/initialize a workspace path, persist it, and select it. */
  selectWorkspace: (path: string, opts?: SelectWorkspaceOptions) => Promise<void>;
  /** Clear the current selection (returns the user to the selector). */
  clearWorkspace: () => void;
}

/**
 * Shared workspace-selection state for pages that require a workspace.
 *
 * Centralizes the "no workspace selected" flow so every page renders the same
 * {@link WorkspaceSelector} instead of bespoke link cards. Mirrors the original
 * per-page handlers: check existence, init with tech-stack detection when new,
 * persist to localStorage, and keep the server-backed workspace list fresh.
 */
export function useWorkspaceSelection(): UseWorkspaceSelectionResult {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  // Hydrate from localStorage on mount (client-only).
  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  const selectWorkspace = useCallback(
    async (path: string, opts?: SelectWorkspaceOptions) => {
      setIsSelecting(true);
      setSelectionError(null);

      try {
        const exists = await workspaceApi.checkExists(path);

        if (exists.exists) {
          // Touch /current so the server bumps recency — fire-and-forget so a
          // transient error on this best-effort call can't block opening an
          // accessible workspace.
          void workspaceApi.getByPath(path).catch(() => {});
          setSelectedWorkspacePath(path);
          setWorkspacePath(path);
        } else {
          const initialized = await workspaceApi.init(path, { detect: true });
          setSelectedWorkspacePath(path);
          setWorkspacePath(path);
          opts?.onInitialized?.(initialized);
        }

        // Keep the server-backed workspace list fresh (localStorage dual-write
        // already happened via setSelectedWorkspacePath).
        void globalMutate(WORKSPACES_SWR_KEY);
      } catch (error) {
        const apiError = error as ApiError;
        setSelectionError(apiError.detail || 'Failed to open project');
      } finally {
        setIsSelecting(false);
      }
    },
    []
  );

  const clearWorkspace = useCallback(() => {
    clearSelectedWorkspacePath();
    setWorkspacePath(null);
  }, []);

  return {
    workspacePath,
    setWorkspacePath,
    workspaceReady,
    isSelecting,
    selectionError,
    selectWorkspace,
    clearWorkspace,
  };
}
