'use client';

import { useState } from 'react';
import {
  Folder01Icon,
  Time01Icon,
  Cancel01Icon,
  Loading03Icon,
  Alert02Icon,
} from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { formatDistanceToNow } from 'date-fns';

interface WorkspaceSelectorProps {
  onSelectWorkspace: (path: string) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

/**
 * WorkspaceSelector - First screen for selecting which project to work with
 *
 * The web UI has no concept of "current directory" like the CLI does.
 * Users must explicitly select which repository/project they want to manage.
 */
export function WorkspaceSelector({
  onSelectWorkspace,
  isLoading,
  error,
}: WorkspaceSelectorProps) {
  const [inputPath, setInputPath] = useState('');
  // Server-backed workspace list with localStorage fallback (issue #601).
  const {
    workspaces: recentWorkspaces,
    isLoading: workspacesLoading,
    removeWorkspace,
  } = useWorkspaces();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputPath.trim()) return;
    await onSelectWorkspace(inputPath.trim());
  };

  const handleSelectRecent = async (path: string) => {
    await onSelectWorkspace(path);
  };

  const handleRemoveRecent = async (workspaceId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await removeWorkspace(workspaceId);
    } catch {
      // Best-effort: a failed deregister leaves the list unchanged.
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-2xl space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold tracking-tight">CodeFRAME</h1>
          <p className="mt-2 text-muted-foreground">
            Select a project to get started
          </p>
        </div>

        {/* Path Input Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Folder01Icon className="h-5 w-5" />
              Open Project
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label
                  htmlFor="workspace-path"
                  className="block text-sm font-medium mb-2"
                >
                  Repository Path
                </label>
                <input
                  id="workspace-path"
                  type="text"
                  value={inputPath}
                  onChange={(e) => setInputPath(e.target.value)}
                  placeholder="/home/user/projects/my-app"
                  className="w-full px-3 py-2 border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  disabled={isLoading}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Enter the full path to your project directory
                </p>
              </div>

              {error && (
                <div className="p-3 rounded-md bg-destructive/10 border border-destructive text-destructive text-sm">
                  {error}
                </div>
              )}

              <Button type="submit" disabled={isLoading || !inputPath.trim()}>
                {isLoading ? (
                  <>
                    <Loading03Icon className="mr-2 h-4 w-4 animate-spin" />
                    Opening...
                  </>
                ) : (
                  'Open Project'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Recent Workspaces */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Time01Icon className="h-5 w-5" />
              Recent Projects
            </CardTitle>
          </CardHeader>
          <CardContent>
            {workspacesLoading && recentWorkspaces.length === 0 ? (
              <div
                data-testid="workspaces-loading"
                className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground"
              >
                <Loading03Icon className="h-4 w-4 animate-spin" />
                Loading projects…
              </div>
            ) : recentWorkspaces.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No recent projects. Open a project above to get started.
              </p>
            ) : (
              <ul className="space-y-2">
                {recentWorkspaces.map((workspace) => {
                  const displayName =
                    workspace.name ?? workspace.repo_path.split(/[\\/]/).pop() ?? workspace.repo_path;
                  const isStale = workspace.path_exists === false;
                  return (
                  <li key={workspace.id}>
                    <div
                      role="button"
                      tabIndex={isLoading ? -1 : 0}
                      onClick={() => !isLoading && handleSelectRecent(workspace.repo_path)}
                      onKeyDown={(e) => {
                        if (e.target !== e.currentTarget) return;
                        if ((e.key === 'Enter' || e.key === ' ') && !isLoading) {
                          e.preventDefault();
                          handleSelectRecent(workspace.repo_path);
                        }
                      }}
                      className={`w-full flex items-center justify-between p-3 rounded-md border hover:bg-accent transition-colors text-left cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring aria-disabled:opacity-50 aria-disabled:cursor-not-allowed${
                        isStale ? ' opacity-60' : ''
                      }`}
                      aria-disabled={isLoading}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Folder01Icon className="h-5 w-5 flex-shrink-0 text-muted-foreground" />
                        <div className="min-w-0">
                          <p className="font-medium truncate flex items-center gap-1.5">
                            {displayName}
                            {isStale && (
                              <span
                                className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground"
                                title="This path no longer exists on disk"
                              >
                                <Alert02Icon className="h-3 w-3" />
                                Missing
                              </span>
                            )}
                          </p>
                          <p className="text-xs text-muted-foreground truncate">
                            {workspace.repo_path}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                        {workspace.last_opened_at && (
                          <span className="text-xs text-muted-foreground">
                            {formatDistanceToNow(new Date(workspace.last_opened_at), {
                              addSuffix: true,
                            })}
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={(e) => handleRemoveRecent(workspace.id, e)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
                          }}
                          className="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive focus:outline-none focus:ring-2 focus:ring-ring"
                          title="Remove from recent"
                          aria-label={`Remove ${displayName} from recent projects`}
                        >
                          <Cancel01Icon className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        {/* Help text */}
        <p className="text-center text-sm text-muted-foreground">
          CodeFRAME will initialize a <code className="px-1 py-0.5 rounded bg-muted">.codeframe</code> directory
          in your project to store workspace state.
        </p>
      </div>
    </div>
  );
}
