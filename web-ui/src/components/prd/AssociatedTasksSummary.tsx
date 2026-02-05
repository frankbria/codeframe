'use client';

import { Badge } from '@/components/ui/badge';
import type { TaskStatusCounts } from '@/types';
import type { BadgeProps } from '@/components/ui/badge';

interface AssociatedTasksSummaryProps {
  taskCounts: TaskStatusCounts;
}

/** Map TaskStatus keys to Badge variant names. */
const STATUS_CONFIG: {
  key: keyof TaskStatusCounts;
  label: string;
  variant: BadgeProps['variant'];
}[] = [
  { key: 'BACKLOG', label: 'Backlog', variant: 'backlog' },
  { key: 'READY', label: 'Ready', variant: 'ready' },
  { key: 'IN_PROGRESS', label: 'In Progress', variant: 'in-progress' },
  { key: 'BLOCKED', label: 'Blocked', variant: 'blocked' },
  { key: 'FAILED', label: 'Failed', variant: 'failed' },
  { key: 'DONE', label: 'Done', variant: 'done' },
];

export function AssociatedTasksSummary({
  taskCounts,
}: AssociatedTasksSummaryProps) {
  const total = Object.values(taskCounts).reduce((sum, n) => sum + n, 0);

  if (total === 0) return null;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium text-muted-foreground">
        Tasks ({total})
      </span>
      <div className="flex flex-wrap gap-1.5">
        {STATUS_CONFIG.map(
          ({ key, label, variant }) =>
            taskCounts[key] > 0 && (
              <Badge key={key} variant={variant}>
                {label}: {taskCounts[key]}
              </Badge>
            )
        )}
      </div>
    </div>
  );
}
