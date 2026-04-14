'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { Loading03Icon, CheckmarkCircle01Icon } from '@hugeicons/react';
import { prApi, proofApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { CICheck, PRStatusResponse, ProofRequirement, ProofStatusResponse } from '@/types';

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

// ── Component ─────────────────────────────────────────────────────────────────

export interface PRStatusPanelProps {
  prNumber: number;
  workspacePath: string;
}

export function PRStatusPanel({ prNumber, workspacePath }: PRStatusPanelProps) {
  const [isMerging, setIsMerging] = useState(false);
  const [merged, setMerged] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);

  const swrKey = `/api/v2/pr/status?workspace_path=${encodeURIComponent(workspacePath)}&pr_number=${prNumber}`;
  const proofKey = `/api/v2/proof/status?workspace_path=${encodeURIComponent(workspacePath)}`;

  const { data, error, mutate: mutatePRStatus } = useSWR<PRStatusResponse>(
    swrKey,
    () => prApi.getStatus(workspacePath, prNumber),
    {
      refreshInterval: (latestData) => {
        if (
          merged ||
          latestData?.merge_state === 'merged' ||
          latestData?.merge_state === 'closed'
        ) {
          return 0;
        }
        return 30_000;
      },
    }
  );

  const { data: proofData, error: proofError, isLoading: proofLoading } = useSWR<ProofStatusResponse>(
    proofKey,
    () => proofApi.getStatus(workspacePath),
    { refreshInterval: merged ? 0 : 15_000 }
  );

  // ── Gate logic ────────────────────────────────────────────────────────────

  const openRequirements: ProofRequirement[] = (proofData?.requirements ?? []).filter(
    (r) => r.status === 'open'
  );

  const ciFailing = (data?.ci_checks ?? []).some(
    (c) =>
      c.conclusion === 'failure' ||
      c.conclusion === 'timed_out' ||
      c.conclusion === 'action_required'
  );

  const ciPending = (data?.ci_checks ?? []).some(
    (c) => c.status === 'in_progress' || c.status === 'queued'
  );

  const ciPassing = !ciFailing && !ciPending;
  const alreadyMerged = merged || data?.merge_state === 'merged';
  const canMerge = !!data && !!proofData && openRequirements.length === 0 && ciPassing;

  // ── Merge handler ─────────────────────────────────────────────────────────

  const handleMerge = async () => {
    setIsMerging(true);
    setMergeError(null);
    try {
      await prApi.merge(workspacePath, prNumber, { method: 'squash' });
      setMerged(true);
      mutatePRStatus((prev) => prev ? { ...prev, merge_state: 'merged' } : prev, false);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setMergeError(apiErr?.detail ?? 'Merge failed. Please try again.');
    } finally {
      setIsMerging(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  const reviewBadge = REVIEW_BADGE[data?.review_status ?? 'pending'] ?? REVIEW_BADGE.pending;
  const mergeBadge = MERGE_BADGE[data?.merge_state ?? 'open'] ?? MERGE_BADGE.open;

  return (
    <Card className="flex w-80 flex-col gap-4 p-4 mt-4">
      <h3 className="text-lg font-semibold">PR Status</h3>

      {/* Loading skeleton */}
      {!data && !error && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-5 animate-pulse rounded bg-muted" />
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

          {/* PROOF9 gate section */}
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">PROOF9</span>
            {proofLoading ? (
              <div className="h-4 animate-pulse rounded bg-muted" />
            ) : proofError && !proofData ? (
              <p className="text-xs text-muted-foreground">
                Unable to load PROOF9 status — merge blocked until resolved.
              </p>
            ) : openRequirements.length === 0 ? (
              <p className="flex items-center gap-1 text-xs text-muted-foreground">
                <CheckmarkCircle01Icon className="h-3 w-3 text-green-600" />
                All clear
              </p>
            ) : (
              <div className="flex flex-col gap-1">
                {openRequirements.map((req) => (
                  <Link
                    key={req.id}
                    href={`/proof/${req.id}`}
                    className="text-xs text-red-600 hover:underline"
                  >
                    {req.title}
                  </Link>
                ))}
                <Link
                  href="/proof"
                  className="mt-1 text-xs text-muted-foreground hover:underline"
                >
                  View all →
                </Link>
              </div>
            )}
          </div>
        </>
      )}

      {/* Blocking messages */}
      {data && (ciFailing || ciPending) && !alreadyMerged && (
        <p className="text-xs text-amber-600">
          {ciFailing ? 'CI checks failing' : 'Waiting for CI checks'}
        </p>
      )}

      {/* Merge error banner */}
      {mergeError && (
        <div className="rounded bg-red-50 px-3 py-2 text-xs text-red-700">
          {mergeError}
        </div>
      )}

      {/* Success banner or Merge button */}
      {alreadyMerged ? (
        <div className="flex items-center gap-1 rounded bg-green-50 px-3 py-2 text-xs text-green-700">
          <CheckmarkCircle01Icon className="h-3 w-3" />
          PR #{prNumber} merged successfully
        </div>
      ) : (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              {/* Wrap in span so tooltip fires even when button is disabled */}
              <span className="w-full">
                <Button
                  onClick={handleMerge}
                  disabled={!canMerge || isMerging}
                  size="sm"
                  className="w-full transition-all"
                >
                  {isMerging ? (
                    <>
                      <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
                      Merging...
                    </>
                  ) : (
                    'Merge'
                  )}
                </Button>
              </span>
            </TooltipTrigger>
            {!canMerge && (
              <TooltipContent>
                {openRequirements.length > 0 && 'Resolve all open PROOF9 requirements. '}
                {ciFailing && 'Fix failing CI checks. '}
                {ciPending && 'Wait for CI checks to complete.'}
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      )}
    </Card>
  );
}
