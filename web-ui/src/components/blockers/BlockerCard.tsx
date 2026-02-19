'use client';

import { useState } from 'react';
import { Alert02Icon, Loading03Icon, CheckmarkCircle01Icon } from '@hugeicons/react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { blockersApi } from '@/lib/api';
import { formatRelativeTime } from '@/lib/format';
import type { Blocker, ApiError } from '@/types';

interface BlockerCardProps {
  blocker: Blocker;
  workspacePath: string;
  onAnswered: () => void;
}

export function BlockerCard({ blocker, workspacePath, onAnswered }: BlockerCardProps) {
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const isOpen = blocker.status === 'OPEN';

  const handleSubmit = async () => {
    if (!answer.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await blockersApi.answer(workspacePath, blocker.id, answer.trim());
      setSubmitted(true);
      setTimeout(() => onAnswered(), 1500);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || 'Failed to submit answer');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <Card
        data-testid="blocker-card"
        className="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/30"
      >
        <CardContent className="flex items-center gap-2 p-4">
          <CheckmarkCircle01Icon className="h-5 w-5 text-green-600 dark:text-green-400" />
          <p className="text-sm font-medium text-green-800 dark:text-green-300">
            Blocker answered. Task will resume execution.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="blocker-card">
      <CardHeader className="pb-3">
        {/* Task context */}
        {blocker.task_id && (
          <p className="text-xs font-medium text-muted-foreground">
            Task {blocker.task_id}
          </p>
        )}

        {/* Question */}
        <div className="rounded-md border-2 border-red-300 bg-red-50 p-3 dark:border-red-700 dark:bg-red-950/30">
          <div className="flex items-start gap-2">
            <Alert02Icon className="mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
            <p className="text-sm font-medium text-foreground">{blocker.question}</p>
          </div>
        </div>

        {/* Metadata row */}
        <div className="flex items-center gap-2 pt-1">
          <Badge variant="blocked">OPEN</Badge>
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(blocker.created_at)}
          </span>
        </div>
      </CardHeader>

      <CardContent>
        {/* Read-only answer display for already-answered blockers */}
        {!isOpen && blocker.answer && (
          <div className="rounded-md border bg-muted/50 p-3">
            <p className="mb-1 text-xs font-medium text-muted-foreground">Answer</p>
            <p className="text-sm text-foreground">{blocker.answer}</p>
          </div>
        )}

        {/* Answer form for OPEN blockers */}
        {isOpen && !collapsed && (
          <div data-testid="blocker-answer-form">
            <textarea
              className="mb-2 w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
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

            {/* Character count */}
            <div className="mb-2 text-right">
              <span className="text-xs text-muted-foreground">
                {answer.length} characters
              </span>
            </div>

            {error && (
              <p className="mb-2 text-xs text-destructive">{error}</p>
            )}

            <div className="flex items-center justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setCollapsed(true)}
                disabled={isSubmitting}
              >
                Skip
              </Button>
              <Button
                size="sm"
                className="gap-1"
                onClick={handleSubmit}
                disabled={!answer.trim() || isSubmitting}
              >
                {isSubmitting && <Loading03Icon className="h-3 w-3 animate-spin" />}
                Answer Blocker
              </Button>
            </div>
          </div>
        )}

        {/* Collapsed state — allow re-expanding */}
        {isOpen && collapsed && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => setCollapsed(false)}
          >
            Show answer form
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
