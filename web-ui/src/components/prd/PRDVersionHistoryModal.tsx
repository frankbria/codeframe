'use client';

import { useState } from 'react';
import useSWR from 'swr';
import {
  ArrowLeft01Icon,
  Loading03Icon,
  Time01Icon,
} from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { prdApi } from '@/lib/api';
import type { PrdResponse, PrdDiffResponse } from '@/types';

interface PRDVersionHistoryModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  prd: PrdResponse;
  workspacePath: string;
  onVersionRestored: (prd: PrdResponse) => void;
}

type View = 'list' | 'preview';

interface PreviewState {
  version: PrdResponse;
  diff: PrdDiffResponse | null;
  diffLoading: boolean;
  confirmingRestore: boolean;
  restoring: boolean;
}

export function PRDVersionHistoryModal({
  open,
  onOpenChange,
  prd,
  workspacePath,
  onVersionRestored,
}: PRDVersionHistoryModalProps) {
  const [view, setView] = useState<View>('list');
  const [preview, setPreview] = useState<PreviewState | null>(null);

  const { data: versions, error, isLoading } = useSWR<PrdResponse[]>(
    open ? `/api/v2/prd/${prd.id}/versions?path=${workspacePath}` : null,
    () => prdApi.getVersions(prd.id, workspacePath)
  );

  function handleClose() {
    onOpenChange(false);
    setView('list');
    setPreview(null);
  }

  function handleViewVersion(version: PrdResponse) {
    setPreview({
      version,
      diff: null,
      diffLoading: false,
      confirmingRestore: false,
      restoring: false,
    });
    setView('preview');
  }

  function handleBackToList() {
    setView('list');
    setPreview(null);
  }

  async function handleCompare() {
    if (!preview) return;
    setPreview((p) => p && { ...p, diffLoading: true, diff: null });
    try {
      const result = await prdApi.diff(
        prd.id,
        workspacePath,
        preview.version.version,
        prd.version
      );
      setPreview((p) => p && { ...p, diff: result, diffLoading: false });
    } catch {
      setPreview((p) => p && { ...p, diffLoading: false });
    }
  }

  async function handleConfirmRestore() {
    if (!preview) return;
    setPreview((p) => p && { ...p, restoring: true });
    try {
      const restored = await prdApi.createVersion(
        prd.id,
        workspacePath,
        preview.version.content,
        `Restored from version ${preview.version.version}`
      );
      onVersionRestored(restored);
      handleClose();
    } catch {
      setPreview((p) => p && { ...p, restoring: false, confirmingRestore: false });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Time01Icon className="h-5 w-5 text-muted-foreground" />
            {view === 'list' ? 'Version History' : `Version ${preview?.version.version} Preview`}
          </DialogTitle>
        </DialogHeader>

        {view === 'list' ? (
          <VersionList
            versions={versions}
            currentVersion={prd.version}
            isLoading={isLoading}
            error={error}
            onViewVersion={handleViewVersion}
          />
        ) : preview ? (
          <VersionPreview
            preview={preview}
            currentVersion={prd.version}
            onBack={handleBackToList}
            onCompare={handleCompare}
            onStartRestore={() =>
              setPreview((p) => p && { ...p, confirmingRestore: true, diff: null })
            }
            onCancelRestore={() =>
              setPreview((p) => p && { ...p, confirmingRestore: false })
            }
            onConfirmRestore={handleConfirmRestore}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

// ── Version List ─────────────────────────────────────────────────────────────

interface VersionListProps {
  versions: PrdResponse[] | undefined;
  currentVersion: number;
  isLoading: boolean;
  error: unknown;
  onViewVersion: (v: PrdResponse) => void;
}

function VersionList({ versions, currentVersion, isLoading, error, onViewVersion }: VersionListProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 text-muted-foreground">
        <Loading03Icon className="mr-2 h-4 w-4 animate-spin" />
        Loading versions...
      </div>
    );
  }

  if (error || !versions) {
    return (
      <div className="py-8 text-center text-sm text-destructive">
        Failed to load version history.
      </div>
    );
  }

  return (
    <ScrollArea className="max-h-[60vh]">
      <div className="divide-y">
        {versions.map((v) => {
          const isCurrent = v.version === currentVersion;
          return (
            <div key={v.id} className="flex items-center gap-3 py-3 pr-1">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">Version {v.version}</span>
                  {isCurrent && (
                    <Badge variant="secondary" className="text-xs">
                      Current
                    </Badge>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {new Date(v.created_at).toLocaleString()}
                </p>
                <p className="mt-0.5 text-xs italic text-muted-foreground">
                  {v.change_summary ?? 'No summary'}
                </p>
              </div>
              {!isCurrent && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onViewVersion(v)}
                >
                  View
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </ScrollArea>
  );
}

// ── Version Preview ───────────────────────────────────────────────────────────

interface VersionPreviewProps {
  preview: PreviewState;
  currentVersion: number;
  onBack: () => void;
  onCompare: () => void;
  onStartRestore: () => void;
  onCancelRestore: () => void;
  onConfirmRestore: () => void;
}

function VersionPreview({
  preview,
  onBack,
  onCompare,
  onStartRestore,
  onCancelRestore,
  onConfirmRestore,
}: VersionPreviewProps) {
  const { version, diff, diffLoading, confirmingRestore, restoring } = preview;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft01Icon className="mr-1.5 h-4 w-4" />
          Back to list
        </Button>
        <div className="ml-auto flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onCompare}
            disabled={diffLoading || !!diff}
          >
            {diffLoading ? (
              <>
                <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
                Loading diff...
              </>
            ) : (
              'Compare with current'
            )}
          </Button>
          {!confirmingRestore && (
            <Button variant="outline" size="sm" onClick={onStartRestore}>
              Restore this version
            </Button>
          )}
        </div>
      </div>

      {confirmingRestore ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
          <p className="text-sm font-medium">
            Restore version {version.version}?
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            This will create a new version with this content. Your current version
            will not be deleted.
          </p>
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              onClick={onConfirmRestore}
              disabled={restoring}
            >
              {restoring ? (
                <>
                  <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
                  Restoring...
                </>
              ) : (
                'Confirm restore'
              )}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onCancelRestore}
              disabled={restoring}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : diff ? (
        <ScrollArea className="max-h-[50vh]">
          <pre className="rounded-md bg-muted p-4 font-mono text-xs whitespace-pre-wrap">
            {diff.diff}
          </pre>
        </ScrollArea>
      ) : (
        <ScrollArea className="max-h-[50vh]">
          <pre className="rounded-md bg-muted p-4 font-mono text-xs whitespace-pre-wrap">
            {version.content}
          </pre>
        </ScrollArea>
      )}
    </div>
  );
}
