'use client';

import { Idea01Icon } from '@hugeicons/react';
import type { ProgressEvent } from '@/hooks/useTaskStream';

interface PlanningEventProps {
  event: ProgressEvent;
}

export function PlanningEvent({ event }: PlanningEventProps) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <Idea01Icon className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
      <div className="min-w-0">
        {event.total_steps > 0 && (
          <span className="text-xs text-muted-foreground">
            Generated {event.total_steps}-step plan
          </span>
        )}
        {event.message && (
          <p className="font-mono text-xs text-foreground">{event.message}</p>
        )}
      </div>
    </div>
  );
}
