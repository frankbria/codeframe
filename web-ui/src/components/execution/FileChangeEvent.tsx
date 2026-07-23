'use client';

import { HugeiconsIcon } from '@hugeicons/react';
import { FileEditIcon } from '@hugeicons/core-free-icons';
import type { ProgressEvent } from '@/hooks/useTaskStream';

interface FileChangeEventProps {
  event: ProgressEvent;
}

/**
 * Renders a file change event as a single file-path line.
 *
 * The message from the backend typically looks like:
 *   "Creating file: src/auth/middleware.py"
 *   "Editing file: src/auth/middleware.py"
 *
 * ponytail: no inline diff here. The stream is a live activity log; the real
 * per-file diff lives on the /review page (DiffViewer). A previous "View Diff"
 * toggle only expanded to the event message — a placeholder, not a diff — so it
 * was removed (#775) rather than duplicate /review with a worse mini-viewer.
 */
export function FileChangeEvent({ event }: FileChangeEventProps) {
  // Extract file path from message (pattern: "Creating/Editing file: <path>")
  const filePath = event.message?.replace(/^(Creating|Editing|Deleting) file:\s*/i, '') ?? '';

  return (
    <div className="flex items-center gap-2 text-sm">
      <HugeiconsIcon icon={FileEditIcon} className="h-4 w-4 shrink-0 text-green-600" />
      <span className="truncate font-mono text-xs">{filePath || event.message}</span>
    </div>
  );
}
