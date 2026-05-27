'use client';

import { useEffect, useRef } from 'react';
import {
  Loading03Icon,
  TestTube01Icon,
  CheckmarkCircle01Icon,
  Alert01Icon,
} from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useStressTestStream } from '@/hooks/useStressTestStream';

interface StressTestModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspacePath: string;
}

/**
 * Triggers the PRD stress-test (recursive decomposition) over SSE and renders
 * streaming progress. Results rendering / answer flow is out of scope here
 * (tracked in issue #562) — the hook retains the spec + report for that work.
 */
export function StressTestModal({
  open,
  onOpenChange,
  workspacePath,
}: StressTestModalProps) {
  const { status, lines, result, error, start, reset } =
    useStressTestStream(workspacePath);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Kick off the stream the first time the modal opens; tear down on close.
  useEffect(() => {
    if (open) {
      start();
    } else {
      reset();
    }
    // start/reset are stable (useCallback); only react to open changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Auto-scroll the log to the bottom as new lines arrive.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  function handleClose() {
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TestTube01Icon className="h-5 w-5 text-muted-foreground" />
            Stress Test PRD
          </DialogTitle>
          <DialogDescription>
            Recursively decomposing your PRD to surface ambiguities and gaps.
          </DialogDescription>
        </DialogHeader>

        {status === 'streaming' && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loading03Icon className="h-4 w-4 animate-spin" />
            Analyzing PRD...
          </div>
        )}

        {status === 'complete' && (
          <div className="flex items-center gap-2 text-sm font-medium text-green-600 dark:text-green-500">
            <CheckmarkCircle01Icon className="h-4 w-4" />
            {result && result.ambiguityCount > 0
              ? `Found ${result.ambiguityCount} ambiguit${result.ambiguityCount === 1 ? 'y' : 'ies'}`
              : 'No ambiguities found — PRD is well-specified'}
          </div>
        )}

        {/* Streaming log */}
        {(status === 'streaming' || status === 'complete') && lines.length > 0 && (
          <ScrollArea className="max-h-[40vh]">
            <div
              ref={scrollRef}
              className="max-h-[40vh] overflow-y-auto rounded-md bg-muted p-4 font-mono text-xs"
            >
              {lines.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap">
                  {line}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        {/* Error state */}
        {status === 'error' && (
          <div className="rounded-md border border-destructive bg-destructive/10 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-destructive">
              <Alert01Icon className="h-4 w-4" />
              Stress test failed
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {error ?? 'An unexpected error occurred.'}
            </p>
          </div>
        )}

        <div className="flex justify-end gap-2">
          {status === 'error' && (
            <Button size="sm" onClick={start}>
              Retry
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={handleClose}>
            {status === 'complete' || status === 'error' ? 'Close' : 'Cancel'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
