/**
 * Workspace path storage and management
 *
 * Handles persistence of workspace paths in localStorage for the web UI.
 * The CLI knows context from current directory, but the web UI needs
 * explicit workspace selection.
 */

const STORAGE_KEY = 'codeframe_workspace_path';
const RECENT_WORKSPACES_KEY = 'codeframe_recent_workspaces';
const MAX_RECENT_WORKSPACES = 10;

export interface RecentWorkspace {
  path: string;
  name: string; // Last segment of path for display
  lastUsed: string; // ISO timestamp
}

/**
 * Get the currently selected workspace path
 */
export function getSelectedWorkspacePath(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEY);
}

/**
 * Set the selected workspace path
 */
export function setSelectedWorkspacePath(path: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, path);
  addToRecentWorkspaces(path);
}

/**
 * Clear the selected workspace path
 */
export function clearSelectedWorkspacePath(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(STORAGE_KEY);
}

/**
 * Get list of recently used workspaces
 */
export function getRecentWorkspaces(): RecentWorkspace[] {
  if (typeof window === 'undefined') return [];
  const stored = localStorage.getItem(RECENT_WORKSPACES_KEY);
  if (!stored) return [];
  try {
    return JSON.parse(stored);
  } catch {
    return [];
  }
}

/**
 * Add a workspace to the recent list
 */
export function addToRecentWorkspaces(path: string): void {
  if (typeof window === 'undefined') return;

  const recent = getRecentWorkspaces();
  const name = path.split('/').pop() || path;

  // Remove existing entry for this path
  const filtered = recent.filter(w => w.path !== path);

  // Add to front of list
  const updated: RecentWorkspace[] = [
    { path, name, lastUsed: new Date().toISOString() },
    ...filtered,
  ].slice(0, MAX_RECENT_WORKSPACES);

  localStorage.setItem(RECENT_WORKSPACES_KEY, JSON.stringify(updated));
}

/**
 * Remove a workspace from the recent list
 */
export function removeFromRecentWorkspaces(path: string): void {
  if (typeof window === 'undefined') return;

  const recent = getRecentWorkspaces();
  const filtered = recent.filter(w => w.path !== path);
  localStorage.setItem(RECENT_WORKSPACES_KEY, JSON.stringify(filtered));
}
