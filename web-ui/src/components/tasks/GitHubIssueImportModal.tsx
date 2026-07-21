'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import useSWR from 'swr';
import { formatDistanceToNowStrict } from 'date-fns';
import { HugeiconsIcon } from '@hugeicons/react';
import { Search01Icon, ArrowLeft01Icon, ArrowRight01Icon, Cancel01Icon, Loading03Icon, Alert02Icon } from '@hugeicons/core-free-icons';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { integrationsApi } from '@/lib/api';
import type { GitHubIssue, GitHubIssuesResponse, ApiError } from '@/types';

interface GitHubIssueImportModalProps {
  open: boolean;
  workspacePath: string;
  /** Connected repo slug ("owner/repo") for the header, when known. */
  repo?: string | null;
  /** True while the parent is executing the import (#565) — shows progress. */
  importing?: boolean;
  /** Error message from a failed import (#565) — rendered inline in the modal. */
  importError?: string | null;
  onClose: () => void;
  /** Called with the chosen issues when the user confirms the import. */
  onImport: (selectedIssues: GitHubIssue[]) => void;
}

const PER_PAGE = 25;

export function GitHubIssueImportModal({
  open,
  workspacePath,
  repo,
  importing = false,
  importError = null,
  onClose,
  onImport,
}: GitHubIssueImportModalProps) {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [labelFilter, setLabelFilter] = useState('');
  // Selected issues, keyed by number. Persists across page changes and is the
  // source of truth for the import payload (so selections survive paging even
  // when a row is no longer in the current page's data).
  const [selected, setSelected] = useState<Map<number, GitHubIssue>>(new Map());

  // ─── Debounce the search box (300ms) before it drives a new fetch ──────
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset transient state each time the modal is (re)opened.
  useEffect(() => {
    if (open) {
      setPage(1);
      setSearchInput('');
      setSearch('');
      setLabelFilter('');
      setSelected(new Map());
    }
  }, [open]);

  const { data, error, isLoading } = useSWR<GitHubIssuesResponse, ApiError>(
    open
      ? ['github-issues', workspacePath, page, search, labelFilter]
      : null,
    () =>
      integrationsApi.getIssues(workspacePath, {
        page,
        perPage: PER_PAGE,
        search,
        label: labelFilter,
      })
  );

  const issues = useMemo(() => data?.issues ?? [], [data]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));

  // ─── Selection helpers ─────────────────────────────────────────────────
  const toggleOne = useCallback((issue: GitHubIssue) => {
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(issue.number)) {
        next.delete(issue.number);
      } else {
        next.set(issue.number, issue);
      }
      return next;
    });
  }, []);

  const pageSelectionState = useMemo<'none' | 'some' | 'all'>(() => {
    if (issues.length === 0) return 'none';
    const selectedOnPage = issues.filter((i) => selected.has(i.number)).length;
    if (selectedOnPage === 0) return 'none';
    if (selectedOnPage === issues.length) return 'all';
    return 'some';
  }, [issues, selected]);

  const toggleAllOnPage = useCallback(() => {
    setSelected((prev) => {
      const next = new Map(prev);
      const allSelected = issues.every((i) => next.has(i.number));
      if (allSelected) {
        for (const i of issues) next.delete(i.number);
      } else {
        for (const i of issues) next.set(i.number, i);
      }
      return next;
    });
  }, [issues]);

  const handleImport = useCallback(() => {
    onImport(Array.from(selected.values()));
  }, [onImport, selected]);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="flex h-[80vh] max-h-[80vh] w-full max-w-3xl flex-col gap-0 p-0">
        {/* Header */}
        <DialogHeader className="flex-row items-center justify-between border-b px-6 py-4 text-left">
          <DialogTitle className="text-base font-semibold">
            Import Issues from GitHub
            {repo && (
              <span className="ml-2 font-normal text-muted-foreground">
                · {repo}
              </span>
            )}
          </DialogTitle>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring"
          >
            <HugeiconsIcon icon={Cancel01Icon} className="h-4 w-4" />
          </button>
        </DialogHeader>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 border-b px-6 py-3">
          <div className="relative flex-1 min-w-[200px]">
            <HugeiconsIcon icon={Search01Icon} className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by title..."
              aria-label="Search issues by title"
              className="pl-8"
            />
          </div>
          <Input
            value={labelFilter}
            onChange={(e) => {
              setLabelFilter(e.target.value);
              setPage(1);
            }}
            placeholder="Label"
            aria-label="Filter by label"
            className="w-40"
          />
        </div>

        {/* Toolbar: select-all + selected count */}
        <div className="flex items-center justify-between border-b px-6 py-2">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Checkbox
              checked={
                pageSelectionState === 'all'
                  ? true
                  : pageSelectionState === 'some'
                  ? 'indeterminate'
                  : false
              }
              onCheckedChange={toggleAllOnPage}
              disabled={issues.length === 0}
              aria-label="Select all on page"
            />
            Select all on page
          </label>
          {selected.size > 0 && (
            <Badge variant="secondary">{selected.size} selected</Badge>
          )}
        </div>

        {/* Issue list */}
        <div className="flex-1 overflow-y-auto px-6 py-2">
          {isLoading && (
            <div className="space-y-2 py-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-12 animate-pulse rounded bg-muted/40"
                />
              ))}
            </div>
          )}

          {error && !isLoading && (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-md border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive"
            >
              <HugeiconsIcon icon={Alert02Icon} className="h-4 w-4 shrink-0" />
              <span>{error.detail || 'Failed to load issues.'}</span>
            </div>
          )}

          {!isLoading && !error && issues.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center text-sm text-muted-foreground">
              No open issues match your filters.
            </div>
          )}

          {!isLoading &&
            !error &&
            issues.map((issue) => {
              const isSelected = selected.has(issue.number);
              return (
                <label
                  key={issue.number}
                  className="flex cursor-pointer items-center gap-3 border-b py-2.5 last:border-b-0 hover:bg-muted/40"
                >
                  <Checkbox
                    checked={isSelected}
                    onCheckedChange={() => toggleOne(issue)}
                    aria-label={`Select issue #${issue.number}`}
                  />
                  <span className="w-12 shrink-0 text-xs font-mono text-muted-foreground">
                    #{issue.number}
                  </span>
                  <span className="flex-1 truncate text-sm font-medium">
                    {issue.title}
                  </span>
                  <span className="flex shrink-0 flex-wrap gap-1">
                    {issue.labels.slice(0, 3).map((label) => (
                      <Badge
                        key={label}
                        variant="outline"
                        className="text-[10px]"
                      >
                        {label}
                      </Badge>
                    ))}
                  </span>
                  <span className="w-20 shrink-0 truncate text-xs text-muted-foreground">
                    {issue.assignee ? `@${issue.assignee}` : '—'}
                  </span>
                  <span className="w-16 shrink-0 text-right text-xs text-muted-foreground">
                    {formatAge(issue.created_at)}
                  </span>
                </label>
              );
            })}
        </div>

        {/* Import error (kept in-modal so the selection is preserved) */}
        {importError && (
          <div
            role="alert"
            className="flex items-center gap-2 border-t border-destructive/40 bg-destructive/10 px-6 py-2.5 text-sm text-destructive"
          >
            <HugeiconsIcon icon={Alert02Icon} className="h-4 w-4 shrink-0" />
            <span>{importError}</span>
          </div>
        )}

        {/* Footer: pagination + actions */}
        <div className="flex items-center justify-between border-t px-6 py-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || isLoading}
              aria-label="Previous page"
            >
              <HugeiconsIcon icon={ArrowLeft01Icon} className="h-4 w-4" />
            </Button>
            <span>
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isLoading}
              aria-label="Next page"
            >
              <HugeiconsIcon icon={ArrowRight01Icon} className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleImport}
              disabled={selected.size === 0 || importing}
            >
              {(isLoading || importing) && (
                <HugeiconsIcon icon={Loading03Icon} className="mr-1.5 h-4 w-4 animate-spin" />
              )}
              {importing
                ? `Importing ${selected.size} issue${selected.size !== 1 ? 's' : ''}…`
                : 'Import Selected'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const AGE_UNIT_ABBR: Record<string, string> = {
  second: 's',
  minute: 'm',
  hour: 'h',
  day: 'd',
  week: 'w',
  month: 'mo',
  year: 'y',
};

/** Render an ISO timestamp as a compact relative age (e.g. "3d", "2mo").
 *
 * Uses the *strict* formatter so there are no "about "/"almost "/"less than a
 * minute" prefixes to mangle; output is always "<n> <unit>" which we then
 * abbreviate. Tolerates empty/invalid input by returning "".
 */
function formatAge(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const strict = formatDistanceToNowStrict(d); // e.g. "3 days", "1 minute"
  const match = strict.match(/^(\d+)\s+(\w+?)s?$/);
  if (!match) return strict;
  const [, count, unit] = match;
  return `${count}${AGE_UNIT_ABBR[unit] ?? unit}`;
}
