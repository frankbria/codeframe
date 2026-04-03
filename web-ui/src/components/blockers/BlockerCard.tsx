'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Alert02Icon,
  Loading03Icon,
  CheckmarkCircle01Icon,
  ArtificialIntelligence01Icon,
  Settings01Icon,
  UserCircle02Icon,
} from '@hugeicons/react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { blockersApi } from '@/lib/api';
import { formatRelativeTime } from '@/lib/format';
import type { Blocker, BlockerOrigin, ApiError } from '@/types';

const ORIGIN_CONFIG: Record<BlockerOrigin, {
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  badgeClass: string;
  guidance: string;
}> = {
  system: {
    label: 'System',
    Icon: Settings01Icon,
    badgeClass: 'bg-blue-100 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300',
    guidance: 'System-initiated pause. Review the context and answer to continue.',
  },
  agent: {
    label: 'Agent',
    Icon: ArtificialIntelligence01Icon,
    badgeClass: 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
    guidance: 'Agent requested information. Provide the answer below.',
  },
  human: {
    label: 'Manual',
    Icon: UserCircle02Icon,
    badgeClass: 'bg-purple-100 text-purple-800 dark:bg-purple-950/40 dark:text-purple-300',
    guidance: 'Manually created blocker. Resolve and mark answered.',
  },
};

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
  const origin = ORIGIN_CONFIG[blocker.created_by ?? 'human'];

  const handleSubmit = async () => {
    if (!answer.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await blockersApi.answer(workspacePath, blocker.id, answer.trim());
      setSubmitted(true);
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
        <CardContent className="flex items-center justify-between gap-4 p-4">
          <div className="flex items-center gap-2">
            <CheckmarkCircle01Icon className="h-5 w-5 shrink-0 text-green-600 dark:text-green-400" />
            <p className="text-sm font-medium text-green-800 dark:text-green-300">
              Answer recorded. Go to Tasks and restart execution to resume the agent.
            </p>
          </div>
          <Button size="sm" variant="outline" asChild>
            <Link href="/tasks" onClick={onAnswered}>Go to Tasks</Link>
          </Button>
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
            Raised by{' '}
            <Link href="/tasks" className="text-primary hover:underline">
              Task {blocker.task_id}
            </Link>
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
          <span
            data-testid="origin-badge"
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${origin.badgeClass}`}
          >
            <origin.Icon className="h-3 w-3" />
            {origin.label}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(blocker.created_at)}
          </span>
        </div>

        {/* Origin-specific guidance */}
        <p className="text-xs text-muted-foreground pt-1">{origin.guidance}</p>
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
