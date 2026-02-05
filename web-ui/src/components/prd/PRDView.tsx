'use client';

import { FileEditIcon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { PRDHeader } from './PRDHeader';
import { MarkdownEditor } from './MarkdownEditor';
import { DiscoveryPanel } from './DiscoveryPanel';
import { AssociatedTasksSummary } from './AssociatedTasksSummary';
import type { PrdResponse, TaskStatusCounts } from '@/types';

interface PRDViewProps {
  prd: PrdResponse | null;
  taskCounts: TaskStatusCounts | null;
  isLoading: boolean;
  isSaving?: boolean;
  isGeneratingTasks?: boolean;
  discoveryOpen: boolean;
  workspacePath: string | null;
  onUploadPrd: () => void;
  onStartDiscovery: () => void;
  onCloseDiscovery: () => void;
  onGenerateTasks: () => void;
  onSavePrd?: (content: string, changeSummary: string) => Promise<void>;
  onPrdGenerated: (prd: PrdResponse) => void;
}

export function PRDView({
  prd,
  taskCounts,
  isLoading,
  isSaving = false,
  isGeneratingTasks = false,
  discoveryOpen,
  workspacePath,
  onUploadPrd,
  onStartDiscovery,
  onCloseDiscovery,
  onGenerateTasks,
  onSavePrd,
  onPrdGenerated,
}: PRDViewProps) {
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="mb-4 h-8 w-64 rounded bg-muted" />
          <div className="h-64 rounded-xl bg-muted" />
        </div>
      </div>
    );
  }

  // Empty state — no PRD yet
  if (!prd && !discoveryOpen) {
    return (
      <div className="space-y-6">
        <PRDHeader
          prd={null}
          isGeneratingTasks={isGeneratingTasks}
          onUploadPrd={onUploadPrd}
          onStartDiscovery={onStartDiscovery}
          onGenerateTasks={onGenerateTasks}
        />

        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <FileEditIcon className="mb-4 h-12 w-12 text-muted-foreground/50" />
            <h3 className="text-lg font-semibold">No PRD yet</h3>
            <p className="mt-1 max-w-sm text-center text-sm text-muted-foreground">
              Upload a PRD document or start an AI-powered discovery session to
              create one.
            </p>
            <div className="mt-6 flex gap-3">
              <Button variant="outline" onClick={onUploadPrd}>
                Upload PRD
              </Button>
              <Button onClick={onStartDiscovery}>
                Start Discovery
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Two-column layout when discovery is open, single column otherwise
  return (
    <div className="space-y-6">
      <PRDHeader
        prd={prd}
        isGeneratingTasks={isGeneratingTasks}
        onUploadPrd={onUploadPrd}
        onStartDiscovery={onStartDiscovery}
        onGenerateTasks={onGenerateTasks}
      />

      <div
        className={`grid gap-4 ${
          discoveryOpen ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'
        }`}
      >
        {/* Left: editor (or empty placeholder when no PRD during discovery) */}
        <Card>
          <CardContent className="pt-6">
            {prd ? (
              <MarkdownEditor
                content={prd.content}
                onSave={onSavePrd ?? (async () => {})}
                isSaving={isSaving}
              />
            ) : (
              <div className="flex min-h-[400px] items-center justify-center text-sm text-muted-foreground">
                PRD will appear here after discovery completes.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Right: discovery panel */}
        {discoveryOpen && workspacePath && (
          <div className="min-h-[500px]">
            <DiscoveryPanel
              workspacePath={workspacePath}
              onClose={onCloseDiscovery}
              onPrdGenerated={onPrdGenerated}
            />
          </div>
        )}
      </div>

      {taskCounts && (
        <AssociatedTasksSummary taskCounts={taskCounts} />
      )}
    </div>
  );
}
