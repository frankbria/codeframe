'use client';

import useSWR from 'swr';
import { prApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import type { CICheck, PRStatusResponse } from '@/types';

// ── Badge variant mappings ────────────────────────────────────────────────

type BadgeVariant =
  | 'default'
  | 'secondary'
  | 'destructive'
  | 'outline'
  | 'ready'
  | 'in-progress'
  | 'done'
  | 'blocked'
  | 'failed'
  | 'backlog'
  | 'merged';

function ciCheckVariant(check: CICheck): BadgeVariant {
  if (check.status !== 'completed') {
    return check.status === 'in_progress' ? 'in-progress' : 'backlog';
  }
  switch (check.conclusion) {
    case 'success':
      return 'done';
    case 'failure':
    case 'timed_out':
    case 'action_required':
      return 'failed';
    default:
      return 'backlog';
  }
}

function ciCheckLabel(check: CICheck): string {
  if (check.status === 'in_progress') return 'Running';
  if (check.status === 'queued') return 'Queued';
  return check.conclusion ?? check.status;
}

const REVIEW_BADGE: Record<string, { variant: BadgeVariant; label: string }> = {
  approved: { variant: 'done', label: 'Approved' },
  changes_requested: { variant: 'failed', label: 'Changes Requested' },
  pending: { variant: 'backlog', label: 'Pending Review' },
};

const MERGE_BADGE: Record<string, { variant: BadgeVariant; label: string }> = {
  merged: { variant: 'merged', label: 'Merged' },
  closed: { variant: 'blocked', label: 'Closed' },
  open: { variant: 'in-progress', label: 'Open' },
};

// ── Component ─────────────────────────────────────────────────────────────

export interface PRStatusPanelProps {
  prNumber: number;
  workspacePath: string;
}

export function PRStatusPanel({ prNumber, workspacePath }: PRStatusPanelProps) {
  const swrKey = `/api/v2/pr/status?workspace_path=${encodeURIComponent(workspacePath)}&pr_number=${prNumber}`;

  const { data, error } = useSWR<PRStatusResponse>(
    swrKey,
    () => prApi.getStatus(workspacePath, prNumber),
    {
      // Stop polling once the PR is merged or closed.
      refreshInterval: (latestData) => {
        if (
          latestData?.merge_state === 'merged' ||
          latestData?.merge_state === 'closed'
        ) {
          return 0;
        }
        return 30_000;
      },
    }
  );

  const reviewBadge = REVIEW_BADGE[data?.review_status ?? 'pending'] ?? REVIEW_BADGE.pending;
  const mergeBadge = MERGE_BADGE[data?.merge_state ?? 'open'] ?? MERGE_BADGE.open;

  return (
    <Card className="flex w-80 flex-col gap-4 p-4 mt-4">
      <h3 className="text-lg font-semibold">PR Status</h3>

      {/* Loading skeleton */}
      {!data && !error && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-5 animate-pulse rounded bg-muted"
            />
          ))}
        </div>
      )}

      {/* Error state */}
      {error && !data && (
        <p className="text-sm text-muted-foreground">
          Unable to load PR status — will retry shortly.
        </p>
      )}

      {/* Data */}
      {data && (
        <>
          {/* Merge state + review status row */}
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={mergeBadge.variant}>{mergeBadge.label}</Badge>
            <Badge variant={reviewBadge.variant}>{reviewBadge.label}</Badge>
          </div>

          {/* CI checks */}
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">CI Checks</span>
            {data.ci_checks.length === 0 ? (
              <p className="text-xs text-muted-foreground">No checks found.</p>
            ) : (
              <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
                {data.ci_checks.map((check, idx) => (
                  <div
                    key={`${check.name}-${idx}`}
                    className="flex items-center justify-between gap-2"
                  >
                    <span
                      className="truncate text-xs text-muted-foreground"
                      title={check.name}
                    >
                      {check.name}
                    </span>
                    <Badge variant={ciCheckVariant(check)} className="shrink-0">
                      {ciCheckLabel(check)}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
