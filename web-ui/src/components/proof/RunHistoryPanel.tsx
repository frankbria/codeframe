'use client';

import useSWR from 'swr';
import { proofApi } from '@/lib/api';
import type { ProofRunSummary } from '@/types';

interface RunHistoryPanelProps {
  workspacePath: string;
  onSelectRun: (runId: string) => void;
  selectedRunId: string | null;
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function RunHistoryPanel({ workspacePath, onSelectRun, selectedRunId }: RunHistoryPanelProps) {
  const { data, error, isLoading } = useSWR<ProofRunSummary[]>(
    workspacePath ? `/api/v2/proof/runs?path=${workspacePath}` : null,
    () => proofApi.listRuns(workspacePath, 5)
  );

  return (
    <section aria-label="Recent runs" className="mt-6">
      <h2 className="mb-3 text-base font-semibold">Recent Runs</h2>

      {isLoading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded-md bg-muted" />
          ))}
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">Failed to load run history.</p>
      )}

      {!isLoading && !error && (!data || data.length === 0) && (
        <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="min-w-[560px] w-full text-sm">
            <thead className="border-b bg-muted/50">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Timestamp</th>
                <th className="px-4 py-2 text-left font-medium">Result</th>
                <th className="px-4 py-2 text-left font-medium">Duration</th>
                <th className="px-4 py-2 text-left font-medium">Triggered by</th>
              </tr>
            </thead>
            <tbody>
              {data.map((run) => {
                const isSelected = run.run_id === selectedRunId;
                return (
                  <tr
                    key={run.run_id}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    onClick={() => onSelectRun(run.run_id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectRun(run.run_id);
                      }
                    }}
                    className={`cursor-pointer border-b last:border-0 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset${
                      isSelected ? ' bg-muted/60' : ''
                    }`}
                  >
                    <td className="px-4 py-2 text-muted-foreground">
                      {formatTimestamp(run.started_at)}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          run.overall_passed
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                        }`}
                      >
                        {run.overall_passed ? 'pass' : 'fail'}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {formatDuration(run.duration_ms)}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground capitalize">
                      {run.triggered_by}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
