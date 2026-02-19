'use client';

import { useState } from 'react';
import { ArrowDown01Icon, ArrowUp01Icon, CheckmarkCircle01Icon } from '@hugeicons/react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatRelativeTime } from '@/lib/format';
import type { Blocker } from '@/types';

interface ResolvedBlockersSectionProps {
  blockers: Blocker[];
}

/**
 * Collapsible section displaying resolved/answered blockers.
 *
 * Collapsed by default. When expanded, each blocker shows its question,
 * quoted answer, status badge, task ID, and relative timestamp.
 */
export function ResolvedBlockersSection({ blockers }: ResolvedBlockersSectionProps) {
  const [expanded, setExpanded] = useState(false);

  if (blockers.length === 0) {
    return null;
  }

  return (
    <div data-testid="resolved-blockers-section">
      <Button
        variant="ghost"
        className="w-full justify-between"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        aria-controls="resolved-blockers-list"
      >
        <span className="flex items-center gap-2">
          <CheckmarkCircle01Icon className="h-4 w-4 text-muted-foreground" />
          Resolved Blockers ({blockers.length})
        </span>
        {expanded ? (
          <ArrowUp01Icon className="h-4 w-4" />
        ) : (
          <ArrowDown01Icon className="h-4 w-4" />
        )}
      </Button>

      <div
        id="resolved-blockers-list"
        data-testid="resolved-blockers-list"
        className={expanded ? 'mt-2 space-y-2' : 'hidden'}
        role="region"
        aria-label="Resolved blockers list"
      >
        {blockers.map((blocker) => {
          const timestamp = blocker.answered_at ?? blocker.created_at;
          const badgeVariant = 'done' as const;

          return (
            <Card key={blocker.id} className="bg-muted/50">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-foreground">{blocker.question}</p>
                  <Badge variant={badgeVariant} className="shrink-0">
                    {blocker.status}
                  </Badge>
                </div>

                {blocker.answer && (
                  <div className="mt-2 border-l-2 border-muted-foreground/20 pl-3">
                    <p className="text-sm text-muted-foreground">{blocker.answer}</p>
                  </div>
                )}

                <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                  {blocker.task_id && <span>{blocker.task_id}</span>}
                  {blocker.task_id && timestamp && (
                    <span aria-hidden="true">·</span>
                  )}
                  {timestamp && (
                    <time dateTime={timestamp}>
                      {formatRelativeTime(timestamp)}
                    </time>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
