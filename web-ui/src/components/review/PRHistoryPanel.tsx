'use client';

import { useState } from 'react';
import useSWR from 'swr';
import {
  ArrowDown01Icon,
  ArrowUp01Icon,
  ArrowUpRight01Icon,
  CheckmarkCircle01Icon,
  Cancel01Icon,
  Alert02Icon,
} from '@hugeicons/react';
import { prApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CaptureGlitchModal } from '@/components/proof';
import type {
  PRHistoryResponse,
  PRHistoryItem,
  ProofSnapshot,
  GateBreakdownItem,
} from '@/types';

// ── Helpers ──────────────────────────────────────────────────────────────────

function proofBadgeClasses(snapshot: ProofSnapshot | null): string {
  if (!snapshot) return 'text-muted-foreground bg-muted';
  if (snapshot.gates_total > 0 && snapshot.gates_passed === snapshot.gates_total) {
    return 'text-green-600 bg-green-50';
  }
  return 'text-yellow-600 bg-yellow-50';
}

function proofBadgeText(snapshot: ProofSnapshot | null): string {
  if (!snapshot) return 'No proof data';
  return `${snapshot.gates_passed}/${snapshot.gates_total} gates`;
}

// ── Component ────────────────────────────────────────────────────────────────

export interface PRHistoryPanelProps {
  workspacePath: string;
}

export function PRHistoryPanel({ workspacePath }: PRHistoryPanelProps) {
  const [expandedPR, setExpandedPR] = useState<number | null>(null);
  const [loadingFiles, setLoadingFiles] = useState<number | null>(null);
  const [glitchTarget, setGlitchTarget] = useState<{
    pr: PRHistoryItem;
    files: string[];
  } | null>(null);

  const swrKey = workspacePath
    ? `/api/v2/pr/history?workspace_path=${encodeURIComponent(workspacePath)}`
    : null;

  const { data, error } = useSWR<PRHistoryResponse>(
    swrKey,
    () => prApi.getHistory(workspacePath)
  );

  const toggleExpand = (prNumber: number) => {
    setExpandedPR((prev) => (prev === prNumber ? null : prNumber));
  };

  const handleReportGlitch = async (pr: PRHistoryItem) => {
    setLoadingFiles(pr.number);
    try {
      const files = await prApi.getFiles(workspacePath, pr.number);
      setGlitchTarget({ pr, files });
    } catch {
      // Open the modal with a note so the user knows scope couldn't be loaded
      setGlitchTarget({ pr, files: ['# Could not load changed files — enter scope manually'] });
    } finally {
      setLoadingFiles(null);
    }
  };

  return (
    <Card data-slot="pr-history-panel" className="flex w-full flex-col gap-4 p-4">
      <h3 className="text-lg font-semibold">PR History</h3>

      {/* Loading skeleton */}
      {!data && !error && (
        <div className="flex flex-col gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-muted" />
          ))}
        </div>
      )}

      {/* Error state */}
      {error && !data && (
        <p className="text-sm text-muted-foreground">
          Unable to load PR history
        </p>
      )}

      {/* Empty state */}
      {data && data.pull_requests.length === 0 && (
        <p className="text-sm text-muted-foreground">No merged PRs yet</p>
      )}

      {/* PR list */}
      {data && data.pull_requests.length > 0 && (
        <div className="flex flex-col gap-2">
          {data.pull_requests.map((pr: PRHistoryItem) => (
            <div key={pr.number} className="flex flex-col rounded-md border">
              {/* Row header */}
              <div className="flex items-center gap-2 p-3">
                <button
                  type="button"
                  onClick={() => toggleExpand(pr.number)}
                  className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left transition-all rounded-md focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
                  aria-expanded={expandedPR === pr.number}
                >
                  {/* Left side */}
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-sm font-medium">
                      {pr.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(pr.merged_at).toLocaleDateString()}
                      {pr.author && ` by ${pr.author}`}
                    </span>
                  </div>

                  {/* Proof badge + chevron */}
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge
                      variant="secondary"
                      className={proofBadgeClasses(pr.proof_snapshot)}
                    >
                      {proofBadgeText(pr.proof_snapshot)}
                    </Badge>
                    {expandedPR === pr.number ? (
                      <ArrowUp01Icon className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ArrowDown01Icon className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                </button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="shrink-0 gap-1.5 text-xs"
                  disabled={loadingFiles !== null}
                  onClick={() => handleReportGlitch(pr)}
                >
                  {loadingFiles === pr.number ? (
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
                  ) : (
                    <Alert02Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  Report Glitch
                </Button>
                <a
                  href={pr.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-muted-foreground transition-all hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring rounded"
                  aria-label={`Open PR #${pr.number} on GitHub`}
                >
                  <ArrowUpRight01Icon className="h-4 w-4" />
                </a>
              </div>

              {/* Expanded gate breakdown */}
              {expandedPR === pr.number && pr.proof_snapshot && (
                <div className="border-t px-3 py-2">
                  <div className="flex flex-col gap-1">
                    {pr.proof_snapshot.gate_breakdown.map((gate: GateBreakdownItem) => (
                      <div
                        key={gate.gate}
                        className="flex items-center gap-2 text-xs"
                      >
                        {gate.status === 'satisfied' ? (
                          <CheckmarkCircle01Icon className="h-3.5 w-3.5 text-green-600" />
                        ) : (
                          <Cancel01Icon className="h-3.5 w-3.5 text-red-600" />
                        )}
                        <span className="text-muted-foreground">
                          {gate.gate}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Expanded but no proof data */}
              {expandedPR === pr.number && !pr.proof_snapshot && (
                <div className="border-t px-3 py-2">
                  <p className="text-xs text-muted-foreground">
                    No proof snapshot available for this PR.
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {glitchTarget && (
        <CaptureGlitchModal
          open
          workspacePath={workspacePath}
          prNumber={glitchTarget.pr.number}
          prTitle={glitchTarget.pr.title}
          prUrl={glitchTarget.pr.url}
          initialScope={glitchTarget.files.join('\n')}
          onClose={() => setGlitchTarget(null)}
          onSuccess={() => setGlitchTarget(null)}
        />
      )}
    </Card>
  );
}
