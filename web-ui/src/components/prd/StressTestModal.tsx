'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Loading03Icon,
  TestTube01Icon,
  CheckmarkCircle01Icon,
  Alert01Icon,
} from '@hugeicons/react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useStressTestStream } from '@/hooks/useStressTestStream';
import { prdApi } from '@/lib/api';
import type { PrdResponse } from '@/types';
import { AmbiguityCard } from './AmbiguityCard';

interface StressTestModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspacePath: string;
  /** PRD being stress-tested; required to refine into a new version. */
  prdId: string | null;
  /** Called with the refined PRD version after a successful refine. */
  onRefined?: (prd: PrdResponse) => void;
}

/**
 * Triggers the PRD stress-test (recursive decomposition) over SSE, renders
 * streaming progress, then shows the results view (issue #562): each ambiguity
 * as an answerable card with a [Refine PRD] action that folds the answers back
 * into a new PRD version. [Refine PRD] stays disabled until every *blocking*
 * ambiguity is answered.
 */
export function StressTestModal({
  open,
  onOpenChange,
  workspacePath,
  prdId,
  onRefined,
}: StressTestModalProps) {
  const { status, lines, result, error, start, reset } =
    useStressTestStream(workspacePath);

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [isRefining, setIsRefining] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Kick off the stream the first time the modal opens; tear down on close.
  useEffect(() => {
    if (open) {
      start();
    } else {
      reset();
    }
    setAnswers({});
    setIsRefining(false);
    // start/reset are stable (useCallback); only react to open changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Auto-scroll the log to the bottom as new lines arrive.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  const ambiguities = result?.ambiguities ?? [];
  const hasResults = status === 'complete' && ambiguities.length > 0;

  const answeredCount = useMemo(
    () => ambiguities.filter((a) => (answers[a.id] ?? '').trim().length > 0).length,
    [ambiguities, answers]
  );
  const blockingUnanswered = useMemo(
    () =>
      ambiguities.filter(
        (a) => a.severity === 'blocking' && (answers[a.id] ?? '').trim().length === 0
      ).length,
    [ambiguities, answers]
  );

  function handleAnswerChange(id: string, value: string) {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }

  function handleClose() {
    onOpenChange(false);
  }

  async function handleRefine() {
    if (!prdId || blockingUnanswered > 0) return;
    setIsRefining(true);
    try {
      const payload = ambiguities
        .filter((a) => (answers[a.id] ?? '').trim().length > 0)
        .map((a) => ({
          label: a.label,
          questions: a.questions,
          answer: answers[a.id].trim(),
        }));
      const refined = await prdApi.refineStressTest(prdId, workspacePath, payload);
      toast.success('PRD refined from your answers');
      onRefined?.(refined);
      onOpenChange(false);
    } catch (err) {
      const detail = (err as { detail?: unknown }).detail;
      toast.error(
        typeof detail === 'string'
          ? detail
          : 'Failed to refine PRD. Please try again.'
      );
    } finally {
      setIsRefining(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={hasResults ? 'sm:max-w-2xl' : 'sm:max-w-lg'}
      >
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

        {/* Streaming log — shown while streaming, or on completion when there
            are no answerable ambiguities to render. Single scroll container so
            the auto-scroll ref and the visible scrollbar are the same element. */}
        {((status === 'streaming') || (status === 'complete' && !hasResults)) &&
          lines.length > 0 && (
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
          )}

        {/* Results view — answerable ambiguity cards + refine action (#562). */}
        {hasResults && (
          <>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {answeredCount} of {ambiguities.length} answered
              </span>
              {blockingUnanswered > 0 && (
                <span className="text-xs text-muted-foreground">
                  {blockingUnanswered} blocking question
                  {blockingUnanswered === 1 ? '' : 's'} remaining
                </span>
              )}
            </div>
            <div className="max-h-[50vh] space-y-3 overflow-y-auto pr-1">
              {ambiguities.map((amb) => (
                <AmbiguityCard
                  key={amb.id}
                  ambiguity={amb}
                  answer={answers[amb.id] ?? ''}
                  onChange={handleAnswerChange}
                />
              ))}
            </div>
          </>
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
          {hasResults && (
            <Button
              size="sm"
              onClick={handleRefine}
              disabled={
                blockingUnanswered > 0 ||
                answeredCount === 0 ||
                isRefining ||
                !prdId
              }
            >
              {isRefining && <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />}
              Refine PRD
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
