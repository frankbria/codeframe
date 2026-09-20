'use client';

import { useEffect, useState } from 'react';
import { HugeiconsIcon } from '@hugeicons/react';
import { Alert02Icon, Loading03Icon } from '@hugeicons/core-free-icons';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type { ProofRequirement } from '@/types';

interface MergeOverrideModalProps {
  open: boolean;
  onClose: () => void;
  /** Called with the reason once the user confirms. Resolves when the merge settles. */
  onConfirm: (reason: string) => Promise<void>;
  prNumber: number;
  /** The requirements being bypassed — rendered so the reason is written with them in view. */
  blockingRequirements: ProofRequirement[];
  /** Surfaced in-modal so a failed override (e.g. a 403 for a non-admin) stays visible. */
  error?: string | null;
}

export function MergeOverrideModal({
  open,
  onClose,
  onConfirm,
  prNumber,
  blockingRequirements,
  error,
}: MergeOverrideModalProps) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  // A reason is per-attempt: carrying one over from a previous open would let
  // a stale justification be attached to a different bypass.
  useEffect(() => {
    if (open) {
      setReason('');
      setTouched(false);
    }
  }, [open]);

  const reasonIsEmpty = reason.trim().length === 0;

  const handleConfirm = async () => {
    setTouched(true);
    if (reasonIsEmpty) return;
    setSubmitting(true);
    try {
      await onConfirm(reason.trim());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen && !submitting) onClose();
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HugeiconsIcon icon={Alert02Icon} className="h-5 w-5 text-amber-500" />
            Override the PROOF9 merge gate
          </DialogTitle>
          <DialogDescription>
            Merging PR #{prNumber} while {blockingRequirements.length} requirement
            {blockingRequirements.length === 1 ? '' : 's'} remain unproven. This is
            recorded against your account and shown in the PR history.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              Requirements being bypassed
            </p>
            <ul className="max-h-40 space-y-1 overflow-y-auto rounded border bg-muted/30 p-2">
              {blockingRequirements.map((req) => (
                <li key={req.id} className="text-xs">
                  <span className="font-mono font-medium">{req.id}</span>
                  <span className="text-muted-foreground"> — {req.title}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <label htmlFor="override-reason" className="mb-1.5 block text-xs font-medium">
              Reason <span className="text-destructive">*</span>
            </label>
            <Textarea
              id="override-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              onBlur={() => setTouched(true)}
              placeholder="Why is it correct to merge without proving these?"
              rows={3}
              disabled={submitting}
              aria-invalid={touched && reasonIsEmpty}
              aria-describedby={touched && reasonIsEmpty ? 'override-reason-error' : undefined}
            />
            {touched && reasonIsEmpty && (
              <p id="override-reason-error" className="mt-1 text-xs text-destructive">
                A reason is required to override the gate.
              </p>
            )}
          </div>

          {error && (
            <div className="rounded bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={submitting || reasonIsEmpty}
          >
            {submitting ? (
              <>
                <HugeiconsIcon icon={Loading03Icon} className="mr-1.5 h-4 w-4 animate-spin" />
                Merging...
              </>
            ) : (
              'Override and Merge'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
