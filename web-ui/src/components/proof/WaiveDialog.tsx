'use client';

import { useState } from 'react';
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
import { proofApi } from '@/lib/api';
import type { WaiveRequest } from '@/types';

export function WaiveDialog({
  reqId,
  workspacePath,
  onClose,
  onSuccess,
}: {
  reqId: string;
  workspacePath: string;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [step, setStep] = useState<'form' | 'confirm'>('form');
  const [reason, setReason] = useState('');
  const [expires, setExpires] = useState('');
  const [approvedBy, setApprovedBy] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleContinue = () => {
    if (!reason.trim()) { setError('Reason is required'); return; }
    setError(null);
    setStep('confirm');
  };

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body: WaiveRequest = {
        reason: reason.trim(),
        expires: expires || null,
        manual_checklist: [],
        approved_by: approvedBy.trim(),
      };
      await proofApi.waive(workspacePath, reqId, body);
      onSuccess();
    } catch {
      setError('Failed to waive requirement');
      setStep('form');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Waive {reqId}</DialogTitle>
        </DialogHeader>

        {step === 'form' ? (
          <div className="space-y-4">
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
              <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
              <Button type="button" onClick={handleContinue}>Continue →</Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
              This requirement will be marked satisfied without evidence. Waiver reason will be recorded. This decision will appear in the audit trail.
            </div>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="font-medium">Reason:</dt>
                <dd className="text-muted-foreground">{reason}</dd>
              </div>
              {expires && (
                <div className="flex gap-2">
                  <dt className="font-medium">Expires:</dt>
                  <dd className="text-muted-foreground">{expires}</dd>
                </div>
              )}
              {approvedBy && (
                <div className="flex gap-2">
                  <dt className="font-medium">Approved by:</dt>
                  <dd className="text-muted-foreground">{approvedBy}</dd>
                </div>
              )}
            </dl>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setStep('form')}>← Back</Button>
              <Button type="button" onClick={handleConfirm} disabled={submitting}>
                {submitting ? 'Waiving…' : 'Confirm Waive'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
