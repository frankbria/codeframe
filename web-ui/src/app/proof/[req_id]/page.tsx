'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import useSWR from 'swr';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ProofStatusBadge, WaiveDialog, GateEvidencePanel } from '@/components/proof';
import { proofApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { ProofRequirement, ProofEvidence, ProofEvidenceSortCol, SortDir, ProofEvidenceWithContent } from '@/types';

function sessionKey(reqId: string) {
  return `proof-evidence-filters:${reqId}`;
}

function loadSessionFilters(reqId: string): { gate: string; result: string; search: string } {
  if (typeof window === 'undefined') return { gate: '', result: '', search: '' };
  try {
    const raw = sessionStorage.getItem(sessionKey(reqId));
    return raw ? JSON.parse(raw) : { gate: '', result: '', search: '' };
  } catch {
    return { gate: '', result: '', search: '' };
  }
}

function saveSessionFilters(reqId: string, gate: string, result: string, search: string) {
  try {
    sessionStorage.setItem(sessionKey(reqId), JSON.stringify({ gate, result, search }));
  } catch {
    // sessionStorage unavailable — ignore
  }
}

function SortButton({
  col,
  label,
  current,
  dir,
  onSort,
}: {
  col: ProofEvidenceSortCol;
  label: string;
  current: ProofEvidenceSortCol;
  dir: SortDir;
  onSort: (col: ProofEvidenceSortCol) => void;
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label={`Sort by ${label}`}
      onClick={() => onSort(col)}
      className="-mx-2 h-auto px-2 py-1 font-medium hover:bg-transparent hover:text-foreground"
    >
      {label}
      {current === col && <span className="ml-1 text-xs">{dir === 'asc' ? '↑' : '↓'}</span>}
    </Button>
  );
}

export default function ProofDetailPage() {
  const params = useParams();
  const reqId = params.req_id as string;

  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [showWaiveDialog, setShowWaiveDialog] = useState(false);

  // Filter state (restored from sessionStorage on mount)
  const [filterGate, setFilterGate] = useState('');
  const [filterResult, setFilterResult] = useState('');
  const [search, setSearch] = useState('');

  // Sort state (default: timestamp descending)
  const [sortCol, setSortCol] = useState<ProofEvidenceSortCol>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
    const saved = loadSessionFilters(reqId);
    setFilterGate(saved.gate);
    setFilterResult(saved.result);
    setSearch(saved.search);
  }, []);

  const { data: req, error: reqError, isLoading: reqLoading, mutate: mutateReq } =
    useSWR<ProofRequirement>(
      workspacePath && reqId ? `/api/v2/proof/requirements/${reqId}?path=${workspacePath}` : null,
      () => proofApi.getRequirement(workspacePath!, reqId)
    );

  const { data: evidence, error: evidenceError, isLoading: evidenceLoading } =
    useSWR<ProofEvidence[]>(
      workspacePath && reqId ? `/api/v2/proof/requirements/${reqId}/evidence?path=${workspacePath}` : null,
      () => proofApi.getEvidence(workspacePath!, reqId)
    );

  // Get the most recent run_id from evidence to show artifact content
  const latestRunId = useMemo(() => {
    if (!Array.isArray(evidence) || evidence.length === 0) return null;
    return [...evidence].sort((a, b) => b.timestamp.localeCompare(a.timestamp))[0]?.run_id ?? null;
  }, [evidence]);

  const { data: latestRunDetail } = useSWR<import('@/types').ProofRunDetail>(
    workspacePath && latestRunId ? `/api/v2/proof/runs/${latestRunId}/evidence?path=${workspacePath}` : null,
    () => proofApi.getRunDetail(workspacePath!, latestRunId!)
  );

  const latestEvidence: ProofEvidenceWithContent[] = useMemo(
    () => (latestRunDetail?.evidence ?? []).filter((ev) => ev.req_id === reqId),
    [latestRunDetail, reqId]
  );

  // Map gate name → most-recent evidence entry for that gate
  const latestRunByGate = useMemo<Record<string, ProofEvidence>>(() => {
    if (!Array.isArray(evidence) || evidence.length === 0) return {};
    const map: Record<string, ProofEvidence> = {};
    for (const ev of evidence) {
      const existing = map[ev.gate];
      if (!existing || ev.timestamp > existing.timestamp) {
        map[ev.gate] = ev;
      }
    }
    return map;
  }, [evidence]);

  const hasActiveFilters = filterGate !== '' || filterResult !== '' || search !== '';

  const gateOptions = useMemo(() => {
    if (!Array.isArray(evidence)) return [];
    return Array.from(new Set(evidence.map((e) => e.gate))).sort();
  }, [evidence]);

  const filteredEvidence = useMemo(() => {
    if (!Array.isArray(evidence)) return [];
    let rows = [...evidence];

    if (filterGate) rows = rows.filter((e) => e.gate === filterGate);
    if (filterResult === 'pass') rows = rows.filter((e) => e.satisfied);
    if (filterResult === 'fail') rows = rows.filter((e) => !e.satisfied);
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (e) =>
          e.run_id.toLowerCase().includes(q) ||
          (e.artifact_path ?? '').toLowerCase().includes(q)
      );
    }

    rows.sort((a, b) => {
      let cmp = 0;
      switch (sortCol) {
        case 'gate':      cmp = a.gate.localeCompare(b.gate); break;
        case 'result':    cmp = Number(a.satisfied) - Number(b.satisfied); break;
        case 'run_id':    cmp = a.run_id.localeCompare(b.run_id); break;
        case 'timestamp': cmp = a.timestamp.localeCompare(b.timestamp); break;
        case 'artifact':  cmp = (a.artifact_path ?? '').localeCompare(b.artifact_path ?? ''); break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return rows;
  }, [evidence, filterGate, filterResult, search, sortCol, sortDir]);

  function handleSort(col: ProofEvidenceSortCol) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }

  function updateGate(val: string) {
    setFilterGate(val);
    saveSessionFilters(reqId, val, filterResult, search);
  }

  function updateResult(val: string) {
    setFilterResult(val);
    saveSessionFilters(reqId, filterGate, val, search);
  }

  function updateSearch(val: string) {
    setSearch(val);
    saveSessionFilters(reqId, filterGate, filterResult, val);
  }

  function resetFilters() {
    setFilterGate('');
    setFilterResult('');
    setSearch('');
    saveSessionFilters(reqId, '', '', '');
  }

  if (!workspaceReady) return null;

  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <p className="text-muted-foreground">No workspace selected.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-4xl px-4 py-8">
        <Link href="/proof" className="mb-6 inline-block text-sm text-muted-foreground hover:text-foreground">
          ← Back to requirements
        </Link>

        {reqLoading && (
          <div className="space-y-4">
            <div className="h-8 w-64 animate-pulse rounded bg-muted" />
            <div className="h-24 animate-pulse rounded bg-muted" />
          </div>
        )}

        {reqError && (
          <div className="rounded-lg border border-destructive bg-destructive/10 p-4">
            <p className="text-sm text-destructive">Requirement not found</p>
          </div>
        )}

        {req && (
          <div className="space-y-8">
            {/* Header */}
            <div>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="mb-1 font-mono text-xs text-muted-foreground">{req.id}</p>
                  <h1 className="text-2xl font-bold">{req.title}</h1>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <span className="rounded-md bg-muted px-2 py-1 text-xs capitalize">{req.severity}</span>
                  <ProofStatusBadge status={req.status} />
                </div>
              </div>
              {req.description && (
                <div className="prose prose-sm mt-3 max-w-none text-muted-foreground">
                  <ReactMarkdown>{req.description}</ReactMarkdown>
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                {req.created_at && <span>Created {new Date(req.created_at).toLocaleDateString()}</span>}
                {req.source && <span>Source: {req.source}</span>}
                {req.source_issue && <span>Issue: {req.source_issue}</span>}
                {req.created_by && <span>By: {req.created_by}</span>}
                {req.waiver?.expires && <span>Waiver expires: {req.waiver.expires}</span>}
              </div>
              {req.scope && (() => {
                const parts = [
                  ...req.scope.routes,
                  ...req.scope.components,
                  ...req.scope.apis,
                  ...req.scope.files,
                  ...req.scope.tags,
                ].filter(Boolean);
                return parts.length > 0 ? (
                  <div className="mt-2 text-xs text-muted-foreground">
                    <span className="font-medium">Where found:</span> {parts.join(', ')}
                  </div>
                ) : null;
              })()}
            </div>

            {/* Glitch Type */}
            {req.glitch_type && (
              <section>
                <h2 className="mb-3 text-base font-semibold">Glitch Type</h2>
                <span className="rounded-md bg-muted px-2 py-1 text-sm">{req.glitch_type}</span>
              </section>
            )}

            {/* Obligations */}
            {req.obligations.length > 0 && (
              <section>
                <h2 className="mb-3 text-base font-semibold">Gate Obligations</h2>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="min-w-full text-sm">
                    <thead className="border-b bg-muted/50">
                      <tr>
                        <th className="px-4 py-2 text-left font-medium">Gate</th>
                        <th className="px-4 py-2 text-left font-medium">Status</th>
                        <th className="px-4 py-2 text-left font-medium">Latest Run</th>
                      </tr>
                    </thead>
                    <tbody>
                      {req.obligations.map((ob, i) => {
                        const latestEv = latestRunByGate[ob.gate];
                        const effectiveStatus = latestEv
                          ? latestEv.satisfied ? 'satisfied' : 'failed'
                          : ob.status;
                        return (
                          <tr key={i} className="border-b last:border-0">
                            <td className="px-4 py-2 font-mono text-xs">{ob.gate}</td>
                            <td className="px-4 py-2 capitalize">
                              <span className={
                                effectiveStatus === 'satisfied'
                                  ? 'text-green-600'
                                  : effectiveStatus === 'failed'
                                  ? 'text-red-600'
                                  : 'text-muted-foreground'
                              }>
                                {effectiveStatus}
                              </span>
                            </td>
                            <td className="px-4 py-2 font-mono text-xs text-muted-foreground">
                              {latestEv ? (
                                <span className={latestEv.satisfied ? 'text-green-600' : 'text-red-600'}>
                                  {latestEv.run_id}
                                </span>
                              ) : '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Latest run gate evidence */}
            {latestEvidence.length > 0 && (
              <section>
                <h2 className="mb-3 text-base font-semibold">Latest Run Evidence</h2>
                <GateEvidencePanel evidence={latestEvidence} />
              </section>
            )}

            {/* Evidence history */}
            <section>
              <h2 className="mb-3 text-base font-semibold">Evidence History</h2>

              {/* Filter controls */}
              {Array.isArray(evidence) && evidence.length > 0 && (
                <div className="mb-4 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Gate</span>
                    <select
                      aria-label="Gate"
                      value={filterGate}
                      onChange={(e) => updateGate(e.target.value)}
                      className="rounded border bg-background px-2 py-1 text-sm"
                    >
                      <option value="">All</option>
                      {gateOptions.map((g) => (
                        <option key={g} value={g}>{g}</option>
                      ))}
                    </select>
                  </label>

                  <label className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Result</span>
                    <select
                      aria-label="Result"
                      value={filterResult}
                      onChange={(e) => updateResult(e.target.value)}
                      className="rounded border bg-background px-2 py-1 text-sm"
                    >
                      <option value="">All</option>
                      <option value="pass">Pass</option>
                      <option value="fail">Fail</option>
                    </select>
                  </label>

                  <Input
                    type="text"
                    placeholder="Search run ID or artifact…"
                    value={search}
                    onChange={(e) => updateSearch(e.target.value)}
                    aria-label="Search run ID or artifact"
                    className="h-8 w-56 text-sm"
                  />

                  {hasActiveFilters && (
                    <Button variant="ghost" size="sm" onClick={resetFilters}>
                      Reset filters
                    </Button>
                  )}
                </div>
              )}

              {evidenceLoading && (
                <div className="h-16 animate-pulse rounded bg-muted" />
              )}
              {!evidenceLoading && evidenceError && (
                <p className="text-sm text-destructive">Failed to load evidence.</p>
              )}
              {!evidenceLoading && !evidenceError && (!evidence || !Array.isArray(evidence) || evidence.length === 0) && (
                <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
                  <p>No gate runs yet for this requirement.</p>
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/review">Run Gates →</Link>
                  </Button>
                </div>
              )}
              {Array.isArray(evidence) && evidence.length > 0 && (
                <div className="overflow-x-auto rounded-lg border">
                  <table className="min-w-[640px] w-full text-sm">
                    <thead className="border-b bg-muted/50">
                      <tr>
                        <th
                          className="px-4 py-2 text-left"
                          aria-sort={sortCol === 'gate' ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                        >
                          <SortButton col="gate" label="Gate" current={sortCol} dir={sortDir} onSort={handleSort} />
                        </th>
                        <th
                          className="px-4 py-2 text-left"
                          aria-sort={sortCol === 'result' ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                        >
                          <SortButton col="result" label="Result" current={sortCol} dir={sortDir} onSort={handleSort} />
                        </th>
                        <th
                          className="px-4 py-2 text-left"
                          aria-sort={sortCol === 'run_id' ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                        >
                          <SortButton col="run_id" label="Run ID" current={sortCol} dir={sortDir} onSort={handleSort} />
                        </th>
                        <th
                          className="px-4 py-2 text-left"
                          aria-sort={sortCol === 'timestamp' ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                        >
                          <SortButton col="timestamp" label="Timestamp" current={sortCol} dir={sortDir} onSort={handleSort} />
                        </th>
                        <th
                          className="px-4 py-2 text-left"
                          aria-sort={sortCol === 'artifact' ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
                        >
                          <SortButton col="artifact" label="Artifact" current={sortCol} dir={sortDir} onSort={handleSort} />
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredEvidence.map((ev) => (
                        <tr
                          key={`${ev.req_id}:${ev.run_id}:${ev.timestamp}:${ev.gate}:${ev.artifact_path}`}
                          className="border-b last:border-0"
                        >
                          <td className="px-4 py-2 font-mono text-xs">{ev.gate}</td>
                          <td className="px-4 py-2">
                            <span className={ev.satisfied ? 'text-green-600' : 'text-red-600'}>
                              {ev.satisfied ? 'pass' : 'fail'}
                            </span>
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{ev.run_id}</td>
                          <td className="px-4 py-2 text-muted-foreground">
                            {new Date(ev.timestamp).toLocaleString()}
                          </td>
                          <td className="max-w-xs px-4 py-2 font-mono text-xs text-muted-foreground">
                            <span className="line-clamp-1">{ev.artifact_path || '—'}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            {/* Waiver */}
            <section>
              <h2 className="mb-3 text-base font-semibold">Waiver</h2>
              {req.waiver ? (
                <div className="rounded-lg border bg-muted/30 p-4">
                  <p className="text-sm"><span className="font-medium">Reason:</span> {req.waiver.reason}</p>
                  {req.waiver.approved_by && (
                    <p className="mt-1 text-sm text-muted-foreground">Approved by: {req.waiver.approved_by}</p>
                  )}
                  {req.waiver.waived_at && (
                    <p className="mt-1 text-sm text-muted-foreground">Waived: {new Date(req.waiver.waived_at).toLocaleString()}</p>
                  )}
                  {req.waiver.expires && (
                    <p className="mt-1 text-sm text-muted-foreground">Expires: {req.waiver.expires}</p>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No waiver on file.</p>
              )}
              {req.status !== 'waived' && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => setShowWaiveDialog(true)}
                >
                  Waive this requirement
                </Button>
              )}
            </section>
          </div>
        )}

        {showWaiveDialog && workspacePath && (
          <WaiveDialog
            reqId={reqId}
            workspacePath={workspacePath}
            onClose={() => setShowWaiveDialog(false)}
            onSuccess={() => {
              setShowWaiveDialog(false);
              mutateReq();
            }}
          />
        )}
      </div>
    </main>
  );
}
