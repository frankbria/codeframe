'use client';

import { Badge } from '@/components/ui/badge';
import type { GateRunEntry, GateRunStatus } from '@/types';

interface GateRunPanelProps {
  gateEntries: GateRunEntry[];
}

const STATUS_LABEL: Record<GateRunStatus, string> = {
  pending: 'pending',
  running: 'running',
  passed: 'passed',
  failed: 'failed',
};

const STATUS_CLASSES: Record<GateRunStatus, string> = {
  pending: 'bg-gray-100 text-gray-600',
  running: 'bg-blue-100 text-blue-800 animate-pulse',
  passed: 'bg-green-100 text-green-900',
  failed: 'bg-red-100 text-red-900',
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
            <Badge className={STATUS_CLASSES[status]}>
              {STATUS_LABEL[status]}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}
