'use client';

import { useMemo, useCallback } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { CheckmarkCircle01Icon, Loading03Icon } from '@hugeicons/react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BlockerCard } from './BlockerCard';
import { ResolvedBlockersSection } from './ResolvedBlockersSection';
import { blockersApi } from '@/lib/api';
import type { BlockerListResponse, ApiError } from '@/types';

interface BlockerResolutionViewProps {
  workspacePath: string;
}

export function BlockerResolutionView({ workspacePath }: BlockerResolutionViewProps) {
  const { mutate: globalMutate } = useSWRConfig();
  const { data, isLoading, error, mutate } = useSWR<BlockerListResponse, ApiError>(
    `/api/v2/blockers?path=${workspacePath}`,
    () => blockersApi.getAll(workspacePath),
    { refreshInterval: 5000, revalidateOnFocus: true }
  );

  // Invalidate both main view and sidebar badge caches
  const revalidateAll = useCallback(() => {
    mutate();
    globalMutate(`/api/v2/blockers/sidebar?path=${workspacePath}`);
  }, [mutate, globalMutate, workspacePath]);

  const openBlockers = useMemo(
    () => data?.blockers.filter((b) => b.status === 'OPEN') ?? [],
    [data?.blockers]
  );

  const resolvedBlockers = useMemo(
    () => data?.blockers.filter((b) => b.status === 'ANSWERED' || b.status === 'RESOLVED') ?? [],
    [data?.blockers]
  );

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">Blockers</h1>
        </div>
        <div className="flex items-center justify-center py-12">
          <Loading03Icon className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">Loading blockers...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">Blockers</h1>
        </div>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
          <p className="mb-3 text-sm text-destructive">
            {error.detail || 'Failed to load blockers'}
          </p>
          <Button variant="outline" size="sm" onClick={() => revalidateAll()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Blockers</h1>
        {openBlockers.length > 0 && (
          <Badge variant="blocked">{openBlockers.length} open</Badge>
        )}
      </div>

      {/* Open blockers */}
      {openBlockers.length === 0 ? (
        <div className="rounded-lg border bg-muted/50 p-8 text-center">
          <CheckmarkCircle01Icon className="mx-auto mb-3 h-10 w-10 text-green-500" />
          <p className="text-sm font-medium text-foreground">No open blockers</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Agents are running smoothly — no questions need your attention.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {openBlockers.map((blocker) => (
            <BlockerCard
              key={blocker.id}
              blocker={blocker}
              workspacePath={workspacePath}
              onAnswered={() => revalidateAll()}
            />
          ))}
        </div>
      )}

      {/* Resolved blockers */}
      <ResolvedBlockersSection blockers={resolvedBlockers} />
    </div>
  );
}
