'use client';

import { Button } from '@/components/ui/button';

interface GateRunBannerProps {
  passed: boolean;
  message: string;
  onRetry: () => void;
  /** Number of gates that could not be verified (waivable, not failures). */
  unverifiableCount?: number;
}

export function GateRunBanner({ passed, message, onRetry, unverifiableCount = 0 }: GateRunBannerProps) {
  if (passed && unverifiableCount > 0) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="mb-4 flex items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-900/50 dark:bg-amber-900/10"
      >
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400" aria-hidden="true" />
        <p className="text-sm font-medium text-amber-900 dark:text-amber-300">
          Gates passed — {unverifiableCount} gate{unverifiableCount === 1 ? '' : 's'} could not be verified
        </p>
        {message && <span className="text-xs text-amber-800/80 dark:text-amber-400/80 ml-1">{message}</span>}
      </div>
    );
  }

  if (passed) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="mb-4 flex items-center gap-3 rounded-lg border bg-muted/30 px-4 py-3"
      >
        <span className="h-2.5 w-2.5 rounded-full bg-green-400" aria-hidden="true" />
        <p className="text-sm font-medium">All gates passed</p>
        {message && <span className="text-xs text-muted-foreground ml-1">{message}</span>}
      </div>
    );
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="mb-4 flex items-center gap-3 rounded-lg border border-destructive bg-destructive/10 px-4 py-3"
    >
      <span className="h-2.5 w-2.5 rounded-full bg-red-400" aria-hidden="true" />
      <p className="text-sm font-medium text-destructive">Some gates failed</p>
      {message && <span className="text-xs text-destructive/80 ml-1 flex-1">{message}</span>}
      <Button variant="ghost" size="sm" onClick={onRetry} className="text-destructive hover:text-destructive/80">
        Retry
      </Button>
    </div>
  );
}
