'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { BlockerResolutionView } from '@/components/blockers/BlockerResolutionView';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';

export default function BlockersPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  // Still hydrating — avoid flashing "No workspace selected"
  if (!workspaceReady) {
    return null;
  }

  // No workspace selected
  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected. Use the sidebar to return to{' '}
              <Link href="/" className="text-primary hover:underline">
                Workspace
              </Link>{' '}
              and select a project.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <BlockerResolutionView workspacePath={workspacePath} />
      </div>
    </main>
  );
}
