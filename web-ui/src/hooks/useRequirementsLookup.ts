'use client';

import useSWR from 'swr';
import { proofApi } from '@/lib/api';
import type { ProofRequirement } from '@/types';

/**
 * Fetches all PROOF9 requirements for a workspace and returns a Map for O(1) lookup by ID.
 * Uses SWR so the fetch is deduplicated across all consumers (TaskCard, TaskDetailModal, etc.)
 */
export function useRequirementsLookup(workspacePath: string | null | undefined) {
  const { data, isLoading, error } = useSWR(
    workspacePath ? ['/proof/requirements', workspacePath] : null,
    ([, path]: [string, string]) => proofApi.listRequirements(path),
  );

  const requirementsMap = new Map<string, ProofRequirement>(
    (data?.requirements ?? []).map((r) => [r.id, r]),
  );

  return { requirementsMap, isLoading, error };
}
