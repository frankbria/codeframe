'use client';

import { HugeiconsIcon } from '@hugeicons/react';
import { CheckmarkCircle01Icon, Cancel01Icon } from '@hugeicons/core-free-icons';
import type { ProgressEvent } from '@/hooks/useTaskStream';

interface VerificationEventProps {
  event: ProgressEvent;
}

/**
 * Renders a verification gate result.
 *
 * The message from the backend typically looks like:
 *   "ruff check: passed"
 *   "pytest: 3/3 passed"
 *   "ruff check: failed (2 errors)"
 */
export function VerificationEvent({ event }: VerificationEventProps) {
  const passed = /\bpassed?\b/i.test(event.message ?? '');
  const icon = passed ? CheckmarkCircle01Icon : Cancel01Icon;

  return (
    <div className="flex items-center gap-2 text-sm">
      <HugeiconsIcon
        icon={icon}
        className={`h-4 w-4 shrink-0 ${
          passed ? 'text-green-600' : 'text-red-600'
        }`}
      />
      <span className="font-mono text-xs">{event.message}</span>
    </div>
  );
}
