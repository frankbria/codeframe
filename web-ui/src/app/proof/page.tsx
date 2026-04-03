'use client';

import { useState, useEffect, useMemo, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import { InformationCircleIcon } from '@hugeicons/react';
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import { ProofStatusBadge, WaiveDialog } from '@/components/proof';
import { proofApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { ProofRequirement, ProofRequirementListResponse, ProofReqStatus, ProofSeverity } from '@/types';

// ── Sort / filter types ────────────────────────────────────────────────────

type SortCol = 'id' | 'title' | 'severity' | 'status' | 'created_at';
type SortDir = 'asc' | 'desc';

const SEVERITY_ORDER: ProofSeverity[] = ['critical', 'high', 'medium', 'low'];
const STATUS_ORDER: ProofReqStatus[] = ['open', 'satisfied', 'waived'];

function severityRank(s: ProofSeverity) {
  return SEVERITY_ORDER.indexOf(s);
}
function statusRank(s: ProofReqStatus) {
  return STATUS_ORDER.indexOf(s);
}

function sortReqs(reqs: ProofRequirement[], col: SortCol, dir: SortDir): ProofRequirement[] {
  return [...reqs].sort((a, b) => {
    let cmp = 0;
    switch (col) {
      case 'id':
        cmp = a.id.localeCompare(b.id);
        break;
      case 'title':
        cmp = a.title.localeCompare(b.title);
        break;
      case 'severity':
        cmp = severityRank(a.severity) - severityRank(b.severity);
        break;
      case 'status':
        cmp = statusRank(a.status) - statusRank(b.status);
        if (cmp === 0) cmp = severityRank(a.severity) - severityRank(b.severity);
        break;
      case 'created_at':
        cmp = (a.created_at ?? '').localeCompare(b.created_at ?? '');
        break;
    }
    return dir === 'asc' ? cmp : -cmp;
  });
}

// ── Sort button component ──────────────────────────────────────────────────

function SortHeader({
  col,
  label,
  activeCol,
  activeDir,
  onSort,
  children,
}: {
  col: SortCol;
  label: string;
  activeCol: SortCol;
  activeDir: SortDir;
  onSort: (col: SortCol) => void;
  children?: React.ReactNode;
}) {
  const isActive = activeCol === col;
  const ariaSort = isActive ? (activeDir === 'asc' ? 'ascending' : 'descending') : undefined;

  return (
    <button
      type="button"
      aria-label={`Sort by ${label}`}
      aria-sort={ariaSort}
      onClick={() => onSort(col)}
      className="flex items-center gap-1 font-medium hover:text-foreground"
    >
      {children ?? label}
      {isActive && (
        <span aria-hidden="true" className="text-xs leading-none">
          {activeDir === 'asc' ? '▲' : '▼'}
        </span>
      )}
    </button>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

function ProofPageContent() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);
  const [waivedReq, setWaivedReq] = useState<ProofRequirement | null>(null);

  // Sort state (default: status asc → open first, then severity)
  const [sortCol, setSortCol] = useState<SortCol>('status');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<'' | ProofReqStatus>('');
  const [filterSeverity, setFilterSeverity] = useState<'' | ProofSeverity>('');
  const [filterGlitch, setFilterGlitch] = useState('');

  const searchParams = useSearchParams();
  const gateFilter = searchParams.get('gate')?.toLowerCase() ?? null;

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  const { data, error, isLoading, mutate } = useSWR<ProofRequirementListResponse>(
    workspacePath ? `/api/v2/proof/requirements?path=${workspacePath}` : null,
    () => proofApi.listRequirements(workspacePath!)
  );

  // Collect unique glitch types from data for the dropdown
  const glitchTypes = useMemo(() => {
    if (!data) return [] as string[];
    const types = data.requirements
      .map((r) => r.glitch_type)
      .filter((g): g is string => g !== null && g !== '');
    return Array.from(new Set(types)).sort();
  }, [data]);

  function handleSort(col: SortCol) {
    if (col === sortCol) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }

  function resetFilters() {
    setSearchQuery('');
    setFilterStatus('');
    setFilterSeverity('');
    setFilterGlitch('');
  }

  if (!workspaceReady) return null;

  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected. Return to{' '}
              <Link href="/" className="text-primary hover:underline">Workspace</Link> and select a project.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <TooltipProvider>
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">PROOF9 Requirements</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            PROOF9 tracks quality requirements with evidence. Requirements must be satisfied or waived before shipping.{' '}
            <a href="#proof9-help" className="text-primary hover:underline">Learn more ↓</a>
          </p>
        </div>

        {isLoading && (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive bg-destructive/10 p-4">
            <p className="text-sm text-destructive">Failed to load requirements</p>
          </div>
        )}

        {data && data.total === 0 && (
          <div className="rounded-lg border bg-muted/50 p-8 text-center">
            <p className="text-muted-foreground">No requirements captured yet.</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Use <code className="rounded bg-muted px-1 py-0.5 text-xs">cf proof capture</code> to add the first one.
            </p>
          </div>
        )}

        {data && data.total > 0 && (() => {
          // Gate filter (from URL param)
          const gateFiltered = gateFilter
            ? data.requirements.filter((r) =>
                r.obligations.some((o) => o.gate.toLowerCase() === gateFilter)
              )
            : data.requirements;

          // Apply search + dropdowns (AND logic)
          const q = searchQuery.toLowerCase();
          const filtered = gateFiltered.filter((r) => {
            if (q && !r.id.toLowerCase().includes(q) && !r.title.toLowerCase().includes(q)) return false;
            if (filterStatus && r.status !== filterStatus) return false;
            if (filterSeverity && r.severity !== filterSeverity) return false;
            if (filterGlitch && r.glitch_type !== filterGlitch) return false;
            return true;
          });

          // Sort
          const visibleReqs = sortReqs(filtered, sortCol, sortDir);

          const hasActiveFilters = q || filterStatus || filterSeverity || filterGlitch;

          return (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
              <span>{data.by_status?.open ?? 0} open</span>
              <span>{data.by_status?.satisfied ?? 0} satisfied</span>
              <span>{data.by_status?.waived ?? 0} waived</span>
              <span className="font-medium text-foreground">{data.total} total</span>
              {gateFilter && (
                <span className="flex items-center gap-1.5 rounded-full border bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                  Filtered by gate: {gateFilter}
                  <Link href="/proof" aria-label={`Clear gate filter ${gateFilter}`} className="text-muted-foreground hover:text-foreground">✕</Link>
                </span>
              )}
            </div>

            {/* Status legend */}
            <div className="mb-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                <span><span className="font-medium text-foreground">open</span> — must be satisfied before shipping</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
                <span><span className="font-medium text-foreground">satisfied</span> — proven with collected evidence</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-gray-400" />
                <span><span className="font-medium text-foreground">waived</span> — approved exception, no evidence required</span>
              </span>
            </div>

            {/* Filter controls */}
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <input
                type="search"
                placeholder="Search by ID or title…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search requirements"
                className="h-8 rounded-md border bg-background px-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              />

              <label className="sr-only" htmlFor="filter-status">Status</label>
              <select
                id="filter-status"
                aria-label="Status"
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value as '' | ProofReqStatus)}
                className="h-8 rounded-md border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              >
                <option value="">All statuses</option>
                <option value="open">open</option>
                <option value="satisfied">satisfied</option>
                <option value="waived">waived</option>
              </select>

              <label className="sr-only" htmlFor="filter-severity">Severity</label>
              <select
                id="filter-severity"
                aria-label="Severity"
                value={filterSeverity}
                onChange={(e) => setFilterSeverity(e.target.value as '' | ProofSeverity)}
                className="h-8 rounded-md border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              >
                <option value="">All severities</option>
                <option value="critical">critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
              </select>

              <label className="sr-only" htmlFor="filter-glitch">Glitch Type</label>
              <select
                id="filter-glitch"
                aria-label="Glitch Type"
                value={filterGlitch}
                onChange={(e) => setFilterGlitch(e.target.value)}
                className="h-8 rounded-md border bg-background px-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              >
                <option value="">All glitch types</option>
                {glitchTypes.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>

              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={resetFilters} aria-label="Reset filters">
                  Reset
                </Button>
              )}
            </div>

            <div className="overflow-x-auto rounded-lg border">
              <table className="min-w-[800px] w-full text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">
                      <SortHeader col="id" label="ID" activeCol={sortCol} activeDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      <SortHeader col="title" label="Title" activeCol={sortCol} activeDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      <span className="flex items-center gap-1">
                        Glitch Type
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button type="button" aria-label="Explain Glitch Type" className="inline-flex cursor-help text-muted-foreground/60 hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                              <InformationCircleIcon className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>The category of quality issue this requirement addresses</TooltipContent>
                        </Tooltip>
                      </span>
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      <span className="flex items-center gap-1">
                        <SortHeader col="severity" label="Severity" activeCol={sortCol} activeDir={sortDir} onSort={handleSort} />
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button type="button" aria-label="Explain Severity" className="inline-flex cursor-help text-muted-foreground/60 hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                              <InformationCircleIcon className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>Impact level: critical, high, medium, or low</TooltipContent>
                        </Tooltip>
                      </span>
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      <span className="flex items-center gap-1">
                        Gates
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button type="button" aria-label="Explain Gates" className="inline-flex cursor-help text-muted-foreground/60 hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                              <InformationCircleIcon className="h-3.5 w-3.5" aria-hidden="true" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent>Number of evidence gates that must pass to satisfy this requirement</TooltipContent>
                        </Tooltip>
                      </span>
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      <SortHeader col="status" label="Status" activeCol={sortCol} activeDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3 text-left font-medium">
                      <SortHeader col="created_at" label="Created" activeCol={sortCol} activeDir={sortDir} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3 text-left font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {visibleReqs.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-sm text-muted-foreground">
                        {gateFilter
                          ? <>No requirements match gate &quot;{gateFilter}&quot;.{' '}<Link href="/proof" className="text-primary hover:underline">Clear filter</Link></>
                          : 'No requirements match the current filters.'}
                      </td>
                    </tr>
                  )}
                  {visibleReqs.map((req) => (
                    <tr key={req.id} className={`border-b last:border-0 hover:bg-muted/30${req.status === 'waived' ? ' opacity-60' : ''}`}>
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link href={`/proof/${encodeURIComponent(req.id)}`} className="text-primary hover:underline">
                          {req.id}
                        </Link>
                      </td>
                      <td className="max-w-xs px-4 py-3">
                        <span className="line-clamp-1">{req.title}</span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {req.glitch_type ?? '—'}
                      </td>
                      <td className="px-4 py-3 capitalize">{req.severity}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {req.obligations.length}
                      </td>
                      <td className="px-4 py-3">
                        <ProofStatusBadge status={req.status} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {req.created_at ? new Date(req.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-4 py-3">
                        {req.status !== 'waived' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setWaivedReq(req)}
                          >
                            Waive
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
          );
        })()}

        {waivedReq && (
          <WaiveDialog
            reqId={waivedReq.id}
            workspacePath={workspacePath}
            onClose={() => setWaivedReq(null)}
            onSuccess={() => {
              setWaivedReq(null);
              mutate();
            }}
          />
        )}

        {/* In-page help reference */}
        <section id="proof9-help" className="mt-12 rounded-lg border bg-muted/30 p-6">
          <h2 className="mb-3 text-base font-semibold">About PROOF9</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            PROOF9 is CodeFRAME&apos;s quality memory system. It captures requirements from past glitches and failures,
            then enforces that each requirement is <em>proven</em> through evidence before code ships. This creates a
            self-reinforcing quality loop: every bug becomes a permanent gate.
          </p>
          <div className="grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <h3 className="mb-1.5 font-medium">Key Terms</h3>
              <dl className="space-y-2 text-muted-foreground">
                <div>
                  <dt className="font-medium text-foreground">Glitch Type</dt>
                  <dd>The category of quality issue a requirement addresses (e.g., regression, security, performance).</dd>
                </div>
                <div>
                  <dt className="font-medium text-foreground">Severity</dt>
                  <dd>Impact level — <strong>critical</strong> blocks ship, <strong>high</strong> strongly recommended, <strong>medium/low</strong> advisory.</dd>
                </div>
                <div>
                  <dt className="font-medium text-foreground">Gates / Obligations</dt>
                  <dd>Evidence rules — specific tests or checks that must pass to satisfy a requirement.</dd>
                </div>
              </dl>
            </div>
            <div>
              <h3 className="mb-1.5 font-medium">Requirement Lifecycle</h3>
              <dl className="space-y-2 text-muted-foreground">
                <div>
                  <dt className="flex items-center gap-1.5 font-medium text-foreground">
                    <span className="h-2 w-2 rounded-full bg-red-400" /> open
                  </dt>
                  <dd>Not yet satisfied. Must be resolved (satisfied or waived) before shipping.</dd>
                </div>
                <div>
                  <dt className="flex items-center gap-1.5 font-medium text-foreground">
                    <span className="h-2 w-2 rounded-full bg-green-400" /> satisfied
                  </dt>
                  <dd>Evidence collected. All obligation gates passed.</dd>
                </div>
                <div>
                  <dt className="flex items-center gap-1.5 font-medium text-foreground">
                    <span className="h-2 w-2 rounded-full bg-gray-400" /> waived
                  </dt>
                  <dd>Approved exception with a recorded reason. No evidence required.</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>
      </div>
    </main>
    </TooltipProvider>
  );
}

export default function ProofPage() {
  return (
    <Suspense>
      <ProofPageContent />
    </Suspense>
  );
}
