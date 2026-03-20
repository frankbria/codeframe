'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { ProofStatusBadge } from '@/components/proof';
import { proofApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { ProofRequirement, ProofRequirementListResponse, WaiveRequest } from '@/types';

function WaiveDialog({
  requirement,
  workspacePath,
  onClose,
  onSuccess,
}: {
  requirement: ProofRequirement;
  workspacePath: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [reason, setReason] = useState('');
  const [expires, setExpires] = useState('');
  const [approvedBy, setApprovedBy] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError('Reason is required');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: WaiveRequest = {
        reason: reason.trim(),
        expires: expires || null,
        manual_checklist: [],
        approved_by: approvedBy.trim(),
      };
      await proofApi.waive(workspacePath, requirement.id, body);
      onSuccess();
    } catch {
      setError('Failed to waive requirement');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Waive {requirement.id}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="waive-reason" className="mb-1 block text-sm font-medium">Reason *</label>
            <Textarea
              id="waive-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this requirement being waived?"
            />
          </div>
          <div>
            <label htmlFor="waive-expires" className="mb-1 block text-sm font-medium">Expiry date (optional)</label>
            <Input
              id="waive-expires"
              type="date"
              value={expires}
              onChange={(e) => setExpires(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="waive-approved-by" className="mb-1 block text-sm font-medium">Approved by</label>
            <Input
              id="waive-approved-by"
              type="text"
              value={approvedBy}
              onChange={(e) => setApprovedBy(e.target.value)}
              placeholder="Your name or handle"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? 'Waiving…' : 'Waive requirement'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function ProofPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [waivedReq, setWaivedReq] = useState<ProofRequirement | null>(null);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  const { data, error, isLoading, mutate } = useSWR<ProofRequirementListResponse>(
    workspacePath ? `/api/v2/proof/requirements?path=${workspacePath}` : null,
    () => proofApi.listRequirements(workspacePath!)
  );

  if (!workspaceReady) return null;

  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected. Return to{' '}
              <Link href="/" className="text-primary hover:underline">Workspace</Link> and select a project.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">PROOF9 Requirements</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Quality memory — requirements captured from glitches, proven through evidence.
          </p>
        </div>

        {isLoading && (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive bg-destructive/10 p-4">
            <p className="text-sm text-destructive">Failed to load requirements</p>
          </div>
        )}

        {data && data.total === 0 && (
          <div className="rounded-lg border bg-muted/50 p-8 text-center">
            <p className="text-muted-foreground">No requirements captured yet.</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Use <code className="rounded bg-muted px-1 py-0.5 text-xs">cf proof capture</code> to add the first one.
            </p>
          </div>
        )}

        {data && data.total > 0 && (
          <>
            <div className="mb-4 flex gap-4 text-sm text-muted-foreground">
              <span>{data.by_status?.open ?? 0} open</span>
              <span>{data.by_status?.satisfied ?? 0} satisfied</span>
              <span>{data.by_status?.waived ?? 0} waived</span>
              <span className="font-medium text-foreground">{data.total} total</span>
            </div>

            <div className="overflow-x-auto rounded-lg border">
              <table className="min-w-[800px] w-full text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">ID</th>
                    <th className="px-4 py-3 text-left font-medium">Title</th>
                    <th className="px-4 py-3 text-left font-medium">Glitch Type</th>
                    <th className="px-4 py-3 text-left font-medium">Severity</th>
                    <th className="px-4 py-3 text-left font-medium">Gates</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Created</th>
                    <th className="px-4 py-3 text-left font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {data.requirements.map((req) => (
                    <tr key={req.id} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link href={`/proof/${encodeURIComponent(req.id)}`} className="text-primary hover:underline">
                          {req.id}
                        </Link>
                      </td>
                      <td className="max-w-xs px-4 py-3">
                        <span className="line-clamp-1">{req.title}</span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {req.glitch_type ?? '—'}
                      </td>
                      <td className="px-4 py-3 capitalize">{req.severity}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {req.obligations.length}
                      </td>
                      <td className="px-4 py-3">
                        <ProofStatusBadge status={req.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {req.created_at ? new Date(req.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {req.status !== 'waived' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setWaivedReq(req)}
                          >
                            Waive
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {waivedReq && (
          <WaiveDialog
            requirement={waivedReq}
            workspacePath={workspacePath}
            onClose={() => setWaivedReq(null)}
            onSuccess={() => {
              setWaivedReq(null);
              mutate();
            }}
          />
        )}
      </div>
    </main>
  );
}
