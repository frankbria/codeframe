'use client';

import { useState, useEffect } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
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

    // Append selected gates to description so the backend LLM uses them when
    // deriving obligations (CaptureRequirementRequest has no gates field;
    // obligations are auto-derived from the description).
    const gateHint = `\n\nRequired gates: ${Array.from(selectedGates).join(', ')}`;
    const fullDescription = description.trim() + gateHint;

    // Derive `where` from scope lines, falling back to source
    const scopeLines = scopeText.split('\n').map((l) => l.trim()).filter(Boolean);
    const where = scopeLines.length > 0 ? scopeLines.join(', ') : source;

    const body: CaptureGlitchRequest = {
      title,
      description: fullDescription,
      where,
      severity,
      source,
      created_by: 'human',
    };

    try {
      const result = await proofApi.capture(workspacePath, body);
      onSuccess(result);
    } catch (err: unknown) {
      // Axios errors carry detail at err.response.data.detail
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      const detail = axiosErr?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to capture glitch. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  // Slide-over panel using Radix Dialog primitives directly so we can position
  // it as a right-anchored sheet rather than a centered modal.
  return (
    <DialogPrimitive.Root open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col border-l bg-background shadow-xl transition-transform duration-300 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-lg"
          aria-describedby="capture-description-text"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b px-6 py-4">
            <div>
              <DialogPrimitive.Title className="text-lg font-semibold">
                Capture Glitch
              </DialogPrimitive.Title>
              <p id="capture-description-text" className="mt-0.5 text-sm text-muted-foreground">
                Convert a production failure into a permanent PROOF9 requirement.
              </p>
            </div>
            <DialogPrimitive.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </DialogPrimitive.Close>
          </div>

          {/* Scrollable form body */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            <div className="space-y-5">
              {/* Description */}
              <div>
                <label htmlFor="capture-description" className="mb-1 block text-sm font-medium">
                  Description <span aria-hidden="true" className="text-destructive">*</span>
                </label>
                <Textarea
                  id="capture-description"
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
                  <SelectTrigger id="capture-source">
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
                  Scope <span className="font-normal text-muted-foreground">(affected files, routes, components — one per line)</span>
                </label>
                <Textarea
                  id="capture-scope"
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
                  <span className="ml-2 font-normal text-muted-foreground text-xs">(appended to description to guide obligation derivation)</span>
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
                  <SelectTrigger id="capture-severity">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITY_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
            </div>
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-2 border-t px-6 py-4">
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
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
