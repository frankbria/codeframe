'use client';

import { useState } from 'react';
import { Alert02Icon, Loading03Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { blockersApi } from '@/lib/api';
import type { BlockerEvent as BlockerEventType } from '@/hooks/useTaskStream';
import type { ApiError } from '@/types';

interface BlockerEventProps {
  event: BlockerEventType;
  workspacePath: string;
  onAnswered?: () => void;
}

/**
 * Renders a blocker as an interrupt pattern with an inline answer form.
 *
 * Matches the architecture doc Section 4 "Interrupt Pattern for Blockers":
 * highlighted card, question text, textarea, and submit button.
 */
export function BlockerEvent({ event, workspacePath, onAnswered }: BlockerEventProps) {
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!answer.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await blockersApi.answer(workspacePath, String(event.blocker_id), answer.trim());
      setSubmitted(true);
      onAnswered?.();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || 'Failed to submit answer');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm dark:border-green-800 dark:bg-green-950/30">
        <p className="text-green-800 dark:text-green-300">
          Blocker answered. Execution resuming...
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border-2 border-red-300 bg-red-50 p-3 dark:border-red-700 dark:bg-red-950/30">
      {/* Header */}
      <div className="mb-2 flex items-center gap-2">
        <Alert02Icon className="h-4 w-4 text-red-600" />
        <span className="text-sm font-semibold text-red-800 dark:text-red-300">
          Agent needs your help
        </span>
      </div>

      {/* Question */}
      <p className="mb-3 text-sm text-foreground">{event.question}</p>

      {/* Context (if available) */}
      {event.context && (
        <p className="mb-3 text-xs text-muted-foreground">{event.context}</p>
      )}

      {/* Answer form */}
      <textarea
        className="mb-2 w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        rows={3}
        placeholder="Type your answer..."
        aria-label="Your answer to the blocker question"
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            handleSubmit();
          }
        }}
        disabled={isSubmitting}
      />

      {error && (
        <p className="mb-2 text-xs text-destructive">{error}</p>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Execution paused — waiting for response...
        </span>
        <Button
          size="sm"
          className="h-7 gap-1 px-3 text-xs"
          onClick={handleSubmit}
          disabled={!answer.trim() || isSubmitting}
        >
          {isSubmitting && <Loading03Icon className="h-3 w-3 animate-spin" />}
          Answer Blocker
        </Button>
      </div>
    </div>
  );
}
