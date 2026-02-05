'use client';

import { FileEditIcon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PRDHeader } from './PRDHeader';
import type { PrdResponse, TaskStatusCounts } from '@/types';

interface PRDViewProps {
  prd: PrdResponse | null;
  taskCounts: TaskStatusCounts | null;
  isLoading: boolean;
  onUploadPrd: () => void;
  onStartDiscovery: () => void;
  onGenerateTasks: () => void;
}

export function PRDView({
  prd,
  taskCounts,
  isLoading,
  onUploadPrd,
  onStartDiscovery,
  onGenerateTasks,
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
  if (!prd) {
    return (
      <div className="space-y-6">
        <PRDHeader
          prd={null}
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

  // PRD exists — show header with actions + content preview
  return (
    <div className="space-y-6">
      <PRDHeader
        prd={prd}
        onUploadPrd={onUploadPrd}
        onStartDiscovery={onStartDiscovery}
        onGenerateTasks={onGenerateTasks}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            PRD Content
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Markdown editor will replace this in Step 4 */}
          <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm">
            {prd.content}
          </div>
        </CardContent>
      </Card>

      {/* Task summary will be built in Step 6 */}
      {taskCounts && (
        <div className="flex gap-2 text-xs text-muted-foreground">
          <span>READY: {taskCounts.READY}</span>
          <span>&middot;</span>
          <span>IN_PROGRESS: {taskCounts.IN_PROGRESS}</span>
          <span>&middot;</span>
          <span>DONE: {taskCounts.DONE}</span>
        </div>
      )}
    </div>
  );
}
