'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { proofConfigApi } from '@/lib/api';
import { GATE_LABELS, PROOF9_GATES, type Proof9Gate } from '@/lib/proof';
import type {
  ApiError,
  ProofConfigResponse,
  ProofStrictness,
} from '@/types';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface Proof9DefaultsTabProps {
  workspacePath: string | null;
}

function isDirty(a: ProofConfigResponse, b: ProofConfigResponse): boolean {
  if (a.strictness !== b.strictness) return true;
  if (a.enabled_gates.length !== b.enabled_gates.length) return true;
  const setA = new Set(a.enabled_gates);
  return b.enabled_gates.some((g) => !setA.has(g));
}

export function Proof9DefaultsTab({ workspacePath }: Proof9DefaultsTabProps) {
  const swrKey = workspacePath ? ['proof-config', workspacePath] : null;
  const { data, error, isLoading, mutate } = useSWR<ProofConfigResponse>(
    swrKey,
    () => proofConfigApi.getConfig(workspacePath!)
  );

  const [draft, setDraft] = useState<ProofConfigResponse | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setDraft({ ...data, enabled_gates: [...data.enabled_gates] });
    }
  }, [data]);

  if (!workspacePath) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a workspace from the sidebar to manage PROOF9 defaults.
      </p>
    );
  }
  if (isLoading && !draft) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error || !draft || !data) {
    return (
      <p className="text-sm text-destructive">
        Failed to load PROOF9 config. Check the server logs.
      </p>
    );
  }

  const dirty = isDirty(data, draft);
  const enabledSet = new Set(draft.enabled_gates);

  const toggleGate = (gate: Proof9Gate, checked: boolean) => {
    const next = new Set(enabledSet);
    if (checked) next.add(gate);
    else next.delete(gate);
    setDraft({
      ...draft,
      enabled_gates: PROOF9_GATES.filter((g) => next.has(g)),
    });
  };

  const setStrictness = (value: ProofStrictness) => {
    setDraft({ ...draft, strictness: value });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const saved = await proofConfigApi.updateConfig(workspacePath, {
        enabled_gates: draft.enabled_gates,
        strictness: draft.strictness,
      });
      await mutate(saved, { revalidate: false });
      toast.success('PROOF9 defaults saved');
    } catch (err) {
      const apiError = err as ApiError;
      toast.error(apiError.detail || 'Failed to save PROOF9 defaults');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setDraft({ ...data, enabled_gates: [...data.enabled_gates] });
    toast.info('Changes discarded');
  };

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        These defaults apply to new projects and to gate runs in this workspace.
      </p>

      <div>
        <h3 className="mb-3 text-sm font-medium">Gates enabled for new projects</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {PROOF9_GATES.map((gate) => {
            const id = `proof9-gate-${gate}`;
            return (
              <label
                key={gate}
                htmlFor={id}
                className="flex items-center gap-2 text-sm"
              >
                <Checkbox
                  id={id}
                  checked={enabledSet.has(gate)}
                  onCheckedChange={(checked) => toggleGate(gate, checked === true)}
                />
                <span>{GATE_LABELS[gate]}</span>
              </label>
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Strictness</h3>
        <p className="mb-3 text-xs text-muted-foreground">
          <strong>strict</strong> fails proof runs on any open non-waived REQ.{' '}
          <strong>warn</strong> allows merge with warnings.
        </p>
        <Select
          value={draft.strictness}
          onValueChange={(v) => setStrictness(v as ProofStrictness)}
        >
          <SelectTrigger className="max-w-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="strict">strict</SelectItem>
            <SelectItem value="warn">warn</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex justify-end gap-2 border-t pt-4">
        <Button
          type="button"
          variant="outline"
          onClick={handleDiscard}
          disabled={!dirty || saving}
        >
          Discard
        </Button>
        <Button
          type="button"
          onClick={handleSave}
          disabled={!dirty || saving}
        >
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </div>
  );
}
