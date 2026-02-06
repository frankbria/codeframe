'use client';

import { useState } from 'react';
import { CommandLineIcon, CheckmarkCircle01Icon, Cancel01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import type { OutputEvent } from '@/hooks/useTaskStream';

interface ShellCommandEventProps {
  /** The output event containing stdout/stderr. */
  event: OutputEvent;
}

/**
 * Renders shell command output with a collapsible output section.
 * Shows the output line in monospace, colored by stream type.
 */
export function ShellCommandEvent({ event }: ShellCommandEventProps) {
  const [expanded, setExpanded] = useState(event.stream === 'stderr');
  const isError = event.stream === 'stderr';

  return (
    <div className="text-sm">
      <div className="flex items-center gap-2">
        <CommandLineIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="truncate font-mono text-xs text-muted-foreground">
          {isError ? 'stderr' : 'stdout'}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-5 px-1.5 text-[10px] text-muted-foreground"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide' : 'Show'}
        </Button>
      </div>
      {expanded && (
        <pre
          className={`mt-1.5 max-h-48 overflow-auto rounded p-2 font-mono text-[11px] leading-relaxed ${
            isError
              ? 'bg-red-50 text-red-800 dark:bg-red-950/30 dark:text-red-300'
              : 'bg-muted/50 text-foreground'
          }`}
        >
          {event.line}
        </pre>
      )}
    </div>
  );
}
