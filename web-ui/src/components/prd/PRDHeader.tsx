'use client';

import {
  FileEditIcon,
  Upload04Icon,
  MessageSearch01Icon,
  TaskEdit01Icon,
} from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import type { PrdResponse } from '@/types';

interface PRDHeaderProps {
  prd: PrdResponse | null;
  onUploadPrd: () => void;
  onStartDiscovery: () => void;
  onGenerateTasks: () => void;
}

export function PRDHeader({
  prd,
  onUploadPrd,
  onStartDiscovery,
  onGenerateTasks,
}: PRDHeaderProps) {
  return (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <FileEditIcon className="h-6 w-6 text-muted-foreground" />
        <div>
          <h2 className="text-2xl font-bold tracking-tight">
            {prd ? prd.title : 'Product Requirements'}
          </h2>
          {prd && (
            <p className="text-sm text-muted-foreground">
              Version {prd.version} &middot;{' '}
              {new Date(prd.created_at).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>

      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={onUploadPrd}>
          <Upload04Icon className="mr-1.5 h-4 w-4" />
          {prd ? 'Upload New' : 'Upload PRD'}
        </Button>
        <Button variant="outline" size="sm" onClick={onStartDiscovery}>
          <MessageSearch01Icon className="mr-1.5 h-4 w-4" />
          Discovery
        </Button>
        <Button size="sm" onClick={onGenerateTasks} disabled={!prd}>
          <TaskEdit01Icon className="mr-1.5 h-4 w-4" />
          Generate Tasks
        </Button>
      </div>
    </header>
  );
}
