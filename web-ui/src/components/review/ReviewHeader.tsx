'use client';

import {
  FileEditIcon,
  Loading03Icon,
  CheckmarkCircle01Icon,
  Cancel01Icon,
  Download04Icon,
  PlayIcon,
} from '@hugeicons/react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { GateResult } from '@/types';

export interface ReviewHeaderProps {
  filesChanged: number;
  insertions: number;
  deletions: number;
  gateResult: GateResult | null;
  isRunningGates: boolean;
  onRunGates: () => void;
  onExportPatch: () => void;
}

export function ReviewHeader({
  filesChanged,
  insertions,
  deletions,
  gateResult,
  isRunningGates,
  onRunGates,
  onExportPatch,
}: ReviewHeaderProps) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-4">
        {/* Left: Change summary */}
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <FileEditIcon className="h-4 w-4" />
            <span>
              {filesChanged} {filesChanged === 1 ? 'file' : 'files'} changed
            </span>
          </span>
          <span className="font-mono text-green-600">+{insertions}</span>
          <span className="font-mono text-red-600">-{deletions}</span>
        </div>

        {/* Center: Quality gate badges */}
        <div className="flex items-center gap-2">
          {gateResult ? (
            gateResult.checks.map((check) => (
              <Badge
                key={check.name}
                className={cn(
                  'gap-1',
                  check.status === 'PASSED'
                    ? 'border-transparent bg-green-100 text-green-900'
                    : check.status === 'FAILED'
                      ? 'border-transparent bg-red-100 text-red-900'
                      : ''
                )}
                variant={
                  check.status === 'PASSED' || check.status === 'FAILED'
                    ? undefined
                    : 'secondary'
                }
              >
                {check.status === 'PASSED' ? (
                  <CheckmarkCircle01Icon className="h-3 w-3" />
                ) : check.status === 'FAILED' ? (
                  <Cancel01Icon className="h-3 w-3" />
                ) : null}
                {check.name}
              </Badge>
            ))
          ) : (
            <span className="text-sm text-muted-foreground">
              No gates run
            </span>
          )}
        </div>

        {/* Right: Action buttons */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onRunGates}
            disabled={isRunningGates}
            className="transition-all"
          >
            {isRunningGates ? (
              <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <PlayIcon className="mr-1.5 h-4 w-4" />
            )}
            Run Gates
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onExportPatch}
            className="transition-all"
          >
            <Download04Icon className="mr-1.5 h-4 w-4" />
            Export Patch
          </Button>
        </div>
      </div>
    </Card>
  );
}
