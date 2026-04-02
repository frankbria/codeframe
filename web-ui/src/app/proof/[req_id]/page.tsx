'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import useSWR from 'swr';
import { Button } from '@/components/ui/button';
import { ProofStatusBadge, WaiveDialog } from '@/components/proof';
import { proofApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { ProofRequirement, ProofEvidence } from '@/types';

export default function ProofDetailPage() {
  const params = useParams();
  const reqId = params.req_id as string;

  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [showWaiveDialog, setShowWaiveDialog] = useState(false);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  const { data: req, error: reqError, isLoading: reqLoading, mutate: mutateReq } =
    useSWR<ProofRequirement>(
      workspacePath && reqId ? `/api/v2/proof/requirements/${reqId}?path=${workspacePath}` : null,
      () => proofApi.getRequirement(workspacePath!, reqId)
    );

  const { data: evidence, error: evidenceError, isLoading: evidenceLoading } =
    useSWR<ProofEvidence[]>(
      workspacePath && reqId ? `/api/v2/proof/requirements/${reqId}/evidence?path=${workspacePath}` : null,
      () => proofApi.getEvidence(workspacePath!, reqId)
    );

  if (!workspaceReady) return null;

  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <p className="text-muted-foreground">No workspace selected.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Link href="/proof" className="mb-6 inline-block text-sm text-muted-foreground hover:text-foreground">
          ← Back to requirements
        </Link>

        {reqLoading && (
          <div className="space-y-4">
            <div className="h-8 w-64 animate-pulse rounded bg-muted" />
            <div className="h-24 animate-pulse rounded bg-muted" />
          </div>
        )}

        {reqError && (
          <div className="rounded-lg border border-destructive bg-destructive/10 p-4">
            <p className="text-sm text-destructive">Requirement not found</p>
          </div>
        )}

        {req && (
          <div className="space-y-8">
            {/* Header */}
            <div>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="mb-1 font-mono text-xs text-muted-foreground">{req.id}</p>
                  <h1 className="text-2xl font-bold">{req.title}</h1>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <span className="rounded-md bg-muted px-2 py-1 text-xs capitalize">{req.severity}</span>
                  <ProofStatusBadge status={req.status} />
                </div>
              </div>
              {req.description && (
                <p className="mt-3 text-sm text-muted-foreground">{req.description}</p>
              )}
              <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
                {req.created_at && <span>Created {new Date(req.created_at).toLocaleDateString()}</span>}
                {req.source_issue && <span>Source: {req.source_issue}</span>}
                {req.created_by && <span>By: {req.created_by}</span>}
              </div>
            </div>

            {/* Glitch Type */}
            {req.glitch_type && (
              <section>
                <h2 className="mb-3 text-base font-semibold">Glitch Type</h2>
                <span className="rounded-md bg-muted px-2 py-1 text-sm">{req.glitch_type}</span>
              </section>
            )}

            {/* Obligations */}
            {req.obligations.length > 0 && (
              <section>
                <h2 className="mb-3 text-base font-semibold">Gate Obligations</h2>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="min-w-full text-sm">
                    <thead className="border-b bg-muted/50">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium">Gate</th>
                        <th className="px-4 py-2 text-left font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {req.obligations.map((ob, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="px-4 py-2 font-mono text-xs">{ob.gate}</td>
                          <td className="px-4 py-2 capitalize text-muted-foreground">{ob.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Evidence history */}
            <section>
              <h2 className="mb-3 text-base font-semibold">Evidence History</h2>
              {evidenceLoading && (
                <div className="h-16 animate-pulse rounded bg-muted" />
              )}
              {!evidenceLoading && evidenceError && (
                <p className="text-sm text-destructive">Failed to load evidence.</p>
              )}
              {!evidenceLoading && !evidenceError && (!evidence || evidence.length === 0) && (
                <p className="text-sm text-muted-foreground">No evidence recorded yet.</p>
              )}
              {evidence && evidence.length > 0 && (
                <div className="overflow-x-auto rounded-lg border">
                  <table className="min-w-[640px] w-full text-sm">
                    <thead className="border-b bg-muted/50">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium">Gate</th>
                        <th className="px-4 py-2 text-left font-medium">Result</th>
                        <th className="px-4 py-2 text-left font-medium">Run ID</th>
                        <th className="px-4 py-2 text-left font-medium">Timestamp</th>
                        <th className="px-4 py-2 text-left font-medium">Artifact</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evidence.map((ev, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="px-4 py-2 font-mono text-xs">{ev.gate}</td>
                          <td className="px-4 py-2">
                            <span className={ev.satisfied ? 'text-green-600' : 'text-red-600'}>
                              {ev.satisfied ? 'pass' : 'fail'}
                            </span>
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{ev.run_id}</td>
                          <td className="px-4 py-2 text-muted-foreground">
                            {new Date(ev.timestamp).toLocaleString()}
                          </td>
                          <td className="max-w-xs px-4 py-2 font-mono text-xs text-muted-foreground">
                            <span className="line-clamp-1">{ev.artifact_path || '—'}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Waiver */}
            <section>
              <h2 className="mb-3 text-base font-semibold">Waiver</h2>
              {req.waiver ? (
                <div className="rounded-lg border bg-muted/30 p-4">
                  <p className="text-sm"><span className="font-medium">Reason:</span> {req.waiver.reason}</p>
                  {req.waiver.approved_by && (
                    <p className="mt-1 text-sm text-muted-foreground">Approved by: {req.waiver.approved_by}</p>
                  )}
                  {req.waiver.waived_at && (
                    <p className="mt-1 text-sm text-muted-foreground">Waived: {new Date(req.waiver.waived_at).toLocaleString()}</p>
                  )}
                  {req.waiver.expires && (
                    <p className="mt-1 text-sm text-muted-foreground">Expires: {req.waiver.expires}</p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No waiver on file.</p>
              )}
              {req.status !== 'waived' && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => setShowWaiveDialog(true)}
                >
                  Waive this requirement
                </Button>
              )}
            </section>
          </div>
        )}

        {showWaiveDialog && workspacePath && (
          <WaiveDialog
            reqId={reqId}
            workspacePath={workspacePath}
            onClose={() => setShowWaiveDialog(false)}
            onSuccess={() => {
              setShowWaiveDialog(false);
              mutateReq();
            }}
          />
        )}
      </div>
    </main>
  );
}
