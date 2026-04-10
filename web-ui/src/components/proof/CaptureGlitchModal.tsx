'use client';

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { proofApi } from '@/lib/api';
import type { ProofRequirement, ProofSeverity, CaptureGlitchRequest } from '@/types';

// The 9 PROOF9 gate types (mirrors Gate enum in codeframe/core/proof/models.py)
const GATE_LIST = ['unit', 'contract', 'e2e', 'visual', 'a11y', 'perf', 'sec', 'demo', 'manual'] as const;

const SOURCE_OPTIONS: { value: CaptureGlitchRequest['source']; label: string }[] = [
  { value: 'production', label: 'Production' },
  { value: 'qa', label: 'QA' },
  { value: 'dogfooding', label: 'Dogfooding' },
  { value: 'monitoring', label: 'Monitoring' },
  { value: 'user_report', label: 'User Report' },
];

const SEVERITY_OPTIONS: { value: ProofSeverity; label: string }[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

export interface CaptureGlitchModalProps {
  open: boolean;
  workspacePath: string;
  onClose: () => void;
  onSuccess: (req: ProofRequirement) => void;
}

export function CaptureGlitchModal({ open, workspacePath, onClose, onSuccess }: CaptureGlitchModalProps) {
  const [description, setDescription] = useState('');
  const [source, setSource] = useState<CaptureGlitchRequest['source']>('production');
  const [scopeText, setScopeText] = useState('');
  const [selectedGates, setSelectedGates] = useState<Set<string>>(new Set());
  const [severity, setSeverity] = useState<ProofSeverity>('high');
  const [expires, setExpires] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset all state when the modal opens
  useEffect(() => {
    if (open) {
      setDescription('');
      setSource('production');
      setScopeText('');
      setSelectedGates(new Set());
      setSeverity('high');
      setExpires('');
      setSubmitting(false);
      setError(null);
    }
  }, [open]);

  function toggleGate(gate: string) {
    setSelectedGates((prev) => {
      const next = new Set(prev);
      if (next.has(gate)) {
        next.delete(gate);
      } else {
        next.add(gate);
      }
      return next;
    });
  }

  async function handleSubmit() {
    // Validate
    if (!description.trim()) {
      setError('Description is required');
      return;
    }
    if (selectedGates.size === 0) {
      setError('Select at least one gate');
      return;
    }

    setError(null);
    setSubmitting(true);

    // Derive title from first line of description (max 80 chars)
    const title = description.trim().split('\n')[0].slice(0, 80);

    // Derive `where` from scope lines, falling back to source
    const scopeLines = scopeText.split('\n').map((l) => l.trim()).filter(Boolean);
    const where = scopeLines.length > 0 ? scopeLines.join(', ') : source;

    const body: CaptureGlitchRequest = {
      title,
      description: description.trim(),
      where,
      severity,
      source,
      created_by: 'human',
    };

    try {
      const result = await proofApi.capture(workspacePath, body);
      onSuccess(result);
    } catch (err: unknown) {
      const detail = (err as { detail?: string })?.detail;
      setError(detail ?? 'Failed to capture glitch. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Capture Glitch</DialogTitle>
          <DialogDescription>
            Convert a production failure into a permanent PROOF9 requirement.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Description */}
          <div>
            <label htmlFor="capture-description" className="mb-1 block text-sm font-medium">
              Description <span aria-hidden="true" className="text-destructive">*</span>
            </label>
            <Textarea
              id="capture-description"
              aria-label="Description"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the failure…"
            />
          </div>

          {/* Where found */}
          <div>
            <label htmlFor="capture-source" className="mb-1 block text-sm font-medium">
              Where was it found? <span aria-hidden="true" className="text-destructive">*</span>
            </label>
            <Select value={source} onValueChange={(v) => setSource(v as CaptureGlitchRequest['source'])}>
              <SelectTrigger id="capture-source" aria-label="Where was it found?">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Scope */}
          <div>
            <label htmlFor="capture-scope" className="mb-1 block text-sm font-medium">
              Scope <span className="text-muted-foreground font-normal">(affected files, routes, components — one per line)</span>
            </label>
            <Textarea
              id="capture-scope"
              aria-label="Scope"
              rows={3}
              value={scopeText}
              onChange={(e) => setScopeText(e.target.value)}
              placeholder={`src/components/Foo.tsx\n/api/v2/bar`}
            />
          </div>

          {/* Gates */}
          <div>
            <p className="mb-2 text-sm font-medium">
              PROOF9 Gates Required <span aria-hidden="true" className="text-destructive">*</span>
            </p>
            <div className="grid grid-cols-3 gap-2">
              {GATE_LIST.map((gate) => (
                <label key={gate} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    aria-label={gate}
                    checked={selectedGates.has(gate)}
                    onCheckedChange={() => toggleGate(gate)}
                  />
                  {gate}
                </label>
              ))}
            </div>
          </div>

          {/* Severity */}
          <div>
            <label htmlFor="capture-severity" className="mb-1 block text-sm font-medium">
              Severity <span aria-hidden="true" className="text-destructive">*</span>
            </label>
            <Select value={severity} onValueChange={(v) => setSeverity(v as ProofSeverity)}>
              <SelectTrigger id="capture-severity" aria-label="Severity">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SEVERITY_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Expiry */}
          <div>
            <label htmlFor="capture-expires" className="mb-1 block text-sm font-medium">
              Expiry date <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <Input
              id="capture-expires"
              aria-label="Expiry"
              type="date"
              value={expires}
              onChange={(e) => setExpires(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? (
              <span className="flex items-center gap-2">
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
                Capturing…
              </span>
            ) : (
              'Capture Glitch'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
