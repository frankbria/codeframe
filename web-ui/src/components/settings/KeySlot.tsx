'use client';

import { useState } from 'react';
import { toast } from 'sonner';

import { settingsApi } from '@/lib/api';
import type { ApiError, KeyProvider, KeyStatusResponse } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface KeySlotProps {
  provider: KeyProvider;
  displayName: string;
  status: KeyStatusResponse;
  onChanged: () => void | Promise<void>;
}

type VerifyResult = { valid: boolean; message: string } | null;

export function KeySlot({
  provider,
  displayName,
  status,
  onChanged,
}: KeySlotProps) {
  const [value, setValue] = useState('');
  const [verifyResult, setVerifyResult] = useState<VerifyResult>(null);
  const [working, setWorking] = useState(false);

  const handleSave = async () => {
    if (!value) return;
    setWorking(true);
    setVerifyResult(null);
    try {
      await settingsApi.storeKey(provider, value);
      setValue('');
      toast.success(`${displayName} key saved`);
      await onChanged();
    } catch (err) {
      toast.error((err as ApiError).detail || 'Failed to save key');
    } finally {
      setWorking(false);
    }
  };

  const handleVerify = async () => {
    setWorking(true);
    setVerifyResult(null);
    try {
      const result = await settingsApi.verifyKey(provider, value || undefined);
      setVerifyResult({ valid: result.valid, message: result.message });
      if (!result.valid) {
        toast.error(result.message);
      }
    } catch (err) {
      const detail = (err as ApiError).detail || 'Verification failed';
      setVerifyResult({ valid: false, message: detail });
      toast.error(detail);
    } finally {
      setWorking(false);
    }
  };

  const handleRemove = async () => {
    setWorking(true);
    setVerifyResult(null);
    try {
      await settingsApi.removeKey(provider);
      setValue('');
      toast.success(`${displayName} key removed`);
      await onChanged();
    } catch (err) {
      toast.error((err as ApiError).detail || 'Failed to remove key');
    } finally {
      setWorking(false);
    }
  };

  const placeholder = status.stored
    ? `•••••••• (last 4: ${status.last_four ?? '????'})`
    : `Enter ${displayName} key`;

  const sourceLabel =
    status.source === 'environment'
      ? 'env var'
      : status.source === 'stored'
      ? 'stored'
      : 'not set';

  const sourceVariant: 'default' | 'secondary' | 'outline' =
    status.source === 'environment'
      ? 'secondary'
      : status.source === 'stored'
      ? 'default'
      : 'outline';

  // Env-source keys are read-only — env vars take precedence at runtime,
  // so storing/removing wouldn't change the effective key.
  const fromEnv = status.source === 'environment';

  return (
    <div className="rounded-lg border bg-card p-4" data-provider={provider}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{displayName}</h3>
        <Badge variant={sourceVariant}>{sourceLabel}</Badge>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          disabled={working || fromEnv}
          autoComplete="off"
          spellCheck={false}
          className="min-w-0 flex-1"
          aria-label={displayName}
        />
        <Button
          type="button"
          variant="outline"
          onClick={handleVerify}
          disabled={working || (fromEnv ? false : !value && !status.stored)}
        >
          Verify
        </Button>
        {value && (
          <Button type="button" onClick={handleSave} disabled={working || fromEnv}>
            Save
          </Button>
        )}
        {status.stored && status.source === 'stored' && (
          <Button
            type="button"
            variant="destructive"
            onClick={handleRemove}
            disabled={working}
          >
            Remove
          </Button>
        )}
      </div>

      {fromEnv && (
        <p className="mt-2 text-xs text-muted-foreground">
          Loaded from environment variable. Unset the env var to manage this key here.
        </p>
      )}

      {verifyResult && (
        <p
          className={`mt-2 text-xs ${
            verifyResult.valid ? 'text-green-600' : 'text-destructive'
          }`}
          role="status"
        >
          {verifyResult.valid ? '✓ Valid' : '✗ Invalid'} — {verifyResult.message}
        </p>
      )}
    </div>
  );
}
