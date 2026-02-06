'use client';

import { useState } from 'react';
import { FileEditIcon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import type { ProgressEvent } from '@/hooks/useTaskStream';

interface FileChangeEventProps {
  event: ProgressEvent;
}

/**
 * Renders a file change event with a collapsible diff preview.
 *
 * The message from the backend typically looks like:
 *   "Creating file: src/auth/middleware.py"
 *   "Editing file: src/auth/middleware.py"
 */
export function FileChangeEvent({ event }: FileChangeEventProps) {
  const [expanded, setExpanded] = useState(false);

  // Extract file path from message (pattern: "Creating/Editing file: <path>")
  const filePath = event.message?.replace(/^(Creating|Editing|Deleting) file:\s*/i, '') ?? '';

  return (
    <div className="text-sm">
      <div className="flex items-center gap-2">
        <FileEditIcon className="h-4 w-4 shrink-0 text-green-600" />
        <span className="truncate font-mono text-xs">{filePath || event.message}</span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto h-5 px-1.5 text-[10px] text-muted-foreground"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide' : 'View Diff'}
        </Button>
      </div>
      {expanded && (
        <pre className="mt-1.5 max-h-48 overflow-auto rounded bg-muted/50 p-2 font-mono text-[11px] leading-relaxed">
          {/* Diff content will come from OutputEvents following this ProgressEvent.
              For now, show the event message as placeholder context. */}
          {event.message}
        </pre>
      )}
    </div>
  );
}
