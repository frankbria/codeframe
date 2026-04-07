'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { proofApi } from '@/lib/api';
import type { GateRunEntry, GateRunStatus } from '@/types';

export type ProofRunState = 'idle' | 'starting' | 'polling' | 'complete' | 'error';

export interface UseProofRunReturn {
  runState: ProofRunState;
  gateEntries: GateRunEntry[];
  passed: boolean | null;
  errorMessage: string | null;
  startRun: (workspacePath: string) => void;
  retry: () => void;
}

/**
 * Manages the full lifecycle of a PROOF9 gate run.
 *
 * Flow: idle → starting (POST) → polling (GET every 2s) → complete / error
 *
 * Since POST /run is synchronous on the backend, the first poll immediately
 * resolves. The optimistic "pending → running" transition gives visual feedback
 * before the final pass/fail state is applied.
 */
export function useProofRun(): UseProofRunReturn {
  const [runState, setRunState] = useState<ProofRunState>('idle');
  const [gateEntries, setGateEntries] = useState<GateRunEntry[]>([]);
  const [passed, setPassed] = useState<boolean | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const workspaceRef = useRef<string>('');
  const runIdRef = useRef<string>('');

  const clearPollInterval = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return clearPollInterval;
  }, [clearPollInterval]);

  const startRun = useCallback(
    async (workspacePath: string) => {
      clearPollInterval();
      workspaceRef.current = workspacePath;
      setRunState('starting');
      setGateEntries([]);
      setPassed(null);
      setErrorMessage(null);

      try {
        const response = await proofApi.startRun(workspacePath, { full: true });
        runIdRef.current = response.run_id;

        // Build optimistic "running" entries from returned results
        const entries: GateRunEntry[] = Object.values(response.results)
          .flat()
          .map((item) => ({ gate: item.gate, status: 'running' as GateRunStatus }));
        // Deduplicate gate names
        const seen = new Set<string>();
        const uniqueEntries = entries.filter(({ gate }) => {
          if (seen.has(gate)) return false;
          seen.add(gate);
          return true;
        });

        setGateEntries(uniqueEntries.length > 0 ? uniqueEntries : []);
        setRunState('polling');

        // Poll every 2s until complete
        intervalRef.current = setInterval(async () => {
          try {
            const status = await proofApi.getRun(workspaceRef.current, runIdRef.current);
            if (status.status === 'complete') {
              clearPollInterval();

              // Build final gate entries with pass/fail status
              const finalEntries: GateRunEntry[] = Object.values(status.results)
                .flat()
                .map((item) => ({
                  gate: item.gate,
                  status: item.satisfied ? ('passed' as GateRunStatus) : ('failed' as GateRunStatus),
                }));
              const seenFinal = new Set<string>();
              const uniqueFinal = finalEntries.filter(({ gate }) => {
                if (seenFinal.has(gate)) return false;
                seenFinal.add(gate);
                return true;
              });

              setGateEntries(uniqueFinal);
              setPassed(status.passed);
              setRunState('complete');
            }
          } catch {
            clearPollInterval();
            setErrorMessage('Failed to retrieve run status. Please retry.');
            setRunState('error');
          }
        }, 2000);
      } catch (err: unknown) {
        clearPollInterval();
        const message =
          err instanceof Error
            ? err.message
            : typeof err === 'object' && err !== null && 'detail' in err
            ? String((err as { detail: unknown }).detail)
            : 'Failed to start proof run.';
        setErrorMessage(message);
        setRunState('error');
      }
    },
    [clearPollInterval]
  );

  const retry = useCallback(() => {
    clearPollInterval();
    setRunState('idle');
    setGateEntries([]);
    setPassed(null);
    setErrorMessage(null);
  }, [clearPollInterval]);

  return { runState, gateEntries, passed, errorMessage, startRun, retry };
}
