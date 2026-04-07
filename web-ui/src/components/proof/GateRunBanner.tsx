'use client';

import { Button } from '@/components/ui/button';

interface GateRunBannerProps {
  passed: boolean;
  message: string;
  onRetry: () => void;
}

export function GateRunBanner({ passed, message, onRetry }: GateRunBannerProps) {
  if (passed) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="mb-4 flex items-center gap-3 rounded-lg border border-green-300 bg-green-50 px-4 py-3"
      >
        <span className="h-2.5 w-2.5 rounded-full bg-green-500" aria-hidden="true" />
        <p className="text-sm font-medium text-green-900">All gates passed</p>
        <span className="text-xs text-green-700 ml-1">{message}</span>
      </div>
    );
  }

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="mb-4 flex items-center gap-3 rounded-lg border border-red-300 bg-red-50 px-4 py-3"
    >
      <span className="h-2.5 w-2.5 rounded-full bg-red-500" aria-hidden="true" />
      <p className="text-sm font-medium text-red-900">Some gates failed</p>
      <span className="text-xs text-red-700 ml-1 flex-1">{message}</span>
      <Button variant="ghost" size="sm" onClick={onRetry} className="text-red-800 hover:text-red-900">
        Retry
      </Button>
    </div>
  );
}
