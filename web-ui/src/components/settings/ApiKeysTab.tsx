'use client';

import useSWR from 'swr';

import { settingsApi } from '@/lib/api';
import type { KeyProvider, KeyStatusResponse } from '@/types';
import { KeySlot } from './KeySlot';

const PROVIDER_DISPLAY: Array<{ provider: KeyProvider; displayName: string }> = [
  { provider: 'LLM_ANTHROPIC', displayName: 'Anthropic API Key' },
  { provider: 'LLM_OPENAI', displayName: 'OpenAI API Key' },
  { provider: 'GIT_GITHUB', displayName: 'GitHub Personal Access Token' },
];

export function ApiKeysTab() {
  const { data, error, isLoading, mutate } = useSWR<KeyStatusResponse[]>(
    'settings:keys',
    () => settingsApi.getKeys()
  );

  if (isLoading && !data) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error || !data) {
    return (
      <p className="text-sm text-destructive">
        Failed to load API key status. Check the server logs.
      </p>
    );
  }

  const statusByProvider = new Map<KeyProvider, KeyStatusResponse>(
    data.map((entry) => [entry.provider, entry])
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Keys are stored encrypted on this machine. Environment variables take
        precedence at runtime.
      </p>
      <div className="space-y-3">
        {PROVIDER_DISPLAY.map(({ provider, displayName }) => {
          const status =
            statusByProvider.get(provider) ?? {
              provider,
              stored: false,
              source: 'none' as const,
              last_four: null,
            };
          return (
            <KeySlot
              key={provider}
              provider={provider}
              displayName={displayName}
              status={status}
              onChanged={() => mutate().then(() => undefined)}
            />
          );
        })}
      </div>
    </div>
  );
}
