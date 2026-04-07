'use client';

import { Badge } from '@/components/ui/badge';
import type { GateRunEntry, GateRunStatus } from '@/types';

interface GateRunPanelProps {
  gateEntries: GateRunEntry[];
}

// Map GateRunStatus to Badge variant names from the shared design system
const STATUS_VARIANT: Record<GateRunStatus, 'backlog' | 'in-progress' | 'done' | 'failed'> = {
  pending: 'backlog',
  running: 'in-progress',
  passed: 'done',
  failed: 'failed',
};

export function GateRunPanel({ gateEntries }: GateRunPanelProps) {
  if (gateEntries.length === 0) return null;

  return (
    <div
      role="status"
      aria-label="Gate run progress"
      className="mb-4 rounded-lg border bg-muted/30 p-4"
    >
      <p className="mb-2 text-sm font-medium">Gate progress</p>
      <ul className="flex flex-wrap gap-2">
        {gateEntries.map(({ gate, status }) => (
          <li key={gate} className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground capitalize">{gate}</span>
            <Badge
              variant={STATUS_VARIANT[status]}
              className={status === 'running' ? 'animate-pulse' : undefined}
            >
              {status}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
