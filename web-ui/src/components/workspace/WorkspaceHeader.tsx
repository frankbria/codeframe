'use client';

import { Folder01Icon, Loading03Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import type { WorkspaceResponse } from '@/types';

interface WorkspaceHeaderProps {
  workspace: WorkspaceResponse | null;
  isLoading: boolean;
  onInitialize: () => Promise<void>;
}

export function WorkspaceHeader({
  workspace,
  isLoading,
  onInitialize,
}: WorkspaceHeaderProps) {
  // Extract repo name from path
  const repoName = workspace?.repo_path?.split('/').pop() || '';

  return (
    <header className="mb-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">CodeFRAME</h1>
          {workspace && (
            <>
              <span className="text-muted-foreground">/</span>
              <div className="flex items-center gap-2 text-muted-foreground">
                <Folder01Icon className="h-5 w-5" />
                <span className="font-medium">{repoName}</span>
              </div>
            </>
          )}
        </div>
      </div>

      {!workspace && (
        <div className="mt-6 rounded-lg border bg-muted/50 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">No workspace initialized</h2>
              <p className="text-sm text-muted-foreground">
                Initialize a workspace to start using CodeFRAME in your project.
              </p>
            </div>
            <Button onClick={onInitialize} disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loading03Icon className="mr-2 h-4 w-4 animate-spin" />
                  Initializing...
                </>
              ) : (
                'Initialize Workspace'
              )}
            </Button>
          </div>
        </div>
      )}
    </header>
  );
}
